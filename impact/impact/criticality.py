"""Dependency criticality: critical interfaces in the blast radius.

A critical interface is SBI to UDM/AUSF (Nudm_*/Nausf_*) or the N2
control plane's SBI face (Namf_Communication_N1N2MessageTransfer). The
scans walk the blast radius's evidence — the capture messages at the
target's and partners' evidence pointers, the specgraph entities
behind the reference dependencies — and collect every critical
interface they find, each with its pointer. Role inference makes the
capture pointers complete: a Nudm message proves the UDM role, so any
critical traffic in the capture is visible at those pointers.
"""

from __future__ import annotations

from dataclasses import dataclass

from .capture import BlastResult, CaptureState, message_at
from .specgraph import RefPartner, SpecGraphState


def is_critical(name: str) -> bool:
    """A critical interface: SBI to UDM/AUSF, or N2's message-transfer face."""
    return (
        name == "Namf_Communication_N1N2MessageTransfer"
        or name.startswith("Nudm_")
        or name.startswith("Nausf_")
    )


@dataclass(frozen=True)
class CriticalHit:
    """One critical interface in the blast radius, with its pointer."""

    name: str
    pointer: str


def capture_hits(
    capture: CaptureState, result: BlastResult
) -> tuple[CriticalHit, ...]:
    """Critical interfaces among the blast radius's capture evidence.

    The scan covers the proving messages only — the target's own
    evidence pointer and every partner's — because role inference
    guarantees a critical-role NF is proved by its critical message.
    Hits order by pointer, the wire's own order.
    """
    if result.target is None:
        return ()
    pointers = [result.target.evidence] + [
        nf.evidence for nf in result.affected
    ]
    hits = []
    for pointer in pointers:
        message = message_at(capture, pointer)
        name = (message or {}).get("name") or ""
        if is_critical(name):
            hits.append(CriticalHit(name, pointer))
    return tuple(sorted(hits, key=lambda hit: hit.pointer))


def specgraph_hits(
    state: SpecGraphState, partners: tuple[RefPartner, ...]
) -> tuple[CriticalHit, ...]:
    """Critical interfaces among the specgraph reference dependencies.

    Reference evidence ids resolve through the state's own entities, so
    a hit always names an entity the export holds; an id the state does
    not hold is skipped, never guessed. Hits order by pointer.
    """
    by_id = {
        entity.get("id"): entity
        for entity in state.entities
        if entity.get("id")
    }
    hits = []
    for partner in partners:
        for id_ in partner.evidence:
            entity = by_id.get(id_)
            name = (entity or {}).get("name") or ""
            if is_critical(name):
                hits.append(CriticalHit(name, id_))
    return tuple(sorted(hits, key=lambda hit: hit.pointer))
