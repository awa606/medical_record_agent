from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.db import (
    append_audit_event,
    clear_login_failures,
    count_active_admins,
    create_auth_session,
    create_user,
    get_auth_session_user,
    get_user_by_id,
    get_user_by_username,
    list_users,
    login_lock_state,
    register_login_failure,
    revoke_auth_session,
    revoke_user_sessions,
    update_user_admin,
    update_user_last_login,
)
from app.schemas.auth import (
    AuthenticatedUser,
    CreateUserRequest,
    LoginRequest,
    LoginResponse,
    UpdateUserRequest,
    UserListResponse,
    UserPublic,
)
from app.services.auth import hash_password, hash_session_token, new_session_token, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_COOKIE_NAME = os.environ.get("MEDICAL_RECORD_AGENT_SESSION_COOKIE_NAME", "medical_record_agent_session")
if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", SESSION_COOKIE_NAME):
    raise ValueError("Invalid MEDICAL_RECORD_AGENT_SESSION_COOKIE_NAME")
DEFAULT_SESSION_HOURS = 8
# Unknown usernames still pay one PBKDF2 verification so latency does not
# reveal whether the account exists.
_TIMING_EQUALIZER_HASH = hash_password("mra-login-timing-equalizer")


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
    try:
        department_id = row["department_id"]
    except (KeyError, IndexError):
        department_id = None
    return AuthenticatedUser(
        id=int(row["id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"]),
        role=row["role"],
        department_id=department_id,
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
    """Fail closed at the HTTP boundary.

    FastAPI always injects a ``Request`` for an HTTP call, so a request that
    carries no authenticated user is a 401 instead of a silent allow. ``None``
    only happens when a handler is invoked directly (tests, maintenance jobs),
    where there is no HTTP boundary to guard.
    """
    if request is None:
        return
    user = current_user_from_request(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if owner_user_id is None:
        if user.role == "admin":
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You are not allowed to access this {resource_name}",
        )
    if user.role == "admin" or user.id == int(owner_user_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"You are not allowed to access this {resource_name}",
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, request: Request) -> LoginResponse:
    client_ip = request.client.host if request.client is not None else "unknown"
    lock = login_lock_state(payload.username, client_ip)

    row = get_user_by_username(payload.username)
    if row is None:
        # Burn the same PBKDF2 cost as a real check: no username oracle by latency.
        verify_password(payload.password, _TIMING_EQUALIZER_HASH)
        password_ok = False
    else:
        password_ok = verify_password(payload.password, row["password_hash"])
    valid = row is not None and bool(row["is_active"]) and password_ok

    if lock is not None and not valid:
        # Rate-limit guessing; a correct password still works so an attacker
        # cannot lock a doctor out of their own account.
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "Too many failed login attempts. Try again later.",
                "retry_after": lock["retry_after"],
            },
            headers={"Retry-After": str(lock["retry_after"])},
        )
    if not valid:
        failure = register_login_failure(payload.username, client_ip)
        if failure["locked"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": "Too many failed login attempts. Try again later.",
                    "retry_after": failure["retry_after"],
                },
                headers={"Retry-After": str(failure["retry_after"])},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Invalid username or password",
                "remaining_attempts": failure["remaining"],
            },
        )

    clear_login_failures(payload.username, client_ip)
    token = new_session_token()
    expires_at = datetime.now(UTC) + timedelta(hours=_session_hours())
    create_auth_session(
        user_id=int(row["id"]),
        token_hash=hash_session_token(token),
        expires_at=expires_at.isoformat(),
    )
    update_user_last_login(int(row["id"]))
    try:
        department_id = row["department_id"]
    except (KeyError, IndexError):
        department_id = None
    append_audit_event(
        "auth_login",
        {
            "username": row["username"],
            "role": row["role"],
            "department_id": department_id,
        },
        resource_type="auth_user",
        resource_id=int(row["id"]),
        actor_user_id=int(row["id"]),
    )
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
    append_audit_event(
        "auth_logout",
        {"session_revoked": bool(token)},
        resource_type="auth_session",
    )
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
            department_id=payload.department_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = next(row for row in list_users() if int(row["id"]) == user_id)
    return UserPublic.model_validate(row)


@router.patch("/users/{user_id}", response_model=UserPublic)
def update_user_route(
    user_id: int,
    payload: UpdateUserRequest,
    admin: AuthenticatedUser = Depends(require_admin),
) -> UserPublic:
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No supported fields to update")
    if "is_active" in fields and fields["is_active"] is None:
        raise HTTPException(status_code=400, detail="is_active must be true or false")
    if "role" in fields and fields["role"] is None:
        raise HTTPException(status_code=400, detail="role must not be null")
    if "display_name" in fields and not fields["display_name"]:
        raise HTTPException(status_code=400, detail="display_name must not be empty")
    if user_id == admin.id and fields.get("is_active") is False:
        raise HTTPException(status_code=400, detail="Refusing to disable the current admin")
    target = get_user_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    loses_admin = (
        target["role"] == "admin"
        and bool(target["is_active"])
        and (
            ("role" in fields and fields["role"] != "admin")
            or ("is_active" in fields and not fields["is_active"])
        )
    )
    if loses_admin and count_active_admins(exclude_user_id=user_id) == 0:
        raise HTTPException(status_code=400, detail="At least one active admin must remain")
    try:
        row = update_user_admin(user_id, fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    revoked = 0
    if fields.get("is_active") is False or "role" in fields:
        # Privilege change or disable: every existing session must re-authenticate.
        revoked = revoke_user_sessions(user_id)
    append_audit_event(
        "auth_user_updated",
        {
            "target_user_id": user_id,
            "fields": {
                key: (bool(value) if key == "is_active" else value)
                for key, value in fields.items()
            },
            "revoked_sessions": revoked,
        },
        resource_type="auth_user",
        resource_id=user_id,
        actor_user_id=admin.id,
    )
    return UserPublic.model_validate(row)
