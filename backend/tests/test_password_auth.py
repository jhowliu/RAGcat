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
from ragcat.shared.errors import Conflict, RateLimited, Unauthenticated, UpstreamUnavailable, ValidationError
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


def confirms(stub: Stubber, email: str = "owner@example.test") -> None:
    stub.add_response("admin_confirm_sign_up", {}, {"UserPoolId": POOL, "Username": email})
    stub.add_response("admin_update_user_attributes", {}, {"UserPoolId": POOL, "Username": email, "UserAttributes": [{"Name": "email_verified", "Value": "true"}]})


def test_public_calls_need_no_aws_credentials() -> None:
    from botocore import UNSIGNED

    auth = CognitoPasswordAuth(replace(get_settings(), auth="cognito", cognito_pool_id=POOL, cognito_client_id=CLIENT))
    assert auth.client.meta.config.signature_version is UNSIGNED
    assert auth.admin is not auth.client and auth.admin.meta.config.signature_version is not UNSIGNED


def creates(stub: Stubber, email: str = "owner@example.test") -> None:
    stub.add_response("admin_create_user", {"User": {"Username": "sub"}}, {
        "UserPoolId": POOL, "Username": email, "MessageAction": "SUPPRESS",
        "UserAttributes": [{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": "true"}],
    })


def test_sign_up_creates_a_confirmed_account_without_any_email_then_signs_in(cognito) -> None:
    auth, stub = cognito
    creates(stub)
    stub.add_response("admin_set_user_password", {}, {"UserPoolId": POOL, "Username": "owner@example.test", "Password": "Secret#123", "Permanent": True})
    stub.add_response("initiate_auth", RESULT, password_auth())
    assert auth.sign_up("owner@example.test", "Secret#123") == Tokens("access", 3600, "id", "refresh")


def test_a_rejected_password_removes_the_half_created_account(cognito) -> None:
    auth, stub = cognito
    creates(stub)
    stub.add_client_error("admin_set_user_password", "InvalidPasswordException", "Password does not conform to policy")
    stub.add_response("admin_delete_user", {}, {"UserPoolId": POOL, "Username": "owner@example.test"})
    with pytest.raises(ValidationError) as raised:
        auth.sign_up("owner@example.test", "weak")
    assert raised.value.code == "INVALID_PASSWORD"


def test_sign_in_finishes_a_sign_up_that_stopped_before_confirming(cognito) -> None:
    auth, stub = cognito
    stub.add_client_error("initiate_auth", "UserNotConfirmedException", "User is not confirmed.", expected_params=password_auth())
    confirms(stub)
    stub.add_response("initiate_auth", RESULT, password_auth())
    assert auth.sign_in("owner@example.test", "Secret#123").access_token == "access"


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
    [("UsernameExistsException", Conflict, "EMAIL_EXISTS"), ("InvalidParameterException", ValidationError, "INVALID_INPUT"), ("AccessDeniedException", UpstreamUnavailable, "UPSTREAM_UNAVAILABLE")],
)
def test_sign_up_errors(cognito, code, error, app_code) -> None:
    auth, stub = cognito
    stub.add_client_error("admin_create_user", code, "rejected")
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
        self.revoked: list[str] = []

    def _token(self, **claims) -> str:
        now = int(time())
        return jwt.encode({"iss": self.issuer, "sub": "owner-sub", "iat": now - 1, "exp": now + 3600, **claims}, self.key, algorithm="RS256")

    def _tokens(self, email: str, refresh: str | None) -> Tokens:
        access = self._token(token_use="access", client_id=CLIENT, username="owner-sub")
        return Tokens(access, 3600, self._token(token_use="id", aud=CLIENT, email=email), refresh)

    def sign_up(self, email: str, password: str) -> Tokens:
        if email in self.accounts:
            raise Conflict("An account with this email already exists.", code="EMAIL_EXISTS")
        self.accounts[email] = password
        return self.sign_in(email, password)

    def sign_in(self, email: str, password: str) -> Tokens:
        if self.accounts.get(email) != password:
            raise Unauthenticated("Email or password is incorrect.", code="INVALID_CREDENTIALS")
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
    signed_up = client.post("/v1/auth/signup", json={"email": " Owner@Example.test ", "password": "Secret#123"})
    assert signed_up.status_code == 201, signed_up.text
    assert signed_up.headers["cache-control"] == "no-store"
    session = signed_up.json()
    assert session["token_type"] == "Bearer" and session["refresh_token"] == "refresh-1"
    assert session["user"] == {"name": "owner", "email": "owner@example.test"}  # email normalised; record provisioned from the ID token

    bearer = {"Authorization": f"Bearer {session['access_token']}"}
    assert client.get("/v1/me", headers=bearer).json()["email"] == "owner@example.test"
    assert client.get("/v1/me", headers={"Authorization": "Bearer dev:owner"}).status_code == 401

    again = client.post("/v1/auth/signup", json={"email": "owner@example.test", "password": "Secret#123"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "EMAIL_EXISTS"
    wrong = client.post("/v1/auth/login", json={"email": "owner@example.test", "password": "nope"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert client.post("/v1/auth/login", json={"email": "owner@example.test", "password": "Secret#123"}).json()["user"]["email"] == "owner@example.test"

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
