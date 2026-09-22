"""The specgraph fallback: reference points when no capture is consulted.

triage builds the specgraph export by AST-parsing the specs; impact only
reads the cached JSON — it never builds the graph itself (CONTEXT-MAP).
The fallback derives the target's service operations and its reference
dependencies: NF families co-mentioned with the target's SBI service.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SBI_FAMILY = re.compile(r"^N[a-z]{2,}$")


@dataclass(frozen=True)
class SpecGraphState:
    """What a specgraph export holds: path, entities, edges, existence."""

    path: str | None
    entities: tuple[dict, ...] = ()
    edges: tuple[dict, ...] = ()
    exists: bool = True

    @property
    def consulted(self) -> bool:
        """True when the export was read and can attest to what it holds."""
        return self.path is not None and self.exists

    def describe(self) -> str:
        if self.path is None:
            return "not consulted"
        if not self.exists:
            return f"{self.path} does not exist"
        if not self.entities:
            return f"{self.path} holds no entities"
        if len(self.entities) == 1:
            return f"{self.path} holds 1 entity"
        return f"{self.path} holds {len(self.entities)} entities"


@dataclass(frozen=True)
class RefPartner:
    """One reference dependency: its NF role and the citing entity ids."""

    role: str
    evidence: tuple[str, ...]


def sbi_family(entity: dict) -> str | None:
    """The NF family of an SBI message entity: Nsmf_... → Nsmf, else None."""
    if entity.get("protocol") != "SBI" or entity.get("type") != "message":
        return None
    family = (entity.get("name") or "").split("_", 1)[0]
    return family if _SBI_FAMILY.match(family) else None


def co_mentioned(
    state: SpecGraphState, entity_ids: tuple[str, ...]
) -> tuple[dict, ...]:
    """The entities co-mentioned with the given ones, in edge order."""
    by_id = {
        entity.get("id"): entity
        for entity in state.entities
        if entity.get("id")
    }
    wanted = set(entity_ids)
    neighbors: list[dict] = []
    seen: set[str] = set()
    for edge in state.edges:
        if edge.get("kind") != "co_mentioned":
            continue
        src, dst = edge.get("src"), edge.get("dst")
        for neighbor_id in (
            dst if src in wanted else None,
            src if dst in wanted else None,
        ):
            if (
                neighbor_id is not None
                and neighbor_id in by_id
                and neighbor_id not in seen
            ):
                seen.add(neighbor_id)
                neighbors.append(by_id[neighbor_id])
    return tuple(neighbors)


def service_family(target: str) -> str:
    """The SBI service family of an NF role: SMF → Nsmf."""
    return f"N{target.lower()}"


def sbi_entities(state: SpecGraphState, family: str) -> tuple[dict, ...]:
    """The SBI message entities of one NF family (e.g. Nsmf)."""
    return tuple(
        entity for entity in state.entities if sbi_family(entity) == family
    )


def reference_partners(
    state: SpecGraphState, target: str
) -> tuple[RefPartner, ...]:
    """Reference dependencies: NF families co-mentioned with the target's service.

    Each partner cites the co-mentioned SBI entity ids behind it; the
    target's own family never joins its own radius.
    """
    if not state.consulted:
        return ()
    own = sbi_entities(state, service_family(target))
    partners: dict[str, tuple[str, ...]] = {}
    for neighbor in co_mentioned(
        state, tuple(entity.get("id") or "" for entity in own)
    ):
        family = sbi_family(neighbor)
        if family is None:
            continue
        role = family[1:].upper()
        if role.upper() == target.upper():
            continue
        partners[role] = partners.get(role, ()) + ((neighbor.get("id") or ""),)
    return tuple(
        sorted(
            (RefPartner(role, evidence) for role, evidence in partners.items()),
            key=lambda partner: partner.role,
        )
    )
