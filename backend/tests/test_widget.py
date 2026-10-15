"""Website widget pieces that need no database (api-design.md §7)."""

from __future__ import annotations

import pytest

from ragcat.apps.widget import WidgetPage, public_events
from ragcat.assistants.domain import Assistant, AssistantConfig, widget_origin
from ragcat.infra.cache import MemoryCache, fixed_window
from ragcat.shared.errors import UpstreamUnavailable, ValidationError

TEMPLATE = '<!doctype html><html><body><div id="root"></div><script type="module" src="/assets/widget-abc.js"></script></body></html>'


def config(published: bool = True, origins: tuple[str, ...] = ("https://mochipet.example",)) -> AssistantConfig:
    return AssistantConfig("ast_1", "owner", 'Mochi "Pet" <Co.>', "help@mochipet.example", published, 3, (), origins)


def test_widget_origins_are_whole_sites_over_https() -> None:
    assert widget_origin(" HTTPS://Shop.Mochipet.example/ ") == "https://shop.mochipet.example"
    assert widget_origin("https://mochipet.example:8443") == "https://mochipet.example:8443"
    assert widget_origin("http://localhost:5173") == "http://localhost:5173"
    for bad in ("mochipet.example", "https://mochipet.example/shop", "https://*.mochipet.example", "http://mochipet.example", "https://mochipet", "ftp://mochipet.example"):
        with pytest.raises(ValidationError):
            widget_origin(bad)


def test_an_assistant_keeps_up_to_ten_distinct_sites() -> None:
    a = Assistant("ast_1", "owner", "AS-01", "Mochi", "")
    a.set_widget_origins(["https://a.example", "https://A.example/", "https://b.example"])
    assert a.widget_origins == ["https://a.example", "https://b.example"]
    with pytest.raises(ValidationError):
        a.set_widget_origins([f"https://s{i}.example" for i in range(11)])


def test_the_widget_answers_only_when_published_with_a_site() -> None:
    assert config().widget_on
    assert not config(published=False).widget_on
    assert not config(origins=()).widget_on
    # Configs cached before the widget existed still load.
    old = config().to_dict()
    del old["widget_origins"]
    assert AssistantConfig.from_dict(old).widget_origins == ()


def test_fixed_window_counts_per_slot_and_names_the_wait() -> None:
    cache = MemoryCache()
    assert [fixed_window(cache, "rl:w:a:1.2.3.4", 2, 60, 120.0) for _ in range(2)] == [None, None]
    assert fixed_window(cache, "rl:w:a:1.2.3.4", 2, 60, 150.0) == 30
    assert fixed_window(cache, "rl:w:a:5.6.7.8", 2, 60, 150.0) is None  # another visitor
    assert fixed_window(cache, "rl:w:a:1.2.3.4", 2, 60, 180.0) is None  # the next minute


def test_fixed_window_lets_requests_through_when_the_cache_is_down() -> None:
    class Down(MemoryCache):
        def incr(self, key: str, ttl: int) -> int | None:
            return None

    assert all(fixed_window(Down(), "rl", 1, 60, 0.0) is None for _ in range(5))


def test_frame_page_is_framable_only_by_the_owners_sites() -> None:
    page = WidgetPage("https://ragcat.example/widget.html", fetch=lambda _: TEMPLATE)
    body, headers = page.render("ast_1", config(origins=("https://mochipet.example", "http://localhost:5173")))
    assert headers["Content-Security-Policy"] == "frame-ancestors https://mochipet.example http://localhost:5173"
    assert headers["Cache-Control"] == "no-store"
    assert 'data-aid="ast_1"' in body and 'data-available="true"' in body
    assert 'data-name="Mochi &quot;Pet&quot; &lt;Co.&gt;"' in body  # escaped, never markup
    assert "/assets/widget-abc.js" in body

    body, headers = page.render("ast_x", None)
    assert headers["Content-Security-Policy"] == "frame-ancestors 'none'"
    assert 'data-available="false"' in body and "data-name" not in body
    _, headers = page.render("ast_1", config(published=False))
    assert headers["Content-Security-Policy"] == "frame-ancestors https://mochipet.example"  # shows "not available"


def test_frame_page_needs_a_usable_template() -> None:
    with pytest.raises(UpstreamUnavailable):
        WidgetPage("u", fetch=lambda _: "<html></html>").render("ast_1", config())


def test_customers_see_document_and_page_only() -> None:
    citation = {"n": 1, "chunk_id": "chk_1", "label": "P-14", "document_id": "doc_1", "document_title": "returns.pdf", "page": 3, "para": 2, "boxes": [{"page": 3}], "edited": True}
    events = list(public_events(iter([("token", {"text": "Yes [1]"}), ("citations", {"items": [citation]})])))
    assert events == [("token", {"text": "Yes [1]"}), ("citations", {"items": [{"n": 1, "document_title": "returns.pdf", "page": 3, "para": 2}]})]
