"""Every port is a runtime-checkable, documented Protocol, and every implementation fits it.

``isinstance`` against a ``runtime_checkable`` protocol only checks that the attributes exist;
the signature and sync/async comparisons here cover what it cannot see.
"""

from __future__ import annotations

import pytest

from ela import ports
from ela.domain import AuditEvent, TaskId
from ela.ports import AuditLog
from tests.contracts.implementations import IMPLEMENTATIONS, Implementation, implementations_of
from tests.contracts.protocols import (
    REQUIRED_PORTS,
    is_async,
    is_property,
    is_runtime_checkable,
    members,
    method_names,
    parameter_shape,
    port_protocols,
)

PORTS = port_protocols()
PAIRS = [(port, impl) for port in PORTS for impl in implementations_of(port)]
PAIR_IDS = [f"{port.__name__}-{impl}" for port, impl in PAIRS]


@pytest.mark.parametrize("port", PORTS, ids=lambda p: p.__name__)
def test_port_is_runtime_checkable(port: type) -> None:
    assert is_runtime_checkable(port)


@pytest.mark.parametrize("port", PORTS, ids=lambda p: p.__name__)
def test_port_cites_the_spec(port: type) -> None:
    assert port.__doc__ and "§" in port.__doc__


@pytest.mark.parametrize("port,impl", PAIRS, ids=PAIR_IDS)
def test_implementation_satisfies_protocol(port: type, impl: Implementation) -> None:
    assert isinstance(impl.make(), port)


@pytest.mark.parametrize("port,impl", PAIRS, ids=PAIR_IDS)
def test_implementation_signatures_match(port: type, impl: Implementation) -> None:
    instance = impl.make()
    for name in members(port):
        if is_property(port, name):
            getattr(instance, name)  # readable, whether property or plain attribute
            continue
        assert parameter_shape(type(instance), name) == parameter_shape(port, name), name


@pytest.mark.parametrize("port,impl", PAIRS, ids=PAIR_IDS)
def test_implementation_modes_match(port: type, impl: Implementation) -> None:
    instance = impl.make()
    for name in method_names(port):
        assert is_async(type(instance), name) is is_async(port, name), name


def test_every_port_has_an_implementation() -> None:
    without = sorted(port.__name__ for port in PORTS if not implementations_of(port))
    assert without == []


def test_ports_are_exactly_the_eleven_required() -> None:
    assert {port.__name__ for port in PORTS} == REQUIRED_PORTS
    assert set(IMPLEMENTATIONS) == set(PORTS)


def test_all_is_sorted_and_complete() -> None:
    assert ports.__all__ == sorted(ports.__all__)
    for name in ports.__all__:
        assert hasattr(ports, name), name


# --------------------------------------------------------------------------------------
# Negative cases: what each check catches.
# --------------------------------------------------------------------------------------


class _AppendOnly:
    async def append(self, event: AuditEvent) -> None:
        pass


class _ReadWithALimit:
    async def append(self, event: AuditEvent) -> None:
        pass

    async def read(self, *, task_id: TaskId | None = None, limit: int = 10) -> tuple[()]:
        return ()


class _SyncRead:
    async def append(self, event: AuditEvent) -> None:
        pass

    def read(self, *, task_id: TaskId | None = None) -> tuple[()]:
        return ()


def test_missing_method_fails_isinstance() -> None:
    assert not isinstance(_AppendOnly(), AuditLog)


def test_extra_parameter_fails_signature_check() -> None:
    assert isinstance(_ReadWithALimit(), AuditLog)  # isinstance alone would let it through
    assert parameter_shape(_ReadWithALimit, "read") != parameter_shape(AuditLog, "read")


def test_sync_method_fails_mode_check() -> None:
    assert isinstance(_SyncRead(), AuditLog)
    assert is_async(_SyncRead, "read") is not is_async(AuditLog, "read")
