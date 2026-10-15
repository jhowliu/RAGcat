"""Real RSA JWT verification without network requests or a DynamoDB dependency."""
from dataclasses import replace
from time import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from ragcat.identity.adapters import JwtVerifier
from ragcat.shared.config import get_settings
from ragcat.shared.errors import Unauthenticated


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier(signing_key):
    verifier = JwtVerifier(replace(get_settings(), auth="cognito", cognito_pool_id="ap-southeast-2_test", cognito_client_id="ragcat-client"))
    verifier._jwks = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=signing_key.public_key()))
    return verifier


def token(verifier, signing_key, **changes):
    claims = {"iss": verifier.issuer, "sub": "owner-sub", "iat": int(time()) - 1, "exp": int(time()) + 3600, "token_use": "access", "client_id": "ragcat-client", "username": "mochi"}
    claims.update(changes)
    claims = {key: value for key, value in claims.items() if value is not None}
    return "Bearer " + jwt.encode(claims, signing_key, algorithm="RS256")


def test_cognito_access_token_maps_to_owner(verifier, signing_key):
    principal = verifier.verify(token(verifier, signing_key))
    assert principal.sub == "owner-sub" and principal.name == "mochi"


def test_id_token_checks_its_audience(verifier, signing_key):
    assert verifier.verify(token(verifier, signing_key, token_use="id", aud="ragcat-client", name="Mochi")).name == "Mochi"
    with pytest.raises(Unauthenticated):
        verifier.verify(token(verifier, signing_key, token_use="id", aud="another-client"))


@pytest.mark.parametrize("changes", [
    {"client_id": "another-client"},
    {"client_id": "another-client", "aud": "ragcat-client"},
    {"exp": int(time()) - 60},
    {"exp": None},
    {"sub": None},
    {"iss": "https://attacker.example"},
    {"token_use": "refresh"},
])
def test_invalid_cognito_tokens_are_rejected(verifier, signing_key, changes):
    with pytest.raises(Unauthenticated):
        verifier.verify(token(verifier, signing_key, **changes))


def test_cognito_mode_does_not_accept_dev_tokens(verifier):
    with pytest.raises(Unauthenticated):
        verifier.verify("Bearer dev:tester")


def test_wrong_signature_is_rejected(verifier, signing_key):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(Unauthenticated):
        verifier.verify(token(verifier, other_key))
