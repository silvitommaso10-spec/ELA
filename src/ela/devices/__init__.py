"""Device Registry and Device Orchestrator: which nodes exist, and which one runs a step (§16, §17).

:class:`DeviceRegistry` is the Core service over :class:`~ela.ports.DeviceRegistryPort`, where the
nodes are kept, with ``SqlDeviceRegistry`` (M6.1) as its persistent implementation.
:class:`DeviceOrchestrator` (§17, M6.2) chooses *which* node runs a step and reads from the
registry, never from the port: the availability it needs is the one derived from the heartbeat,
not the one stored in the row (ADR 0016 §3, ADR 0017).

The package advises and does not command: it cannot import ``ela.tasks``, so no placement can
move — or fail — a task (ADR 0017 §6, architecture rule 22).
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
from ela.devices.orchestrator import (
    NETWORK_POINTS,
    ORCHESTRATOR_ACTOR,
    PERFORMANCE_POINTS,
    POWER_POINTS,
    PRIVACY_ORDER,
    STATUS_POINTS,
    TRAIT_POINTS,
    UNGUARDED_RISK,
    WORKLOAD_POINTS,
    DeviceOrchestrator,
    Placement,
    Refusal,
    Requirements,
    Score,
    choose,
    refusals,
    score,
)
from ela.devices.registry import AVAILABLE, UNAVAILABLE, DeviceRegistry, is_available
from ela.devices.settings import DEFAULT_HEARTBEAT_TTL_SECONDS, DeviceSettings

__all__ = [
    "AVAILABLE",
    "DEFAULT_HEARTBEAT_TTL_SECONDS",
    "DEVICE_NAMESPACE",
    "LOCAL_DEVICE_ID",
    "LOCAL_DEVICE_NAME",
    "NETWORK_POINTS",
    "ORCHESTRATOR_ACTOR",
    "PERFORMANCE_POINTS",
    "POWER_POINTS",
    "PRIVACY_ORDER",
    "STATUS_POINTS",
    "SYSTEMS",
    "TRAIT_POINTS",
    "UNAVAILABLE",
    "UNGUARDED_RISK",
    "WORKLOAD_POINTS",
    "DeviceOrchestrator",
    "DeviceRegistry",
    "DeviceSettings",
    "Placement",
    "Refusal",
    "Requirements",
    "Score",
    "UnsupportedOperatingSystemError",
    "choose",
    "is_available",
    "local_device",
    "operating_system",
    "refusals",
    "score",
]
