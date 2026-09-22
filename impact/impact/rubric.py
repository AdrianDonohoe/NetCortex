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

from .change import Change
from .evidence import Evidence


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
    if evidence.history.path is not None and evidence.history.exists:
        for idx, entry, outcome in evidence.history.change_records():
            if (
                entry.type is change.type
                and entry.target == change.target
                and outcome == "failed"
            ):
                return (
                    HistoricalSignal.FAILURE_MATCH,
                    Factor(
                        "historical evidence",
                        f"a failed Change Record on {change.target}: "
                        f"{entry.describe()}",
                        f"{evidence.history.path}:{idx}",
                    ),
                )
    if evidence.episodes.path is not None and evidence.episodes.exists:
        mentions = evidence.episodes.mention_lines(change.target)
        if mentions:
            return (
                HistoricalSignal.CONTACT,
                Factor(
                    "historical evidence",
                    f"past Episodes touch {change.target}",
                    f"{evidence.episodes.path}:"
                    f"{','.join(map(str, mentions))}",
                ),
            )
    history_checked = (
        evidence.history.path is not None and evidence.history.exists
    )
    episodes_checked = (
        evidence.episodes.path is not None and evidence.episodes.exists
    )
    if not history_checked and not episodes_checked:
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
    if episodes_checked:
        findings.append(f"no Episodes touch {change.target}")
        sources.append(evidence.episodes.path)
    else:
        findings.append(f"Episodes {evidence.episodes.describe()}")
    signal = (
        HistoricalSignal.NONE
        if history_checked and episodes_checked
        else HistoricalSignal.UNKNOWN
    )
    return (
        signal,
        Factor("historical evidence", "; ".join(findings), ", ".join(sources)),
    )


def grade(change: Change, evidence: Evidence) -> Rubric:
    """Grade the Change: assess the factors, then apply the matrix.

    Dependency criticality and blast radius derive from captures; no
    captures are consulted yet, so both grade as not determinable and
    their citations say so. The tickets that consult captures extend
    this function.
    """
    history_signal, history_factor = _assess_history(change, evidence)
    criticality_factor = Factor(
        "dependency criticality",
        "not determinable",
        "no capture evidence to derive dependencies from",
    )
    blast_factor = Factor(
        "blast radius",
        "not determinable",
        "no capture evidence to derive the affected Procedures and KPIs from",
    )
    return Rubric(
        grade_matrix(history_signal, Criticality.UNKNOWN, BlastRadius.UNKNOWN),
        (history_factor, criticality_factor, blast_factor),
    )
