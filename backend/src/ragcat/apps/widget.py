"""HTTP helpers for the Website widget (api-design.md §7): the frame page an owner's site embeds,
the visitor's IP for the rate limit, and the public view of an answer's citations."""

from __future__ import annotations

import html
import threading
import time
from typing import Any, Callable, Iterator

import httpx
from fastapi import Request

from ragcat.assistants.domain import AssistantConfig
from ragcat.shared.errors import UpstreamUnavailable

Event = tuple[str, dict[str, Any]]

ROOT = '<div id="root"></div>'
TEMPLATE_TTL = 60.0
CITATION_FIELDS = ("n", "document_title", "page", "para")


class WidgetPage:
    """Fills in the built widget.html (Vite's output, so its asset names stay hashed) with one
    Assistant. The template is fetched from `url` and kept for a minute."""

    def __init__(self, url: str, fetch: Callable[[str], str] | None = None) -> None:
        self.url = url
        self.fetch = fetch or _get
        self._lock = threading.Lock()
        self._template: tuple[float, str] | None = None

    def template(self) -> str:
        with self._lock:
            if self._template and self._template[0] > time.monotonic():
                return self._template[1]
        try:
            text = self.fetch(self.url)
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable("The widget page is unavailable") from exc
        if ROOT not in text:
            raise UpstreamUnavailable("The widget page template has no #root")
        with self._lock:
            self._template = (time.monotonic() + TEMPLATE_TTL, text)
        return text

    def render(self, aid: str, config: AssistantConfig | None) -> tuple[str, dict[str, str]]:
        """The page and its headers. Only the owner's sites may frame it; an unknown Assistant or
        one with no sites can't be framed anywhere."""
        attrs = {"data-aid": aid, "data-available": "true" if config and config.widget_on else "false"}
        if config:
            attrs |= {"data-name": config.name, "data-contact": config.fallback_contact}
        root = '<div id="root" ' + " ".join(f'{k}="{html.escape(v, quote=True)}"' for k, v in attrs.items()) + "></div>"
        ancestors = " ".join(config.widget_origins) if config and config.widget_origins else "'none'"
        headers = {
            "Content-Security-Policy": f"frame-ancestors {ancestors}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        }
        return self.template().replace(ROOT, root, 1), headers


def _get(url: str) -> str:
    response = httpx.get(url, timeout=5.0)
    response.raise_for_status()
    return response.text


def visitor_ip(request: Request) -> str:
    """CloudFront's view of the visitor ("ip:port"). The ALB only accepts CloudFront, so the header
    can be trusted; X-Forwarded-For can be forged by the client. Locally, the socket's address."""
    viewer = request.headers.get("cloudfront-viewer-address")
    if viewer:
        return viewer.rsplit(":", 1)[0]
    return request.client.host if request.client else "unknown"


def public_events(events: Iterator[Event]) -> Iterator[Event]:
    """Customers see which Document and page an answer used, not the passage ids or boxes."""
    for name, data in events:
        if name == "citations":
            data = {"items": [{k: c.get(k) for k in CITATION_FIELDS} for c in data["items"]]}
        yield name, data
