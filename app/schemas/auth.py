from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


UserRole = Literal["admin", "doctor"]


class AuthenticatedUser(BaseModel):
    id: int
    username: str
    display_name: str
    role: UserRole
    is_active: bool = True


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    user: AuthenticatedUser
    session_expires_at: str


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(min_length=1, max_length=80)
    role: UserRole = "doctor"


class UserPublic(BaseModel):
    id: int
    username: str
    display_name: str
    role: UserRole
    is_active: bool
    created_at: str
    updated_at: str
    last_login_at: str | None = None


class UserListResponse(BaseModel):
    users: list[UserPublic]
