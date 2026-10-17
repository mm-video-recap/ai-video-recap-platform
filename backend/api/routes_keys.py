"""POST /api/keys/verify — check a user-typed Gemini/Groq key without
saving it.

The key travels in the JSON BODY (never a query param, never logged)
and is used once for a cheap read-only probe against the provider
(Gemini: list models; Groq: list models). The response carries only
valid + a reason code — the key itself is never echoed back.
"""
from __future__ import annotations

import logging
from typing import Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.api.deps import get_current_user
from backend.database import User

log = logging.getLogger("api.keys")

router = APIRouter(prefix="/api/keys", tags=["keys"])


class VerifyRequest(BaseModel):
    provider: Literal["gemini", "groq"]
    key: str = Field(min_length=1)


class VerifyResponse(BaseModel):
    valid: bool
    # ok | invalid | quota | error
    reason: str


def _verify_gemini_key(key: str) -> tuple[bool, str]:
    try:
        r = httpx.Client(timeout=10).get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": key})
    except httpx.HTTPError as exc:
        log.warning("gemini key verify network error: %s", type(exc).__name__)
        return False, "error"
    if r.status_code == 200:
        return True, "ok"
    if r.status_code == 429:
        # Key is real — the quota pool is exhausted.
        return True, "quota"
    if r.status_code in (400, 401, 403):
        return False, "invalid"
    return False, "error"


def _verify_groq_key(key: str) -> tuple[bool, str]:
    try:
        r = httpx.Client(timeout=10).get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as exc:
        log.warning("groq key verify network error: %s", type(exc).__name__)
        return False, "error"
    if r.status_code == 200:
        return True, "ok"
    if r.status_code == 429:
        return True, "quota"
    if r.status_code in (401, 403):
        return False, "invalid"
    return False, "error"


@router.post("/verify", response_model=VerifyResponse)
def verify_key(body: VerifyRequest, user: User = Depends(get_current_user)):
    # The key is used once for the probe and discarded — never logged,
    # never stored. (get_current_user already enforced login.)
    if body.provider == "gemini":
        valid, reason = _verify_gemini_key(body.key)
    else:
        valid, reason = _verify_groq_key(body.key)
    log.info("key verify provider=%s user=%s valid=%s reason=%s",
             body.provider, user.id, valid, reason)
    return VerifyResponse(valid=valid, reason=reason)
