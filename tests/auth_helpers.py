from __future__ import annotations

from fastapi.testclient import TestClient


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123456"


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
) -> dict:
    login_as_admin(client)
    response = client.post(
        "/api/auth/users",
        json={
            "username": username,
            "password": password,
            "display_name": display_name,
            "role": role,
        },
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
