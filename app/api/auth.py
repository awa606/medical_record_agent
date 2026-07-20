from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.db import (
    create_auth_session,
    create_user,
    get_auth_session_user,
    get_user_by_username,
    list_users,
    revoke_auth_session,
    update_user_last_login,
)
from app.schemas.auth import (
    AuthenticatedUser,
    CreateUserRequest,
    LoginRequest,
    LoginResponse,
    UserListResponse,
    UserPublic,
)
from app.services.auth import hash_session_token, new_session_token, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_COOKIE_NAME = "medical_record_agent_session"
DEFAULT_SESSION_HOURS = 8


def _cookie_secure() -> bool:
    return os.environ.get("MEDICAL_RECORD_AGENT_COOKIE_SECURE", "").lower() in {"1", "true", "yes"}


def _session_hours() -> int:
    raw = os.environ.get("MEDICAL_RECORD_AGENT_SESSION_HOURS")
    if not raw:
        return DEFAULT_SESSION_HOURS
    try:
        return max(1, min(int(raw), 72))
    except ValueError:
        return DEFAULT_SESSION_HOURS


def _session_cookie(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        return token
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def _public_user(row: dict[str, Any]) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=int(row["id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"]),
        role=row["role"],
        is_active=bool(row["is_active"]),
    )


def require_current_user(request: Request) -> AuthenticatedUser:
    token = _session_cookie(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    row = get_auth_session_user(hash_session_token(token))
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    user = _public_user(row)
    request.state.current_user = user
    return user


def require_admin(user: AuthenticatedUser = Depends(require_current_user)) -> AuthenticatedUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


def current_user_from_request(request: Request | None) -> AuthenticatedUser | None:
    if request is None:
        return None
    user = getattr(request.state, "current_user", None)
    if isinstance(user, AuthenticatedUser):
        return user
    return None


def assert_owner_or_admin(
    owner_user_id: int | None,
    request: Request | None,
    *,
    resource_name: str = "resource",
) -> None:
    if owner_user_id is None:
        return
    user = current_user_from_request(request)
    if user is None:
        return
    if user.role == "admin" or user.id == int(owner_user_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"You are not allowed to access this {resource_name}",
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response) -> LoginResponse:
    row = get_user_by_username(payload.username)
    if row is None or not bool(row["is_active"]) or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = new_session_token()
    expires_at = datetime.now(UTC) + timedelta(hours=_session_hours())
    create_auth_session(
        user_id=int(row["id"]),
        token_hash=hash_session_token(token),
        expires_at=expires_at.isoformat(),
    )
    update_user_last_login(int(row["id"]))
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        max_age=_session_hours() * 3600,
        expires=_session_hours() * 3600,
        path="/",
    )
    row = get_user_by_username(payload.username) or row
    return LoginResponse(user=_public_user(row), session_expires_at=expires_at.isoformat())


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    token = _session_cookie(request)
    if token:
        revoke_auth_session(hash_session_token(token))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"status": "logged_out"}


@router.get("/me", response_model=AuthenticatedUser)
def read_me(user: AuthenticatedUser = Depends(require_current_user)) -> AuthenticatedUser:
    return user


@router.get("/users", response_model=UserListResponse)
def read_users(_admin: AuthenticatedUser = Depends(require_admin)) -> UserListResponse:
    return UserListResponse(users=[UserPublic.model_validate(row) for row in list_users()])


@router.post("/users", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def create_user_route(
    payload: CreateUserRequest,
    _admin: AuthenticatedUser = Depends(require_admin),
) -> UserPublic:
    try:
        user_id = create_user(
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = next(row for row in list_users() if int(row["id"]) == user_id)
    return UserPublic.model_validate(row)
