"""ellmos-homecontrol: SmartHome, household appliance, and vendor-neutral router control hub."""

from .hub import (
    FritzBoxAdapter,
    HighLoadConfirmationRequiredError,
    HomeAssistantAdapter,
    HomeControlHub,
    HomeDevice,
    MatterBridgeAdapter,
    MqttShellyAdapter,
)
from .router import (
    CapabilityDescriptor,
    FritzBoxRouterAdapter,
    GenericGatewayAdapter,
    HuaweiHiLinkRouterAdapter,
    RouterAdapter,
    RouterAuthorityGateError,
    RouterCredentials,
    RouterError,
    RouterReadbackVerificationError,
    UnsupportedCapabilityError,
    discover_router,
    redact_secrets,
    resolve_router_credentials,
)

__all__ = [
    "CapabilityDescriptor",
    "FritzBoxAdapter",
    "FritzBoxRouterAdapter",
    "GenericGatewayAdapter",
    "HighLoadConfirmationRequiredError",
    "HomeAssistantAdapter",
    "HomeControlHub",
    "HomeDevice",
    "HuaweiHiLinkRouterAdapter",
    "MatterBridgeAdapter",
    "MqttShellyAdapter",
    "RouterAdapter",
    "RouterAuthorityGateError",
    "RouterCredentials",
    "RouterError",
    "RouterReadbackVerificationError",
    "UnsupportedCapabilityError",
    "discover_router",
    "redact_secrets",
    "resolve_router_credentials",
]

__version__ = "0.1.0"
