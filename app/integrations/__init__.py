from app.integrations.emr import EMRAdapter, MockEMRAdapter
from app.integrations.factory import AdapterUnavailableError, create_emr_adapter, create_his_adapter, create_identity_provider
from app.integrations.his import HISAdapter, MockHISAdapter
from app.integrations.identity import IdentityProvider, LocalIdentityProvider, MockOIDCIdentityProvider

REAL_HOSPITAL_ADAPTERS: tuple[str, ...] = ()

__all__ = [
    "AdapterUnavailableError",
    "EMRAdapter",
    "HISAdapter",
    "IdentityProvider",
    "LocalIdentityProvider",
    "MockEMRAdapter",
    "MockHISAdapter",
    "MockOIDCIdentityProvider",
    "REAL_HOSPITAL_ADAPTERS",
    "create_emr_adapter",
    "create_his_adapter",
    "create_identity_provider",
]
