"""Device Registry: the nodes ELA can operate through, and which of them answer (§16, §54).

:class:`DeviceRegistry` is the Core service; :class:`~ela.ports.DeviceRegistryPort` is where the
nodes are kept, with ``SqlDeviceRegistry`` (M6.1) as its persistent implementation. The Device
Orchestrator (§17, M6.2) chooses *which* node to use and reads from here; M6.1 chooses nothing.
"""

from ela.devices.errors import UnsupportedOperatingSystemError
from ela.devices.local import (
    DEVICE_NAMESPACE,
    LOCAL_DEVICE_ID,
    LOCAL_DEVICE_NAME,
    SYSTEMS,
    local_device,
    operating_system,
)
from ela.devices.registry import AVAILABLE, UNAVAILABLE, DeviceRegistry, is_available
from ela.devices.settings import DEFAULT_HEARTBEAT_TTL_SECONDS, DeviceSettings

__all__ = [
    "AVAILABLE",
    "DEFAULT_HEARTBEAT_TTL_SECONDS",
    "DEVICE_NAMESPACE",
    "LOCAL_DEVICE_ID",
    "LOCAL_DEVICE_NAME",
    "SYSTEMS",
    "UNAVAILABLE",
    "DeviceRegistry",
    "DeviceSettings",
    "UnsupportedOperatingSystemError",
    "is_available",
    "local_device",
    "operating_system",
]
