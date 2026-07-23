from __future__ import annotations

from typing import Any, Protocol

from app.enterprise.contracts import IdentityAuthResult, IdentityPrincipal


class IdentityProvider(Protocol):
    provider_name: str

    def authenticate(self, credentials: dict[str, Any]) -> IdentityAuthResult:
        """Authenticate against a local or mock identity provider."""


class LocalIdentityProvider:
    provider_name = "local"

    def authenticate(self, credentials: dict[str, Any]) -> IdentityAuthResult:
        username = str(credentials.get("username") or "").strip()
        user_id = credentials.get("user_id")
        if not username:
            return IdentityAuthResult(
                status="rejected",
                provider=self.provider_name,
                reason="username_required",
            )
        subject = f"local:{user_id}" if user_id is not None else f"local:{username}"
        return IdentityAuthResult(
            status="authenticated",
            provider=self.provider_name,
            principal=IdentityPrincipal(
                subject=subject,
                display_name=username,
                organization_id=credentials.get("organization_id"),
                department_ids=list(credentials.get("department_ids") or []),
                claims={"source": "local_identity_provider"},
            ),
        )


class MockOIDCIdentityProvider:
    provider_name = "mock_oidc"
    issuer = "mock-oidc"

    def authenticate(self, credentials: dict[str, Any]) -> IdentityAuthResult:
        token = str(credentials.get("token") or "").strip()
        if token != "mock-valid-token":
            return IdentityAuthResult(
                status="rejected",
                provider=self.provider_name,
                reason="mock_token_rejected",
            )
        return IdentityAuthResult(
            status="authenticated",
            provider=self.provider_name,
            principal=IdentityPrincipal(
                subject="mock-oidc:doctor-001",
                display_name="Mock OIDC Doctor",
                email="doctor-001@example.invalid",
                organization_id=str(credentials.get("organization_id") or "mock-org"),
                department_ids=[str(credentials.get("department_id") or "mock-dept")],
                claims={
                    "iss": self.issuer,
                    "sub": "doctor-001",
                    "mock": True,
                },
            ),
        )
