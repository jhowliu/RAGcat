"""Identity & Usage domain: owners, their plan, and monthly usage meters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

PLANS = {
    "growth": {"pages_limit": 2000, "answers_limit": 5000, "assistants_limit": 10},
}
DEFAULT_PLAN = "growth"


@dataclass(frozen=True)
class Principal:
    """A verified caller identity. Produced by the JwtVerifier anti-corruption layer."""

    sub: str
    email: str
    name: str


@dataclass(frozen=True)
class Tokens:
    """What a password sign-in or a refresh returns. A refresh keeps the existing refresh token."""

    access_token: str
    expires_in: int
    id_token: str | None = None
    refresh_token: str | None = None


@dataclass
class User:
    id: str
    email: str
    name: str
    plan: str
    created_at: str

    @property
    def limits(self) -> dict[str, int]:
        return PLANS.get(self.plan, PLANS[DEFAULT_PLAN])


@dataclass
class Usage:
    period_start: str
    pages_read: int = 0
    answers: int = 0


def current_period(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}-01"
