"""GET /api/auth/me — no backend register/login; Supabase owns identity."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.deps import get_current_user, is_owner
from backend.api.schemas import MeResponse
from backend.database import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    return MeResponse(id=user.id, email=user.email, is_admin=user.is_admin,
                      is_owner=is_owner(user),
                      display_name=user.display_name)
