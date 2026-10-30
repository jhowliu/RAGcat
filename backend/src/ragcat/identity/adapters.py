"""Identity adapters: DynamoDB repository, password sign-in through the Cognito API, and the JWT
anti-corruption layer over Cognito."""

from __future__ import annotations

import logging
from typing import Any

import boto3
import jwt
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from jwt import PyJWKClient

from ragcat.identity.domain import Principal, Tokens, Usage, User
from ragcat.infra.dynamo import Table, plain
from ragcat.shared.config import Settings
from ragcat.shared.errors import AppError, Conflict, Forbidden, RateLimited, Unauthenticated, UpstreamUnavailable, ValidationError

log = logging.getLogger("ragcat.identity")


class DynamoIdentityRepo:
    def __init__(self, table: Table) -> None:
        self.table = table

    def ensure_user(self, user: User) -> None:
        self.table.put(
            {"PK": f"USER#{user.id}", "SK": "PROFILE", "type": "user", "id": user.id, "email": user.email, "name": user.name, "plan": user.plan, "created_at": user.created_at},
            condition="attribute_not_exists(PK)",
        )

    def get_user(self, sub: str) -> User | None:
        item = self.table.get(f"USER#{sub}", "PROFILE")
        if not item:
            return None
        return User(item["id"], item.get("email", ""), item.get("name", ""), item.get("plan", "growth"), item.get("created_at", ""))

    def update_user(self, sub: str, fields: dict[str, Any]) -> None:
        self.table.update(f"USER#{sub}", "PROFILE", set_fields=fields)

    def get_usage(self, sub: str, period: str) -> Usage:
        item = self.table.get(f"USER#{sub}", f"USAGE#{period}") or {}
        return Usage(period, plain(item.get("pages_read", 0)), plain(item.get("answers", 0)))

    def add_usage(self, sub: str, period: str, field: str, amount: int) -> None:
        self.table.update(f"USER#{sub}", f"USAGE#{period}", set_fields={"type": "usage"}, add_fields={field: amount})


class CognitoPasswordAuth:
    """Email and password accounts for RAGcat's own sign-in page, all through Cognito's public API:
    unsigned, so the api needs no AWS credentials or IAM grants for them. Sign-up and password reset
    email the owner a code; the user pool's email settings decide the sender and the daily limit."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.client_id = settings.cognito_client_id
        self.client = client or boto3.client("cognito-idp", region_name=settings.region, config=Config(signature_version=UNSIGNED))

    def sign_up(self, email: str, password: str) -> None:
        """Creates an unconfirmed account; Cognito emails the code that confirms it."""
        self._call("sign_up", Username=email, Password=password, UserAttributes=[{"Name": "email", "Value": email}])

    def verify_email(self, email: str, code: str) -> None:
        try:
            self.client.confirm_sign_up(ClientId=self.client_id, Username=email, ConfirmationCode=code)
        except ClientError as exc:
            if not (_code(exc) == "NotAuthorizedException" and "CONFIRMED" in _message(exc)):  # already confirmed
                raise _auth_error(exc) from exc
        except BotoCoreError as exc:
            raise _auth_error(exc) from exc

    def resend_code(self, email: str) -> None:
        self._call("resend_confirmation_code", Username=email)

    def forgot_password(self, email: str) -> None:
        """Emails a reset code. With the app client's user-existence errors off, an unknown email
        looks the same as a known one."""
        self._call("forgot_password", Username=email)

    def reset_password(self, email: str, code: str, password: str) -> None:
        self._call("confirm_forgot_password", Username=email, ConfirmationCode=code, Password=password)

    def sign_in(self, email: str, password: str) -> Tokens:
        try:
            return self._password(email, password)
        except (ClientError, BotoCoreError) as exc:
            raise _auth_error(exc) from exc

    def refresh(self, refresh_token: str) -> Tokens:
        try:
            response = self.client.initiate_auth(ClientId=self.client_id, AuthFlow="REFRESH_TOKEN_AUTH", AuthParameters={"REFRESH_TOKEN": refresh_token})
        except (ClientError, BotoCoreError) as exc:
            raise _auth_error(exc, refreshing=True) from exc
        return _tokens(response)

    def sign_out(self, refresh_token: str) -> None:
        """Revoke the refresh token and the tokens it issued. Best effort: the browser has already
        forgotten them."""
        try:
            self.client.revoke_token(Token=refresh_token, ClientId=self.client_id)
        except (ClientError, BotoCoreError) as exc:
            log.warning("Refresh token revocation failed: %s", _code(exc) or type(exc).__name__)

    def _password(self, email: str, password: str) -> Tokens:
        response = self.client.initiate_auth(ClientId=self.client_id, AuthFlow="USER_PASSWORD_AUTH", AuthParameters={"USERNAME": email, "PASSWORD": password})
        return _tokens(response)

    def _call(self, operation: str, **params: Any) -> None:
        try:
            getattr(self.client, operation)(ClientId=self.client_id, **params)
        except (ClientError, BotoCoreError) as exc:
            raise _auth_error(exc) from exc


def _code(exc: Exception) -> str:
    return exc.response.get("Error", {}).get("Code", "") if isinstance(exc, ClientError) else ""


def _message(exc: Exception) -> str:
    return exc.response.get("Error", {}).get("Message", "") if isinstance(exc, ClientError) else str(exc)


def _tokens(response: dict[str, Any]) -> Tokens:
    result = response.get("AuthenticationResult")
    if not result:  # a challenge such as NEW_PASSWORD_REQUIRED, which RAGcat's sign-in page does not offer
        raise Unauthenticated("This account needs a step RAGcat's sign-in page does not support.", code="AUTH_CHALLENGE")
    return Tokens(result["AccessToken"], int(result["ExpiresIn"]), result.get("IdToken"), result.get("RefreshToken"))


def _auth_error(exc: Exception, *, refreshing: bool = False) -> AppError:
    """Cognito errors as API errors whose code the sign-in page turns into a message."""
    code, message = _code(exc), _message(exc)
    if "flow not enabled" in message:  # the app client is misconfigured, not the owner's input
        log.error("Cognito app client rejects the sign-in flow: %s", message)
        return UpstreamUnavailable("Sign-in is unavailable. Try again shortly.")
    if code in ("TooManyRequestsException", "LimitExceededException", "TooManyFailedAttemptsException") or "attempts exceeded" in message:
        return RateLimited("Too many attempts. Wait a few minutes and try again.", code="TOO_MANY_ATTEMPTS")
    if code in ("NotAuthorizedException", "UserNotFoundException"):
        if refreshing:
            return Unauthenticated("Your session expired. Sign in again.", code="SESSION_EXPIRED")
        return Unauthenticated("Email or password is incorrect.", code="INVALID_CREDENTIALS")
    # Only a right password reaches this, so it reveals nothing a wrong one wouldn't.
    if code == "UserNotConfirmedException":
        return Forbidden("Verify your email address first.", code="EMAIL_NOT_VERIFIED")
    if code in ("UsernameExistsException", "AliasExistsException"):
        return Conflict("An account with this email already exists.", code="EMAIL_EXISTS")
    if code == "InvalidPasswordException":
        return ValidationError("The password does not meet the requirements.", code="INVALID_PASSWORD")
    if code == "CodeMismatchException":
        return ValidationError("The code is incorrect.", code="INVALID_CODE")
    if code == "ExpiredCodeException":
        return ValidationError("The code has expired. Ask for a new one.", code="CODE_EXPIRED")
    if code == "CodeDeliveryFailureException":
        return UpstreamUnavailable("The email could not be sent. Try again shortly.", code="EMAIL_NOT_SENT")
    if code == "InvalidParameterException" and "already confirmed" in message:  # resending to a verified account
        return Conflict("This email is already verified. Sign in.", code="ALREADY_VERIFIED")
    if code == "InvalidParameterException" and "no registered/verified email" in message:  # resetting an unverified account
        return Forbidden("Verify your email address first.", code="EMAIL_NOT_VERIFIED")
    if code == "InvalidParameterException":
        return ValidationError("Check the email address and password.", code="INVALID_INPUT")
    log.warning("Cognito call failed: %s %s", code or type(exc).__name__, message)
    return UpstreamUnavailable("Sign-in is unavailable. Try again shortly.")


class JwtVerifier:
    """Turns a bearer token into a Principal. Other contexts only ever see Principal / owner id."""

    def __init__(self, settings: Settings) -> None:
        self.mode = settings.auth
        self.client_id = settings.cognito_client_id
        self.issuer = f"https://cognito-idp.{settings.region}.amazonaws.com/{settings.cognito_pool_id}"
        self._jwks: PyJWKClient | None = None

    def verify(self, authorization: str | None) -> Principal:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise Unauthenticated("Sign in to continue")
        token = authorization[7:].strip()
        if self.mode == "dev":
            if not token.startswith("dev:") or len(token) < 5:
                raise Unauthenticated("Development tokens look like 'dev:<name>'")
            name = token[4:][:40]
            return Principal(sub=f"dev-{name}", email=f"{name}@example.dev", name=name)
        return self._verify_cognito(token)

    def _verify_cognito(self, token: str) -> Principal:
        if self._jwks is None:
            self._jwks = PyJWKClient(f"{self.issuer}/.well-known/jwks.json", timeout=5)
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], issuer=self.issuer, options={"verify_aud": False, "require": ["exp", "iat", "sub", "token_use"]})
        except Exception as exc:  # PyJWT raises several version-specific exceptions
            raise Unauthenticated("Invalid or expired token") from exc
        token_use = claims.get("token_use")
        audience = claims.get("client_id") if token_use == "access" else claims.get("aud")
        if audience != self.client_id or token_use not in ("id", "access"):
            raise Unauthenticated("Token was not issued for this app")
        return Principal(
            sub=claims["sub"],
            email=claims.get("email", ""),
            name=claims.get("name") or claims.get("given_name") or claims.get("username") or claims.get("email", "").split("@")[0],
        )
