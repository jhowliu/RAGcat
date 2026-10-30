"""Password sign-in through the Cognito API: the adapter's calls and error mapping (botocore
Stubber, no network), then the HTTP flow in Cognito mode with real RSA-signed tokens."""

from __future__ import annotations

from dataclasses import replace
from time import time
from types import SimpleNamespace
from typing import Iterator

import boto3
import jwt
import pytest
from botocore.stub import Stubber
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from ragcat.apps.container import Container, build
from ragcat.apps.dev import create_dev_app
from ragcat.identity.adapters import CognitoPasswordAuth
from ragcat.identity.domain import Tokens
from ragcat.shared.config import get_settings
from ragcat.shared.errors import Conflict, Forbidden, RateLimited, Unauthenticated, UpstreamUnavailable, ValidationError
from ragcat.shared.ids import ulid

POOL, CLIENT = "ap-southeast-2_test", "ragcat-client"
RESULT = {"AuthenticationResult": {"AccessToken": "access", "ExpiresIn": 3600, "IdToken": "id", "RefreshToken": "refresh", "TokenType": "Bearer"}}


@pytest.fixture
def cognito() -> Iterator[tuple[CognitoPasswordAuth, Stubber]]:
    client = boto3.client("cognito-idp", region_name="ap-southeast-2", aws_access_key_id="test", aws_secret_access_key="test")
    settings = replace(get_settings(), auth="cognito", cognito_pool_id=POOL, cognito_client_id=CLIENT)
    with Stubber(client) as stub:
        yield CognitoPasswordAuth(settings, client=client), stub
        stub.assert_no_pending_responses()


def password_auth(email: str = "owner@example.test", password: str = "Secret#123") -> dict:
    return {"ClientId": CLIENT, "AuthFlow": "USER_PASSWORD_AUTH", "AuthParameters": {"USERNAME": email, "PASSWORD": password}}


def test_public_calls_need_no_aws_credentials() -> None:
    from botocore import UNSIGNED

    auth = CognitoPasswordAuth(replace(get_settings(), auth="cognito", cognito_pool_id=POOL, cognito_client_id=CLIENT))
    assert auth.client.meta.config.signature_version is UNSIGNED


def test_sign_up_leaves_the_account_for_the_emailed_code_to_confirm(cognito) -> None:
    auth, stub = cognito
    delivery = {"UserConfirmed": False, "UserSub": "sub", "CodeDeliveryDetails": {"Destination": "o***@e***", "DeliveryMedium": "EMAIL", "AttributeName": "email"}}
    stub.add_response("sign_up", delivery, {"ClientId": CLIENT, "Username": "owner@example.test", "Password": "Secret#123", "UserAttributes": [{"Name": "email", "Value": "owner@example.test"}]})
    auth.sign_up("owner@example.test", "Secret#123")  # no tokens until the email is verified


def test_verify_email_confirms_once_and_tolerates_a_second_try(cognito) -> None:
    auth, stub = cognito
    stub.add_response("confirm_sign_up", {}, {"ClientId": CLIENT, "Username": "owner@example.test", "ConfirmationCode": "123456"})
    auth.verify_email("owner@example.test", "123456")
    stub.add_client_error("confirm_sign_up", "NotAuthorizedException", "User cannot be confirmed. Current status is CONFIRMED")
    auth.verify_email("owner@example.test", "123456")  # a double submit, not an error


def test_resend_code_asks_cognito_for_a_new_code(cognito) -> None:
    auth, stub = cognito
    stub.add_response("resend_confirmation_code", {"CodeDeliveryDetails": {"Destination": "o***@e***"}}, {"ClientId": CLIENT, "Username": "owner@example.test"})
    auth.resend_code("owner@example.test")


def test_password_reset_sends_a_code_then_sets_the_new_password(cognito) -> None:
    auth, stub = cognito
    stub.add_response("forgot_password", {"CodeDeliveryDetails": {"Destination": "o***@e***"}}, {"ClientId": CLIENT, "Username": "owner@example.test"})
    auth.forgot_password("owner@example.test")
    stub.add_response("confirm_forgot_password", {}, {"ClientId": CLIENT, "Username": "owner@example.test", "ConfirmationCode": "654321", "Password": "Newer#456"})
    auth.reset_password("owner@example.test", "654321", "Newer#456")


def test_sign_in_to_an_unverified_account_asks_for_the_code(cognito) -> None:
    auth, stub = cognito
    stub.add_client_error("initiate_auth", "UserNotConfirmedException", "User is not confirmed.", expected_params=password_auth())
    with pytest.raises(Forbidden) as raised:
        auth.sign_in("owner@example.test", "Secret#123")
    assert raised.value.code == "EMAIL_NOT_VERIFIED"


@pytest.mark.parametrize(
    ("operation", "code", "message", "error", "app_code"),
    [
        ("confirm_sign_up", "CodeMismatchException", "Invalid verification code provided", ValidationError, "INVALID_CODE"),
        ("confirm_sign_up", "ExpiredCodeException", "Invalid code provided, please request a code again.", ValidationError, "CODE_EXPIRED"),
        ("confirm_sign_up", "AliasExistsException", "An account with the email already exists.", Conflict, "EMAIL_EXISTS"),
        ("resend_confirmation_code", "InvalidParameterException", "User is already confirmed.", Conflict, "ALREADY_VERIFIED"),
        ("resend_confirmation_code", "LimitExceededException", "Attempt limit exceeded, please try after some time.", RateLimited, "TOO_MANY_ATTEMPTS"),
        ("forgot_password", "InvalidParameterException", "Cannot reset password for the user as there is no registered/verified email or phone_number", Forbidden, "EMAIL_NOT_VERIFIED"),
        ("forgot_password", "CodeDeliveryFailureException", "Unable to deliver message", UpstreamUnavailable, "EMAIL_NOT_SENT"),
        ("confirm_forgot_password", "InvalidPasswordException", "Password does not conform to policy", ValidationError, "INVALID_PASSWORD"),
    ],
)
def test_code_errors_become_codes_the_page_can_explain(cognito, operation, code, message, error, app_code) -> None:
    auth, stub = cognito
    stub.add_client_error(operation, code, message)
    call = {
        "confirm_sign_up": lambda: auth.verify_email("owner@example.test", "000000"),
        "resend_confirmation_code": lambda: auth.resend_code("owner@example.test"),
        "forgot_password": lambda: auth.forgot_password("owner@example.test"),
        "confirm_forgot_password": lambda: auth.reset_password("owner@example.test", "000000", "weak"),
    }[operation]
    with pytest.raises(error) as raised:
        call()
    assert raised.value.code == app_code


@pytest.mark.parametrize(
    ("code", "message", "error", "app_code"),
    [
        ("NotAuthorizedException", "Incorrect username or password.", Unauthenticated, "INVALID_CREDENTIALS"),
        ("NotAuthorizedException", "Password attempts exceeded", RateLimited, "TOO_MANY_ATTEMPTS"),
        ("TooManyRequestsException", "Rate exceeded", RateLimited, "TOO_MANY_ATTEMPTS"),
        ("InvalidParameterException", "USER_PASSWORD_AUTH flow not enabled for this client", UpstreamUnavailable, "UPSTREAM_UNAVAILABLE"),
        ("InternalErrorException", "boom", UpstreamUnavailable, "UPSTREAM_UNAVAILABLE"),
    ],
)
def test_sign_in_errors_become_codes_the_page_can_explain(cognito, code, message, error, app_code) -> None:
    auth, stub = cognito
    stub.add_client_error("initiate_auth", code, message)
    with pytest.raises(error) as raised:
        auth.sign_in("owner@example.test", "wrong")
    assert raised.value.code == app_code


@pytest.mark.parametrize(
    ("code", "error", "app_code"),
    [
        ("UsernameExistsException", Conflict, "EMAIL_EXISTS"),
        ("InvalidPasswordException", ValidationError, "INVALID_PASSWORD"),
        ("InvalidParameterException", ValidationError, "INVALID_INPUT"),
        ("CodeDeliveryFailureException", UpstreamUnavailable, "EMAIL_NOT_SENT"),
    ],
)
def test_sign_up_errors(cognito, code, error, app_code) -> None:
    auth, stub = cognito
    stub.add_client_error("sign_up", code, "rejected")
    with pytest.raises(error) as raised:
        auth.sign_up("owner@example.test", "weak")
    assert raised.value.code == app_code


def test_refresh_keeps_the_refresh_token_and_reports_an_expired_session(cognito) -> None:
    auth, stub = cognito
    refreshed = {"AuthenticationResult": {"AccessToken": "access2", "ExpiresIn": 3600, "IdToken": "id2", "TokenType": "Bearer"}}
    stub.add_response("initiate_auth", refreshed, {"ClientId": CLIENT, "AuthFlow": "REFRESH_TOKEN_AUTH", "AuthParameters": {"REFRESH_TOKEN": "refresh"}})
    assert auth.refresh("refresh") == Tokens("access2", 3600, "id2", None)
    stub.add_client_error("initiate_auth", "NotAuthorizedException", "Refresh Token has been revoked")
    with pytest.raises(Unauthenticated) as raised:
        auth.refresh("refresh")
    assert raised.value.code == "SESSION_EXPIRED"


def test_sign_out_revokes_the_refresh_token_on_a_best_effort_basis(cognito) -> None:
    auth, stub = cognito
    stub.add_response("revoke_token", {}, {"Token": "refresh", "ClientId": CLIENT})
    auth.sign_out("refresh")
    stub.add_client_error("revoke_token", "UnsupportedTokenTypeException", "nope")
    auth.sign_out("refresh")  # does not raise


# ---------------------------------------------------------------- HTTP, Cognito mode


class FakeCognito:
    """Stands in for the Cognito API and issues real RS256 tokens signed with the test key."""

    def __init__(self, issuer: str, key) -> None:
        self.issuer, self.key = issuer, key
        self.accounts: dict[str, str] = {}
        self.codes: dict[str, str] = {}
        self.verified: set[str] = set()
        self.revoked: list[str] = []

    def _token(self, **claims) -> str:
        now = int(time())
        return jwt.encode({"iss": self.issuer, "sub": "owner-sub", "iat": now - 1, "exp": now + 3600, **claims}, self.key, algorithm="RS256")

    def _tokens(self, email: str, refresh: str | None) -> Tokens:
        access = self._token(token_use="access", client_id=CLIENT, username="owner-sub")
        return Tokens(access, 3600, self._token(token_use="id", aud=CLIENT, email=email), refresh)

    def sign_up(self, email: str, password: str) -> None:
        if email in self.accounts:
            raise Conflict("An account with this email already exists.", code="EMAIL_EXISTS")
        self.accounts[email] = password
        self.codes[email] = "123456"

    def verify_email(self, email: str, code: str) -> None:
        if self.codes.get(email) != code:
            raise ValidationError("The code is incorrect.", code="INVALID_CODE")
        self.verified.add(email)

    def resend_code(self, email: str) -> None:
        self.codes[email] = "222222"

    def forgot_password(self, email: str) -> None:
        self.codes[email] = "654321"

    def reset_password(self, email: str, code: str, password: str) -> None:
        if self.codes.get(email) != code:
            raise ValidationError("The code is incorrect.", code="INVALID_CODE")
        self.accounts[email] = password

    def sign_in(self, email: str, password: str) -> Tokens:
        if self.accounts.get(email) != password:
            raise Unauthenticated("Email or password is incorrect.", code="INVALID_CREDENTIALS")
        if email not in self.verified:
            raise Forbidden("Verify your email address first.", code="EMAIL_NOT_VERIFIED")
        return self._tokens(email, "refresh-1")

    def refresh(self, refresh_token: str) -> Tokens:
        if refresh_token in self.revoked:
            raise Unauthenticated("Your session expired. Sign in again.", code="SESSION_EXPIRED")
        return self._tokens("owner@example.test", None)

    def sign_out(self, refresh_token: str) -> None:
        self.revoked.append(refresh_token)


@pytest.fixture
def cognito_app(dynamodb_endpoint) -> Iterator[tuple[TestClient, Container, FakeCognito]]:
    settings = replace(
        get_settings(),
        table_name=f"ragcat-test-{ulid().lower()}",
        dynamodb_endpoint=dynamodb_endpoint,
        storage="local",
        queue="local",
        vectors="local",
        cache="memory",
        auth="cognito",
        cognito_pool_id=POOL,
        cognito_client_id=CLIENT,
    )
    c = build(settings)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    c.verifier._jwks = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key()))
    fake = FakeCognito(c.verifier.issuer, key)
    c.identity.auth = fake
    with TestClient(create_dev_app(c)) as client:
        yield client, c, fake
    c.table.drop()


def test_password_sign_in_flow_in_cognito_mode(cognito_app) -> None:
    client, c, fake = cognito_app
    owner = {"email": " Owner@Example.test ", "password": "Secret#123"}
    signed_up = client.post("/v1/auth/signup", json=owner)
    assert signed_up.status_code == 202 and signed_up.content == b""  # no session before the email is verified
    unverified = client.post("/v1/auth/login", json=owner)
    assert unverified.status_code == 403 and unverified.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    wrong_code = client.post("/v1/auth/verify-email", json={"email": owner["email"], "code": "000000"})
    assert wrong_code.status_code == 400 and wrong_code.json()["error"]["code"] == "INVALID_CODE"
    assert client.post("/v1/auth/verify-email", json={"email": owner["email"], "code": " 123456 "}).status_code == 204

    signed_in = client.post("/v1/auth/login", json=owner)
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.headers["cache-control"] == "no-store"
    session = signed_in.json()
    assert session["token_type"] == "Bearer" and session["refresh_token"] == "refresh-1"
    assert session["user"] == {"name": "owner", "email": "owner@example.test"}  # email normalised; record provisioned from the ID token

    bearer = {"Authorization": f"Bearer {session['access_token']}"}
    assert client.get("/v1/me", headers=bearer).json()["email"] == "owner@example.test"
    assert client.get("/v1/me", headers={"Authorization": "Bearer dev:owner"}).status_code == 401

    again = client.post("/v1/auth/signup", json={"email": "owner@example.test", "password": "Secret#123"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "EMAIL_EXISTS"
    wrong = client.post("/v1/auth/login", json={"email": "owner@example.test", "password": "nope"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"

    assert client.post("/v1/auth/forgot-password", json={"email": "owner@example.test"}).status_code == 202
    reset = client.post("/v1/auth/reset-password", json={"email": "owner@example.test", "code": "654321", "password": "Newer#456"})
    assert reset.status_code == 204
    assert client.post("/v1/auth/login", json={"email": "owner@example.test", "password": "Newer#456"}).json()["user"]["email"] == "owner@example.test"

    refreshed = client.post("/v1/auth/refresh", json={"refresh_token": "refresh-1"})
    assert refreshed.status_code == 200 and "refresh_token" not in refreshed.json()
    assert client.post("/v1/auth/logout", json={"refresh_token": "refresh-1"}).status_code == 204
    expired = client.post("/v1/auth/refresh", json={"refresh_token": "refresh-1"})
    assert expired.status_code == 401 and expired.json()["error"]["code"] == "SESSION_EXPIRED"


def test_password_sign_in_is_off_with_development_tokens(dynamodb_endpoint) -> None:
    settings = replace(get_settings(), table_name=f"ragcat-test-{ulid().lower()}", dynamodb_endpoint=dynamodb_endpoint, storage="local", queue="local", vectors="local", cache="memory", auth="dev")
    c = build(settings)
    with TestClient(create_dev_app(c)) as client:
        assert client.post("/v1/auth/login", json={"email": "owner@example.test", "password": "x"}).status_code == 404
    c.table.drop()
