"""The risk rubric: computed in code, never by the LLM.

Three factors — historical evidence, dependency criticality, blast
radius — map to four grades, and every factor carries its citation.
An unknowable risk never grades LOW: with no evidence to apply the
rubric to, the grade is INSUFFICIENT EVIDENCE.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .evidence import Evidence


class RiskGrade(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT EVIDENCE"


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


def grade(evidence: Evidence) -> Rubric:
    """Grade the Change from the evidence at hand.

    With no evidence at all the rubric cannot be applied, and the grade
    says so — INSUFFICIENT EVIDENCE, never LOW. The full matrix lands
    with the rubric ticket.
    """
    if evidence.empty:
        return Rubric(
            RiskGrade.INSUFFICIENT_EVIDENCE,
            (
                Factor(
                    "historical evidence",
                    "none available",
                    "no Change Records and no Episodes consulted",
                ),
                Factor(
                    "dependency criticality",
                    "not determinable",
                    "no capture evidence to derive dependencies from",
                ),
                Factor(
                    "blast radius",
                    "not determinable",
                    "no capture evidence to derive the affected "
                    "Procedures and KPIs from",
                ),
            ),
        )
    raise NotImplementedError("the rubric matrix lands with the rubric ticket")
