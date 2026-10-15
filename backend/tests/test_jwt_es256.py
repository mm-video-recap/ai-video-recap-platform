"""Regression tests: Supabase ES256 (ECDSA) token verification.

Live incident 2026-10-16: the Supabase project signs access tokens with
ES256 (its JWKS has a single EC P-256 key), but verify_jwt's JWKS path
allowed RS256 only. Every real user token failed verification -> the API
answered 401 -> the frontend hard-redirected to /login -> the login page
saw a valid Supabase session and bounced back to /dashboard -> 401 again:
an infinite reload/flicker loop. The fix allows RS256 + ES256 and adds
the `cryptography` dependency PyJWT needs for ECDSA.
"""

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

from backend.security import jwt as jwt_mod
from backend.security.jwt import InvalidTokenError, verify_jwt


def _ec_keypair():
    private = ec.generate_private_key(ec.SECP256R1())
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return private_pem, public_pem


def _sign_es256(private_pem, claims):
    return pyjwt.encode(claims, private_pem, algorithm="ES256")


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    def __init__(self, key):
        self._key = key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._key)


@pytest.fixture()
def _fake_jwks(monkeypatch):
    """Route the JWKS lookup at a caller-supplied public key (PEM)."""

    def _install(public_pem):
        monkeypatch.setattr(
            jwt_mod, "_get_jwk_client",
            lambda url: _FakeJWKClient(public_pem),
        )

    return _install


def test_verify_es256_token(_fake_jwks):
    private_pem, public_pem = _ec_keypair()
    _fake_jwks(public_pem)
    token = _sign_es256(private_pem, {
        "sub": "user-123",
        "email": "user@example.com",
        "role": "authenticated",
    })
    user = verify_jwt(token, supabase_url="https://example.supabase.co",
                      jwt_secret="")
    assert user.id == "user-123"
    assert user.email == "user@example.com"


def test_verify_es256_wrong_key_rejected(_fake_jwks):
    private_pem, _ = _ec_keypair()
    _other_private, other_public = _ec_keypair()
    _fake_jwks(other_public)
    token = _sign_es256(private_pem, {
        "sub": "user-123",
        "email": "user@example.com",
        "role": "authenticated",
    })
    with pytest.raises(InvalidTokenError):
        verify_jwt(token, supabase_url="https://example.supabase.co",
                   jwt_secret="")


def test_verify_rs256_still_allowed(monkeypatch):
    """The ES256 fix must not drop RS256 support (older Supabase projects)."""
    import json

    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    monkeypatch.setattr(
        jwt_mod, "_get_jwk_client",
        lambda url: _FakeJWKClient(public_pem),
    )
    token = pyjwt.encode(
        {"sub": "user-456", "email": "rsa@example.com",
         "role": "authenticated"},
        private_pem, algorithm="RS256",
        headers={"kid": "test-rsa-key"},
    )
    # Sanity: the token really is RS256-signed.
    assert json.loads(
        pyjwt.utils.base64url_decode(token.split(".")[0] + "==").decode()
    )["alg"] == "RS256"
    user = verify_jwt(token, supabase_url="https://example.supabase.co",
                      jwt_secret="")
    assert user.id == "user-456"
