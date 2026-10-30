"""Identity & Usage application service."""

from __future__ import annotations

from typing import Callable

from ragcat.identity.adapters import CognitoPasswordAuth, DynamoIdentityRepo, JwtVerifier
from ragcat.identity.domain import DEFAULT_PLAN, Principal, Tokens, Usage, User, current_period
from ragcat.shared.errors import NotFound, QuotaExceeded
from ragcat.shared.kernel import now_iso


class IdentityService:
    def __init__(
        self,
        repo: DynamoIdentityRepo,
        clock: Callable[[], str] = now_iso,
        *,
        auth: CognitoPasswordAuth | None = None,
        verifier: JwtVerifier | None = None,
    ) -> None:
        self.repo = repo
        self.now = clock
        self.auth = auth  # None with development tokens
        self.verifier = verifier
        self._known: set[str] = set()

    def ensure(self, principal: Principal) -> None:
        """JIT provisioning: first request from a new owner creates their record."""
        if principal.sub in self._known:
            return
        self.repo.ensure_user(User(principal.sub, principal.email, principal.name, DEFAULT_PLAN, self.now()))
        self._known.add(principal.sub)

    def me(self, sub: str) -> tuple[User, Usage]:
        user = self.repo.get_user(sub)
        if user is None:
            raise NotFound("User not found")
        return user, self.repo.get_usage(sub, current_period())

    def rename(self, sub: str, name: str) -> None:
        self.repo.update_user(sub, {"name": name.strip()[:80]})

    def pages_available(self, sub: str, pages: int) -> bool:
        user, usage = self.me(sub)
        return usage.pages_read + pages <= user.limits["pages_limit"]

    def add_pages(self, sub: str, pages: int) -> None:
        if pages:
            self.repo.add_usage(sub, current_period(), "pages_read", pages)

    def check_answers(self, sub: str) -> None:
        user, usage = self.me(sub)
        if usage.answers >= user.limits["answers_limit"]:
            raise QuotaExceeded("This Assistant has used all answers for this month")

    def add_answer(self, sub: str) -> None:
        self.repo.add_usage(sub, current_period(), "answers", 1)

    # ------------------------------------------------------------ password sign-in (Cognito)

    def sign_up(self, email: str, password: str) -> None:
        """The owner signs in once the emailed code has verified the address."""
        self._password_auth().sign_up(_email(email), password)

    def verify_email(self, email: str, code: str) -> None:
        self._password_auth().verify_email(_email(email), code.strip())

    def resend_code(self, email: str) -> None:
        self._password_auth().resend_code(_email(email))

    def forgot_password(self, email: str) -> None:
        self._password_auth().forgot_password(_email(email))

    def reset_password(self, email: str, code: str, password: str) -> None:
        self._password_auth().reset_password(_email(email), code.strip(), password)

    def sign_in(self, email: str, password: str) -> tuple[Tokens, User]:
        tokens = self._password_auth().sign_in(_email(email), password)
        return tokens, self._provision(tokens)

    def refresh(self, refresh_token: str) -> Tokens:
        return self._password_auth().refresh(refresh_token)

    def sign_out(self, refresh_token: str) -> None:
        self._password_auth().sign_out(refresh_token)

    def _password_auth(self) -> CognitoPasswordAuth:
        if self.auth is None:
            raise NotFound("Password sign-in is off: this server accepts development tokens")
        return self.auth

    def _provision(self, tokens: Tokens) -> User:
        """The verified ID token carries the email the access token lacks, so the owner's record
        starts complete."""
        assert self.verifier is not None, "password sign-in needs the JWT verifier"
        principal = self.verifier.verify(f"Bearer {tokens.id_token}")
        self.ensure(principal)
        return self.me(principal.sub)[0]


def _email(value: str) -> str:
    return value.strip().lower()
