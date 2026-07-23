from __future__ import annotations

from app.enterprise.config import EnterpriseConfig, get_enterprise_config
from app.integrations.emr import MockEMRAdapter
from app.integrations.his import MockHISAdapter
from app.integrations.identity import LocalIdentityProvider, MockOIDCIdentityProvider


class AdapterUnavailableError(RuntimeError):
    """Raised when a requested enterprise adapter is disabled or unsupported."""


def create_identity_provider(config: EnterpriseConfig | None = None):
    selected = config or get_enterprise_config()
    state = selected.capability_states()["identity_provider"]
    if state == "disabled":
        raise AdapterUnavailableError("Identity provider is disabled")
    if selected.identity_provider == "local":
        return LocalIdentityProvider()
    if selected.identity_provider == "mock_oidc":
        return MockOIDCIdentityProvider()
    raise AdapterUnavailableError("Only local and mock_oidc identity providers are implemented")


def create_his_adapter(config: EnterpriseConfig | None = None) -> MockHISAdapter:
    selected = config or get_enterprise_config()
    state = selected.capability_states()["his_adapter"]
    if state == "disabled":
        raise AdapterUnavailableError("HIS adapter is disabled")
    if selected.his_adapter == "mock":
        return MockHISAdapter()
    raise AdapterUnavailableError("Only mock HIS adapter is implemented")


def create_emr_adapter(config: EnterpriseConfig | None = None) -> MockEMRAdapter:
    selected = config or get_enterprise_config()
    state = selected.capability_states()["emr_adapter"]
    if state == "disabled":
        raise AdapterUnavailableError("EMR adapter is disabled")
    if selected.emr_adapter == "mock":
        return MockEMRAdapter()
    raise AdapterUnavailableError("Only mock EMR adapter is implemented")
