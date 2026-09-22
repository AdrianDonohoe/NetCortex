"""The risk rubric: computed in code, never by the LLM.

Three factors — historical evidence, dependency criticality, blast
radius — map to four grades, and every factor carries its citation.
The matrix lives in grade_matrix: HIGH on a historical failure match
or a critical-interface dependency, MEDIUM on past-Episode contact or
a wide blast radius, LOW only when every factor is determinable and
nothing fires, INSUFFICIENT EVIDENCE otherwise — an unknowable risk
is never graded LOW (ADR-0001).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .capture import blast_radius
from .change import Change, ChangeType
from .criticality import capture_hits, specgraph_hits
from .evidence import (
    Evidence,
    capture_note,
    dispatch_episode_mentions,
    report_mentions,
    triage_episode_mentions,
)
from .specgraph import reference_partners


class RiskGrade(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT EVIDENCE"


class HistoricalSignal(str, Enum):
    """What the historical stores say about this Change's target."""

    FAILURE_MATCH = "failure match"
    CONTACT = "contact"
    NONE = "none"
    UNKNOWN = "not determinable"


class Criticality(str, Enum):
    """Whether a critical interface sits in the blast radius."""

    CRITICAL = "critical"
    NON_CRITICAL = "non-critical"
    UNKNOWN = "not determinable"


class BlastRadius(str, Enum):
    """How many NFs and Procedures the Change touches."""

    WIDE = "wide"  # two or more affected NFs
    NARROW = "narrow"  # zero or one
    UNKNOWN = "not determinable"


def blast_from_count(n_affected: int | None) -> BlastRadius:
    """Map the affected count onto the matrix's blast-radius signal."""
    if n_affected is None:
        return BlastRadius.UNKNOWN
    if n_affected >= 2:
        return BlastRadius.WIDE
    return BlastRadius.NARROW


@dataclass(frozen=True)
class Factor:
    """One rubric factor, with its finding and the citation behind it."""

    name: str
    finding: str
    citation: str


@dataclass(frozen=True)
class Rubric:
    grade: RiskGrade
    factors: tuple[Factor, ...]


def grade_matrix(
    history: HistoricalSignal,
    criticality: Criticality,
    blast: BlastRadius,
) -> RiskGrade:
    """The matrix: three factor signals map to one of four grades."""
    if (
        history is HistoricalSignal.FAILURE_MATCH
        or criticality is Criticality.CRITICAL
    ):
        return RiskGrade.HIGH
    if history is HistoricalSignal.CONTACT or blast is BlastRadius.WIDE:
        return RiskGrade.MEDIUM
    if (
        history is HistoricalSignal.NONE
        and criticality is Criticality.NON_CRITICAL
        and blast is BlastRadius.NARROW
    ):
        return RiskGrade.LOW
    return RiskGrade.INSUFFICIENT_EVIDENCE


def _assess_history(
    change: Change, evidence: Evidence
) -> tuple[HistoricalSignal, Factor]:
    """Failed Change Records on the target first, then Episode contact."""
    target = change.target
    if evidence.history.path is not None and evidence.history.exists:
        for idx, entry, outcome in evidence.history.change_records():
            if (
                entry.type is change.type
                and entry.target == target
                and outcome == "failed"
            ):
                return (
                    HistoricalSignal.FAILURE_MATCH,
                    Factor(
                        "historical evidence",
                        f"a failed Change Record on {target}: "
                        f"{entry.describe()}",
                        f"{evidence.history.path}:{idx}",
                    ),
                )
    triage_mentions = triage_episode_mentions(
        evidence.triage_episodes, target
    )
    dispatch_mentions = dispatch_episode_mentions(
        evidence.dispatch_episodes, target
    )
    report_paths = report_mentions(evidence.reports, target)
    labels = [mention.label for mention in triage_mentions + dispatch_mentions]
    if labels or report_paths:
        findings = []
        if labels:
            findings.append(f"past Episodes touch {target}: {', '.join(labels)}")
        if report_paths:
            findings.append(
                f"post-incident reports mention {target}: "
                f"{', '.join(path for path, _ in report_paths)}"
            )
        citations = [
            mention.citation
            for mention in triage_mentions + dispatch_mentions
        ] + [
            f"{path}:{','.join(map(str, lines))}" for path, lines in report_paths
        ]
        return (
            HistoricalSignal.CONTACT,
            Factor(
                "historical evidence",
                "; ".join(findings),
                ", ".join(citations),
            ),
        )
    history_checked = evidence.history.consulted
    triage_checked = evidence.triage_episodes.consulted
    dispatch_checked = evidence.dispatch_episodes.consulted
    reports_checked = evidence.reports.consulted
    if not (history_checked or triage_checked or dispatch_checked or reports_checked):
        return (
            HistoricalSignal.UNKNOWN,
            Factor(
                "historical evidence",
                "not determinable",
                "no historical stores consulted",
            ),
        )
    findings: list[str] = []
    sources: list[str] = []
    if history_checked:
        findings.append("no failed Change Records in Change History")
        sources.append(evidence.history.path)
    else:
        findings.append(f"Change History {evidence.history.describe()}")
    if triage_checked:
        findings.append(f"no Triage Episodes touch {target}")
        sources.append(evidence.triage_episodes.path)
    else:
        findings.append(
            f"Triage Episodes {evidence.triage_episodes.describe()}"
        )
    if dispatch_checked:
        findings.append(f"no Dispatch Episodes touch {target}")
        sources.append(evidence.dispatch_episodes.path)
    else:
        findings.append(
            f"Dispatch Episodes {evidence.dispatch_episodes.describe()}"
        )
    if reports_checked:
        findings.append(f"no post-incident reports mention {target}")
        sources.append(evidence.reports.path)
    else:
        findings.append(
            f"Post-incident reports {evidence.reports.describe()}"
        )
    signal = (
        HistoricalSignal.NONE
        if history_checked and triage_checked and dispatch_checked and reports_checked
        else HistoricalSignal.UNKNOWN
    )
    return (
        signal,
        Factor("historical evidence", "; ".join(findings), ", ".join(sources)),
    )


def _assess_blast(
    change: Change, evidence: Evidence
) -> tuple[BlastRadius, Factor]:
    """Blast radius from capture evidence, falling back to specgraph references.

    The count is the target's partners only; an unroleable peer keeps
    the count unknown — NARROW requires full knowledge. Two or more
    known partners is WIDE whatever else the capture holds. The
    fallback order: capture first; the target not located there →
    specgraph; neither → honest not determinable.
    """
    if change.type is ChangeType.CONFIG:
        return (
            BlastRadius.UNKNOWN,
            Factor(
                "blast radius",
                "not determinable — the Change names a config key, "
                "not a network function",
                "change record",
            ),
        )
    result = blast_radius(change, evidence.capture)
    if result.target is not None:
        affected = result.affected
        if result.unknown_peers and len(affected) < 2:
            count = None
        else:
            count = len(affected)
        blast = blast_from_count(count)
        if affected:
            noun = "NF" if len(affected) == 1 else "NFs"
            finding = (
                f"affects {', '.join(nf.role for nf in affected)} "
                f"({len(affected)} {noun})"
            )
        else:
            finding = "affects no other NF"
        if result.unknown_peers:
            finding += (
                f"; {result.unknown_peers} peer(s) with no determinable role"
            )
        sources = [
            f"{evidence.capture.pointer_source(result.target.evidence)}:{result.target.evidence}",
            *(
                f"{evidence.capture.pointer_source(nf.evidence)}:{nf.evidence}"
                for nf in affected
            ),
            *(
                f"{evidence.capture.pointer_source(pointer)}:{pointer}"
                for pointer in result.unknown_peer_pointers
            ),
        ]
        return (
            blast,
            Factor(
                "blast radius",
                finding,
                ", ".join(dict.fromkeys(sources)),
            ),
        )
    partners = reference_partners(evidence.specgraph, change.target)
    if partners:
        noun = "NF" if len(partners) == 1 else "NFs"
        note = capture_note(evidence.capture, change.target)
        citation = ", ".join(
            f"{evidence.specgraph.path}:{id_}"
            for partner in partners
            for id_ in partner.evidence
        )
        return (
            blast_from_count(len(partners)),
            Factor(
                "blast radius",
                f"affects {', '.join(p.role for p in partners)} "
                f"({len(partners)} {noun}) per specgraph references; {note}",
                citation,
            ),
        )
    consulted = [
        str(state.path)
        for state in (evidence.capture, evidence.specgraph)
        if state.consulted
    ]
    missing = [
        state.describe()
        for state in (evidence.capture, evidence.specgraph)
        if state.path is not None and not state.exists
    ]
    if consulted:
        finding = (
            f"not determinable — {change.target} has no determinable "
            f"partners in {', '.join(consulted)}"
        )
        if missing:
            finding += "; " + "; ".join(missing)
        return (
            BlastRadius.UNKNOWN,
            Factor("blast radius", finding, ", ".join(consulted)),
        )
    if missing:
        return (
            BlastRadius.UNKNOWN,
            Factor(
                "blast radius",
                f"not determinable — {change.target} has no determinable "
                f"partners; {'; '.join(missing)}",
                ", ".join(
                    str(state.path)
                    for state in (evidence.capture, evidence.specgraph)
                    if state.path is not None
                ),
            ),
        )
    return (
        BlastRadius.UNKNOWN,
        Factor(
            "blast radius",
            "not determinable — no capture or specgraph evidence consulted",
            "no capture or specgraph evidence consulted",
        ),
    )


def _assess_criticality(
    change: Change, evidence: Evidence
) -> tuple[Criticality, Factor]:
    """Critical interfaces in the blast radius, from every consulted source.

    The capture's evidence pointers carry the proving messages, the
    specgraph's reference ids the co-mentioned entities; one critical
    interface in either is CRITICAL whatever else the sources hold.
    NON_CRITICAL requires full knowledge of the radius — no unroleable
    peers, every consulted source quiet. The fallback order mirrors the
    blast factor's: capture first; the target not located there →
    specgraph; neither → honest not determinable.
    """
    if change.type is ChangeType.CONFIG:
        return (
            Criticality.UNKNOWN,
            Factor(
                "dependency criticality",
                "not determinable — the Change names a config key, "
                "not a network function",
                "change record",
            ),
        )
    result = blast_radius(change, evidence.capture)
    partners = reference_partners(evidence.specgraph, change.target)
    capture_scan = capture_hits(evidence.capture, result)
    specgraph_scan = specgraph_hits(evidence.specgraph, partners)
    if capture_scan or specgraph_scan:
        names = ", ".join(
            dict.fromkeys(hit.name for hit in capture_scan + specgraph_scan)
        )
        citations = [
            f"{evidence.capture.pointer_source(hit.pointer)}:{hit.pointer}"
            for hit in capture_scan
        ] + [
            f"{evidence.specgraph.path}:{hit.pointer}"
            for hit in specgraph_scan
        ]
        return (
            Criticality.CRITICAL,
            Factor(
                "dependency criticality",
                f"critical interface {names} in the blast radius",
                ", ".join(dict.fromkeys(citations)),
            ),
        )
    if result.target is not None and result.unknown_peers == 0:
        return (
            Criticality.NON_CRITICAL,
            Factor(
                "dependency criticality",
                "no critical interface in the blast radius",
                ", ".join(
                    dict.fromkeys(
                        str(state.path)
                        for state in (evidence.capture, evidence.specgraph)
                        if state.consulted
                    )
                ),
            ),
        )
    if result.unknown_peers:
        pointers = ", ".join(
            f"{evidence.capture.pointer_source(pointer)}:{pointer}"
            for pointer in result.unknown_peer_pointers
        )
        return (
            Criticality.UNKNOWN,
            Factor(
                "dependency criticality",
                f"not determinable — {result.unknown_peers} peer(s) with no "
                "determinable role could hide a critical interface",
                pointers,
            ),
        )
    if partners:
        note = capture_note(evidence.capture, change.target)
        return (
            Criticality.NON_CRITICAL,
            Factor(
                "dependency criticality",
                f"no critical interface per the specgraph references; {note}",
                ", ".join(
                    f"{evidence.specgraph.path}:{id_}"
                    for partner in partners
                    for id_ in partner.evidence
                ),
            ),
        )
    consulted = [
        str(state.path)
        for state in (evidence.capture, evidence.specgraph)
        if state.consulted
    ]
    missing = [
        state.describe()
        for state in (evidence.capture, evidence.specgraph)
        if state.path is not None and not state.exists
    ]
    if consulted:
        finding = (
            f"not determinable — no blast radius to scan in "
            f"{', '.join(consulted)}"
        )
        if missing:
            finding += "; " + "; ".join(missing)
        return (
            Criticality.UNKNOWN,
            Factor("dependency criticality", finding, ", ".join(consulted)),
        )
    if missing:
        return (
            Criticality.UNKNOWN,
            Factor(
                "dependency criticality",
                f"not determinable — no blast radius to scan; "
                f"{'; '.join(missing)}",
                ", ".join(
                    str(state.path)
                    for state in (evidence.capture, evidence.specgraph)
                    if state.path is not None
                ),
            ),
        )
    return (
        Criticality.UNKNOWN,
        Factor(
            "dependency criticality",
            "not determinable — no capture or specgraph evidence consulted",
            "no capture or specgraph evidence consulted",
        ),
    )


def grade(change: Change, evidence: Evidence) -> Rubric:
    """Grade the Change: assess the factors, then apply the matrix."""
    history_signal, history_factor = _assess_history(change, evidence)
    criticality_signal, criticality_factor = _assess_criticality(
        change, evidence
    )
    blast_signal, blast_factor = _assess_blast(change, evidence)
    return Rubric(
        grade_matrix(history_signal, criticality_signal, blast_signal),
        (history_factor, criticality_factor, blast_factor),
    )
