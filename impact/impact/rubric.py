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
from .evidence import (
    Evidence,
    dispatch_episode_mentions,
    report_mentions,
    triage_episode_mentions,
)


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
