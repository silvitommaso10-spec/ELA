"""The hash chain of ``ela.audit.chain`` (ADR 0007 §2–§3): deterministic, sensitive, verifiable."""

from __future__ import annotations

import json
import re

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ela.audit.chain import (
    EMPTY_CHAIN,
    GENESIS_HASH,
    AuditChainError,
    ChainFault,
    ChainSummary,
    Link,
    Record,
    canonical_bytes,
    link_hash,
    verify_links,
)

HEX_64 = re.compile(r"^[0-9a-f]{64}$")
RECORD: Record = {"id": "e1", "summary": "nota scritta", "payload": {"bytes": 2048, "ok": True}}
OTHER: Record = {"id": "e2", "summary": "seconda", "payload": {}}
THIRD: Record = {"id": "e3", "summary": "terza", "payload": {"n": None}}

json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=10,
)
records = st.dictionaries(st.text(), json_values, max_size=6)


def chain_of(*records: Record) -> list[Link]:
    """A well-formed chain over ``records``, positions from 1."""
    links: list[Link] = []
    head = GENESIS_HASH
    for position, record in enumerate(records, start=1):
        digest = link_hash(head, record)
        links.append(Link(position, head, digest, record))
        head = digest
    return links


# ----------------------------------------------------------------------------------------
# Hashing
# ----------------------------------------------------------------------------------------


def test_genesis_is_sixty_four_zeros() -> None:
    assert GENESIS_HASH == "0" * 64
    assert ChainSummary(length=0, head_hash=GENESIS_HASH) == EMPTY_CHAIN


def test_link_hash_is_a_lowercase_sha256_and_deterministic() -> None:
    digest = link_hash(GENESIS_HASH, RECORD)
    assert HEX_64.match(digest)
    assert digest == link_hash(GENESIS_HASH, dict(RECORD))


def test_canonical_form_is_sorted_compact_ascii_json() -> None:
    raw = canonical_bytes("ab", {"z": 1, "a": {"é": "ü"}, "m": [1, 2]})
    assert raw == b'{"previous_hash":"ab","record":{"a":{"\\u00e9":"\\u00fc"},"m":[1,2],"z":1}}'
    assert json.loads(raw) == {
        "previous_hash": "ab",
        "record": {"z": 1, "a": {"é": "ü"}, "m": [1, 2]},
    }


def test_key_order_does_not_matter() -> None:
    assert link_hash("x", {"a": 1, "b": 2}) == link_hash("x", {"b": 2, "a": 1})


def test_every_key_and_the_previous_hash_matter() -> None:
    base = link_hash(GENESIS_HASH, RECORD)
    for key in RECORD:
        altered = {**RECORD, key: "altered"}
        assert link_hash(GENESIS_HASH, altered) != base, key
    assert link_hash("1" * 64, RECORD) != base
    assert link_hash(GENESIS_HASH, {**RECORD, "extra": None}) != base


def test_a_value_that_is_not_json_cannot_be_hashed() -> None:
    with pytest.raises(TypeError):
        link_hash(GENESIS_HASH, {"when": object()})
    with pytest.raises(ValueError):
        link_hash(GENESIS_HASH, {"nan": float("nan")})


# ----------------------------------------------------------------------------------------
# Verification
# ----------------------------------------------------------------------------------------


def test_an_empty_chain_verifies_to_the_genesis() -> None:
    assert verify_links([]) == EMPTY_CHAIN


def test_a_well_formed_chain_verifies_to_its_head() -> None:
    links = chain_of(RECORD, OTHER, THIRD)
    assert verify_links(links) == ChainSummary(length=3, head_hash=links[-1].hash)


def test_verification_continues_across_windows() -> None:
    links = chain_of(RECORD, OTHER, THIRD)
    first = verify_links(links[:2])
    assert first.length == 2
    assert verify_links(links[2:], after=first) == verify_links(links)


def test_a_first_link_not_on_the_genesis_is_a_broken_link() -> None:
    links = chain_of(RECORD, OTHER)
    with pytest.raises(AuditChainError) as excinfo:
        verify_links(links[1:])  # starts from the second link, as if the first were gone
    assert (excinfo.value.position, excinfo.value.fault) == (2, ChainFault.BROKEN_LINK)
    assert "BROKEN_LINK at position 2" in str(excinfo.value)


def test_a_missing_link_in_the_middle_is_a_broken_link_on_the_next() -> None:
    links = chain_of(RECORD, OTHER, THIRD)
    with pytest.raises(AuditChainError) as excinfo:
        verify_links([links[0], links[2]])
    assert (excinfo.value.position, excinfo.value.fault) == (3, ChainFault.BROKEN_LINK)


def test_a_rewritten_previous_hash_is_a_broken_link() -> None:
    links = chain_of(RECORD, OTHER)
    forged = Link(2, "f" * 64, links[1].hash, links[1].record)
    with pytest.raises(AuditChainError) as excinfo:
        verify_links([links[0], forged])
    assert (excinfo.value.position, excinfo.value.fault) == (2, ChainFault.BROKEN_LINK)


def test_an_altered_record_is_an_altered_row() -> None:
    links = chain_of(RECORD, OTHER, THIRD)
    altered = Link(2, links[1].previous_hash, links[1].hash, {**OTHER, "summary": "rewritten"})
    with pytest.raises(AuditChainError) as excinfo:
        verify_links([links[0], altered, links[2]])
    assert (excinfo.value.position, excinfo.value.fault) == (2, ChainFault.ALTERED_ROW)


def test_swapped_links_are_detected() -> None:
    links = chain_of(RECORD, OTHER, THIRD)
    with pytest.raises(AuditChainError) as excinfo:
        verify_links([links[0], links[2], links[1]])
    assert excinfo.value.position == 3


def test_the_first_fault_wins() -> None:
    """A row both unlinked and altered is reported as unlinked: the link is checked first."""
    links = chain_of(RECORD, OTHER)
    forged = Link(2, "f" * 64, links[1].hash, {**OTHER, "summary": "rewritten"})
    with pytest.raises(AuditChainError) as excinfo:
        verify_links([links[0], forged])
    assert excinfo.value.fault is ChainFault.BROKEN_LINK


def test_a_truncated_tail_is_not_detectable_by_the_chain_alone() -> None:
    """Documented limit (ADR 0007 §8): the anchor to detect it is the summary itself."""
    links = chain_of(RECORD, OTHER, THIRD)
    full = verify_links(links)
    truncated = verify_links(links[:2])
    assert truncated.length < full.length and truncated.head_hash != full.head_hash


@settings(max_examples=100)
@given(st.lists(records, max_size=8))
def test_any_chain_built_with_link_hash_verifies(items: list[Record]) -> None:
    links = chain_of(*items)
    summary = verify_links(links)
    assert summary.length == len(items)
    assert summary.head_hash == (links[-1].hash if links else GENESIS_HASH)


@settings(max_examples=100)
@given(st.lists(records, min_size=1, max_size=8), st.data())
def test_altering_any_record_breaks_the_chain(items: list[Record], data: st.DataObject) -> None:
    links = chain_of(*items)
    index = data.draw(st.integers(min_value=0, max_value=len(links) - 1))
    victim = links[index]
    assume(victim.record.get("__tampered__") is not True)
    tampered = Link(
        victim.position, victim.previous_hash, victim.hash, {**victim.record, "__tampered__": True}
    )
    with pytest.raises(AuditChainError) as excinfo:
        verify_links([*links[:index], tampered, *links[index + 1 :]])
    assert (excinfo.value.position, excinfo.value.fault) == (index + 1, ChainFault.ALTERED_ROW)
