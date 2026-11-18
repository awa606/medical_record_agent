from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.requests import Request

from app.schemas.auth import AuthenticatedUser


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123456"


def authenticated_request(user: dict) -> Request:
    """A real Request carrying an authenticated user, for direct handler calls.

    Tests that call route functions as plain Python functions still have to
    present an identity: authorization is fail-closed since the hardening pass.
    """
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
        "app": None,
    }
    request = Request(scope)
    request.state.current_user = AuthenticatedUser.model_validate(user)
    return request


def login_as_admin(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login",
        json={"username": DEFAULT_ADMIN_USERNAME, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def create_user(
    client: TestClient,
    *,
    username: str,
    password: str = "doctor-pass-123",
    display_name: str = "Test Doctor",
    role: str = "doctor",
    department_id: str | None = None,
) -> dict:
    login_as_admin(client)
    payload = {
        "username": username,
        "password": password,
        "display_name": display_name,
        "role": role,
    }
    if department_id is not None:
        payload["department_id"] = department_id
    response = client.post(
        "/api/auth/users",
        json=payload,
    )
    assert response.status_code == 201, response.text
    client.post("/api/auth/logout")
    return response.json()


def login_as_user(
    client: TestClient,
    *,
    username: str,
    password: str = "doctor-pass-123",
) -> dict:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]
