"""The rubric matrix: every factor combination maps to its grade."""

import json

import pytest

from helpers import UPGRADE_JSON
from impact.change import parse_change
from impact.evidence import Evidence, StoreState
from impact.rubric import (
    BlastRadius,
    Criticality,
    HistoricalSignal,
    RiskGrade,
    blast_from_count,
    grade,
    grade_matrix,
)

HIST_FAIL, HIST_CONTACT, HIST_NONE, HIST_UNKNOWN = (
    HistoricalSignal.FAILURE_MATCH,
    HistoricalSignal.CONTACT,
    HistoricalSignal.NONE,
    HistoricalSignal.UNKNOWN,
)
CRIT, NONCRIT, CRIT_UNKNOWN = (
    Criticality.CRITICAL,
    Criticality.NON_CRITICAL,
    Criticality.UNKNOWN,
)
WIDE, NARROW, BLAST_UNKNOWN = (
    BlastRadius.WIDE,
    BlastRadius.NARROW,
    BlastRadius.UNKNOWN,
)
HIGH, MEDIUM, LOW, INSUFFICIENT = (
    RiskGrade.HIGH,
    RiskGrade.MEDIUM,
    RiskGrade.LOW,
    RiskGrade.INSUFFICIENT_EVIDENCE,
)

# The full matrix, one row per factor combination: a failure match or a
# critical interface → HIGH; Episode contact or a wide blast radius →
# MEDIUM; all three factors determinable and quiet → LOW; anything
# unknown with no signal firing → INSUFFICIENT EVIDENCE.
CASES = [
    # a failure match grades HIGH whatever else is known
    (HIST_FAIL, CRIT, WIDE, HIGH), (HIST_FAIL, CRIT, NARROW, HIGH),
    (HIST_FAIL, CRIT, BLAST_UNKNOWN, HIGH),
    (HIST_FAIL, NONCRIT, WIDE, HIGH), (HIST_FAIL, NONCRIT, NARROW, HIGH),
    (HIST_FAIL, NONCRIT, BLAST_UNKNOWN, HIGH),
    (HIST_FAIL, CRIT_UNKNOWN, WIDE, HIGH),
    (HIST_FAIL, CRIT_UNKNOWN, NARROW, HIGH),
    (HIST_FAIL, CRIT_UNKNOWN, BLAST_UNKNOWN, HIGH),
    # a critical interface grades HIGH whatever else is known
    (HIST_CONTACT, CRIT, WIDE, HIGH), (HIST_CONTACT, CRIT, NARROW, HIGH),
    (HIST_CONTACT, CRIT, BLAST_UNKNOWN, HIGH),
    (HIST_NONE, CRIT, WIDE, HIGH), (HIST_NONE, CRIT, NARROW, HIGH),
    (HIST_NONE, CRIT, BLAST_UNKNOWN, HIGH),
    (HIST_UNKNOWN, CRIT, WIDE, HIGH), (HIST_UNKNOWN, CRIT, NARROW, HIGH),
    (HIST_UNKNOWN, CRIT, BLAST_UNKNOWN, HIGH),
    # Episode contact grades MEDIUM
    (HIST_CONTACT, NONCRIT, WIDE, MEDIUM),
    (HIST_CONTACT, NONCRIT, NARROW, MEDIUM),
    (HIST_CONTACT, NONCRIT, BLAST_UNKNOWN, MEDIUM),
    (HIST_CONTACT, CRIT_UNKNOWN, WIDE, MEDIUM),
    (HIST_CONTACT, CRIT_UNKNOWN, NARROW, MEDIUM),
    (HIST_CONTACT, CRIT_UNKNOWN, BLAST_UNKNOWN, MEDIUM),
    # a wide blast radius grades MEDIUM
    (HIST_NONE, NONCRIT, WIDE, MEDIUM),
    (HIST_NONE, CRIT_UNKNOWN, WIDE, MEDIUM),
    (HIST_UNKNOWN, NONCRIT, WIDE, MEDIUM),
    (HIST_UNKNOWN, CRIT_UNKNOWN, WIDE, MEDIUM),
    # all three factors determinable and quiet grades LOW
    (HIST_NONE, NONCRIT, NARROW, LOW),
    # anything unknown with no signal firing grades INSUFFICIENT EVIDENCE
    (HIST_NONE, NONCRIT, BLAST_UNKNOWN, INSUFFICIENT),
    (HIST_NONE, CRIT_UNKNOWN, NARROW, INSUFFICIENT),
    (HIST_NONE, CRIT_UNKNOWN, BLAST_UNKNOWN, INSUFFICIENT),
    (HIST_UNKNOWN, NONCRIT, NARROW, INSUFFICIENT),
    (HIST_UNKNOWN, NONCRIT, BLAST_UNKNOWN, INSUFFICIENT),
    (HIST_UNKNOWN, CRIT_UNKNOWN, NARROW, INSUFFICIENT),
    (HIST_UNKNOWN, CRIT_UNKNOWN, BLAST_UNKNOWN, INSUFFICIENT),
]


@pytest.mark.parametrize(("history", "criticality", "blast", "expected"), CASES)
def test_matrix(history, criticality, blast, expected):
    assert grade_matrix(history, criticality, blast) is expected


@pytest.mark.parametrize(
    ("n_affected", "expected"),
    [(None, BLAST_UNKNOWN), (0, NARROW), (1, NARROW), (2, WIDE), (5, WIDE)],
)
def test_blast_from_count(n_affected, expected):
    assert blast_from_count(n_affected) is expected


def test_grade_reads_a_failure_out_of_the_history_store():
    change = parse_change(json.loads(UPGRADE_JSON))
    history = StoreState(
        "changes.jsonl",
        (
            '{"change": {"type": "upgrade", "nf": "SMF", "from": "1.0", '
            '"to": "1.1"}, "outcome": "failed"}',
        ),
    )
    evidence = Evidence(history=history, episodes=StoreState(None, exists=False))
    rubric = grade(change, evidence)
    assert rubric.grade is RiskGrade.HIGH
    factor = rubric.factors[0]
    assert factor.name == "historical evidence"
    assert "failed" in factor.finding
    assert factor.citation == "changes.jsonl:1"


def test_grade_finds_nothing_in_empty_stores():
    change = parse_change(json.loads(UPGRADE_JSON))
    evidence = Evidence(
        history=StoreState("changes.jsonl"),
        episodes=StoreState("episodes.jsonl"),
    )
    rubric = grade(change, evidence)
    assert rubric.grade is RiskGrade.INSUFFICIENT_EVIDENCE
    assert (
        rubric.factors[0].finding
        == "no failed Change Records in Change History; "
        "no Episodes touch SMF"
    )
    assert rubric.factors[0].citation == "changes.jsonl, episodes.jsonl"
