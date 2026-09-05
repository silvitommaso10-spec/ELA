"""Permissions: the capability catalogue (M4.1, ADR 0010) and, from M4.2, the Guardian (§27–§29)."""

from ela.permissions.capabilities import (
    CORE_ECHO,
    DEFAULT_NOTES_SCOPE,
    MAX_RISK,
    MODEL_COMPLETE,
    SCHEMA_VALIDATOR,
    V01_INTRODUCED_AT,
    WORKSPACE_WRITE_NOTE,
    CapabilityRegistry,
    catalogue_v01,
    check_capability,
    core_echo,
    is_valid_scope_entry,
    model_complete,
    validate_arguments,
    workspace_write_note,
)
from ela.permissions.errors import (
    CapabilityNotFound,
    InvalidArgumentsError,
    InvalidCapabilityError,
    PermissionsError,
    RiskNotAllowedError,
)

__all__ = [
    "CORE_ECHO",
    "DEFAULT_NOTES_SCOPE",
    "MAX_RISK",
    "MODEL_COMPLETE",
    "SCHEMA_VALIDATOR",
    "V01_INTRODUCED_AT",
    "WORKSPACE_WRITE_NOTE",
    "CapabilityNotFound",
    "CapabilityRegistry",
    "InvalidArgumentsError",
    "InvalidCapabilityError",
    "PermissionsError",
    "RiskNotAllowedError",
    "catalogue_v01",
    "check_capability",
    "core_echo",
    "is_valid_scope_entry",
    "model_complete",
    "validate_arguments",
    "workspace_write_note",
]
