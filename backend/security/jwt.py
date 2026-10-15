"""
JWT authentication against Supabase Auth.

Supabase issues ES256/HS256... in practice Supabase Auth signs access tokens
with HS256 (SUPABASE_JWT_SECRET) on older projects or RS256/ES256 with a
published JWKS document on newer ones. This module supports all three:

1. If SUPABASE_JWT_SECRET is set -> verify with HS256 against the secret.
2. Otherwise -> fetch the JWKS document from
   {SUPABASE_URL}/auth/v1/.well-known/jwks.json (cached in-memory) and
   verify RS256 or ES256 signatures. NOTE: newer Supabase projects sign
   with ES256 (EC P-256) — allowing RS256 only rejects every real user
   token, which the frontend turns into an infinite login<->dashboard
   reload loop (401 -> /login -> /dashboard -> 401 ...).

Design is import-safe: without PyJWT installed, verify_jwt raises
AuthUnavailableError instead of crashing at import time.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

try:  # optional dependency
    import jwt as _pyjwt
    from jwt import PyJWKClient
    _PYJWT_AVAILABLE = True
except Exception:  # pragma: no cover - defensive
    _pyjwt = None  # type: ignore
    PyJWKClient = None  # type: ignore
    _PYJWT_AVAILABLE = False

try:
    import httpx as _httpx
    _HTTPX_AVAILABLE = True
except Exception:  # pragma: no cover
    _httpx = None
    _HTTPX_AVAILABLE = False


class AuthError(Exception):
    """Base auth failure."""


class AuthUnavailableError(AuthError):
    """Auth backend cannot run (missing dependency or configuration)."""


class InvalidTokenError(AuthError):
    """Token failed verification."""


@dataclass
class AuthUser:
    id: str
    email: str | None
    role: str
    is_admin: bool


_JWKS_CACHE: dict = {"client": None, "url": None, "fetched_at": 0.0}
_JWKS_TTL = 3600.0


def _get_jwk_client(supabase_url: str):
    global _JWKS_CACHE
    jwks_url = supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    cached = _JWKS_CACHE
    if cached["client"] is not None and cached["url"] == jwks_url \
            and time.time() - cached["fetched_at"] < _JWKS_TTL:
        return cached["client"]
    client = PyJWKClient(jwks_url)
    _JWKS_CACHE = {"client": client, "url": jwks_url, "fetched_at": time.time()}
    return client


def verify_jwt(token: str, *, supabase_url: str = "", jwt_secret: str = "") -> AuthUser:
    """
    Verify a Supabase access token and return the authenticated user.

    Raises AuthUnavailableError if verification cannot run, InvalidTokenError
    if the token is bad.
    """
    if not token:
        raise InvalidTokenError("Missing bearer token")
    if not _PYJWT_AVAILABLE:
        raise AuthUnavailableError("PyJWT is not installed; cannot verify tokens")

    claims: dict
    try:
        if jwt_secret:
            claims = _pyjwt.decode(token, jwt_secret, algorithms=["HS256"],
                                   options={"verify_aud": False})
        else:
            if not supabase_url:
                raise AuthUnavailableError(
                    "No SUPABASE_URL (JWKS) or SUPABASE_JWT_SECRET configured")
            if not _HTTPX_AVAILABLE:
                raise AuthUnavailableError("httpx is not installed; cannot fetch JWKS")
            signing_key = _get_jwk_client(supabase_url).get_signing_key_from_jwt(token)
            claims = _pyjwt.decode(token, signing_key.key,
                                   algorithms=["RS256", "ES256"],
                                   options={"verify_aud": False})
    except AuthError:
        raise
    except _pyjwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("Token expired") from exc
    except _pyjwt.InvalidTokenError as exc:
        raise InvalidTokenError(f"Invalid token: {exc}") from exc
    except Exception as exc:  # network / JWKS fetch failures
        raise AuthUnavailableError(f"Token verification unavailable: {exc}") from exc

    user_id = claims.get("sub") or ""
    if not user_id:
        raise InvalidTokenError("Token has no subject")
    role = claims.get("role", "authenticated")
    app_meta = claims.get("app_metadata") or {}
    is_admin = bool(app_meta.get("is_admin")) or role in {"service_role", "admin"}
    return AuthUser(
        id=user_id,
        email=claims.get("email"),
        role=role,
        is_admin=is_admin,
    )
