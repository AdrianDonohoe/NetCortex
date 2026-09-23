"""The rubric matrix: every factor combination maps to its grade."""

import json

import pytest

from helpers import CONFIG_JSON, UPGRADE_JSON
from impact.capture import CaptureState
from impact.change import parse_change
from impact.evidence import Evidence, ReportFile, ReportsState, StoreState
from impact.rubric import (
    BlastRadius,
    Criticality,
    HistoricalSignal,
    RiskGrade,
    blast_from_count,
    grade,
    grade_matrix,
)
from impact.plan import PlanState
from impact.specgraph import SpecGraphState

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


def _evidence(**overrides):
    defaults = dict(
        history=StoreState(None, exists=False),
        triage_episodes=StoreState(None, exists=False),
        dispatch_episodes=StoreState(None, exists=False),
        reports=ReportsState(None, exists=False),
        capture=CaptureState(None),
        specgraph=SpecGraphState(None),
        plan=PlanState(None),
    )
    return Evidence(**{**defaults, **overrides})


@pytest.mark.parametrize("outcome", ["rejected", "rolled-back"])
def test_grade_reads_a_failure_out_of_the_history_store(outcome):
    change = parse_change(json.loads(UPGRADE_JSON))
    history = StoreState(
        "changes.jsonl",
        (
            '{"change": {"type": "upgrade", "nf": "SMF", "from": "1.0", '
            '"to": "1.1"}, "outcome": "' + outcome + '"}',
        ),
    )
    rubric = grade(change, _evidence(history=history))
    assert rubric.grade is RiskGrade.HIGH
    factor = rubric.factors[0]
    assert factor.name == "historical evidence"
    assert "failed" in factor.finding
    assert factor.citation == "changes.jsonl:1"


def test_grade_an_applied_record_is_not_a_failure_match():
    change = parse_change(json.loads(UPGRADE_JSON))
    history = StoreState(
        "changes.jsonl",
        (
            '{"change": {"type": "upgrade", "nf": "SMF", "from": "1.0", '
            '"to": "1.1"}, "outcome": "applied"}',
        ),
    )
    rubric = grade(change, _evidence(history=history))
    assert rubric.grade is RiskGrade.INSUFFICIENT_EVIDENCE
    factor = rubric.factors[0]
    assert factor.name == "historical evidence"
    assert "no failed Change Records in Change History" in factor.finding


def test_grade_finds_nothing_in_empty_stores():
    change = parse_change(json.loads(UPGRADE_JSON))
    rubric = grade(
        change,
        _evidence(
            history=StoreState("changes.jsonl"),
            triage_episodes=StoreState("triage.jsonl"),
            dispatch_episodes=StoreState("dispatch.jsonl"),
        ),
    )
    assert rubric.grade is RiskGrade.INSUFFICIENT_EVIDENCE
    assert (
        rubric.factors[0].finding
        == "no failed Change Records in Change History; "
        "no Triage Episodes touch SMF; no Dispatch Episodes touch SMF; "
        "Post-incident reports not consulted"
    )
    assert (
        rubric.factors[0].citation
        == "changes.jsonl, triage.jsonl, dispatch.jsonl"
    )


def test_grade_episode_contact_cites_the_episode():
    change = parse_change(json.loads(UPGRADE_JSON))
    triage = StoreState(
        "triage.jsonl",
        (
            '{"incident_type": "sbi_nssf_reject", "narrative": "The Nnssf '
            'rejected the NSI request during SMF selection.", '
            '"cited_evidence": [{"message": "Nnssf_NSSelection", '
            '"cause": null, "ts": 1.0}], "created_at": "2026-08-18T00:00:00Z"}',
        ),
    )
    rubric = grade(change, _evidence(triage_episodes=triage))
    assert rubric.grade is RiskGrade.MEDIUM
    factor = rubric.factors[0]
    assert "past Episodes touch SMF: record 1 (sbi_nssf_reject)" in factor.finding
    assert factor.citation == "triage.jsonl:1"


def test_grade_report_contact_cites_path_and_line():
    change = parse_change(json.loads(UPGRADE_JSON))
    reports = ReportsState(
        "reports",
        (ReportFile("reports/one.md", ("The SMF melted.", "## Root cause")),),
    )
    rubric = grade(change, _evidence(reports=reports))
    assert rubric.grade is RiskGrade.MEDIUM
    factor = rubric.factors[0]
    assert "post-incident reports mention SMF: reports/one.md" in factor.finding
    assert factor.citation == "reports/one.md:1"


def _smf_capture(path="capture.json", n4_messages=None, sbi_messages=None):
    return CaptureState(
        path,
        n2={"flows": [], "unassociated": []},
        n4={
            "messages": n4_messages
            or [
                {
                    "ts": 1.0,
                    "name": "PFCP Association Setup Request",
                    "src_ip": "10.0.0.3",
                    "dst_ip": "10.0.0.4",
                }
            ],
            "procedures": [],
            "unpaired_requests": 0,
        },
        sbi={"messages": sbi_messages or [], "procedures": [], "unpaired_requests": 0},
    )


def _specgraph(nsmf):
    namf = {
        "id": "message:29518:5.2:Namf_Communication_N1N2MessageTransfer",
        "type": "message",
        "spec": "29518",
        "name": "Namf_Communication_N1N2MessageTransfer",
        "protocol": "SBI",
    }
    return SpecGraphState(
        "specgraph.json",
        entities=(nsmf, namf),
        edges=({"src": nsmf["id"], "dst": namf["id"], "kind": "co_mentioned"},),
    )


def test_grade_derives_blast_from_the_capture():
    change = parse_change(json.loads(UPGRADE_JSON))
    rubric = grade(change, _evidence(capture=_smf_capture()))
    assert rubric.grade is RiskGrade.INSUFFICIENT_EVIDENCE
    blast = rubric.factors[2]
    assert blast.name == "blast radius"
    assert blast.finding == "affects UPF (1 NF)"
    assert blast.citation == "capture.json:n4/messages/0"


def test_grade_wide_blast_from_an_sbi_peer():
    change = parse_change(json.loads(UPGRADE_JSON))
    capture = _smf_capture(
        sbi_messages=[
            {
                "ts": 2.0,
                "src_ip": "10.0.0.3",
                "dst_ip": "10.0.0.5",
                "direction": "request",
                "name": "Nnssf_NSSelection_Get",
            }
        ]
    )
    rubric = grade(change, _evidence(capture=capture))
    assert rubric.grade is RiskGrade.MEDIUM  # a wide blast radius
    blast = rubric.factors[2]
    assert blast.finding == "affects NSSF, UPF (2 NFs)"


def test_grade_unknown_peers_keep_the_blast_unknown():
    change = parse_change(json.loads(UPGRADE_JSON))
    capture = _smf_capture(
        sbi_messages=[
            {
                "ts": 2.0,
                "src_ip": "10.0.0.6",
                "dst_ip": "10.0.0.3",
                "direction": "request",
                "name": "Nsmf_PDUSession_CreateSMContext",
            }
        ]
    )
    rubric = grade(change, _evidence(capture=capture))
    assert rubric.grade is RiskGrade.INSUFFICIENT_EVIDENCE
    blast = rubric.factors[2]
    assert (
        blast.finding
        == "affects UPF (1 NF); 1 peer(s) with no determinable role"
    )


def test_grade_falls_back_to_the_specgraph_without_a_capture():
    change = parse_change(json.loads(UPGRADE_JSON))
    nsmf = {
        "id": "message:29502:8.2.2.2.2:Nsmf_PDUSession_CreateSMContext",
        "type": "message",
        "spec": "29502",
        "name": "Nsmf_PDUSession_CreateSMContext",
        "protocol": "SBI",
    }
    rubric = grade(change, _evidence(specgraph=_specgraph(nsmf)))
    blast = rubric.factors[2]
    assert blast.finding == (
        "affects AMF (1 NF) per specgraph references; "
        "no capture consulted"
    )
    assert blast.citation == (
        "specgraph.json:"
        "message:29518:5.2:Namf_Communication_N1N2MessageTransfer"
    )


def test_grade_a_missing_capture_with_specgraph_fallback_is_named():
    change = parse_change(json.loads(UPGRADE_JSON))
    nsmf = {
        "id": "message:29502:8.2.2.2.2:Nsmf_PDUSession_CreateSMContext",
        "type": "message",
        "spec": "29502",
        "name": "Nsmf_PDUSession_CreateSMContext",
        "protocol": "SBI",
    }
    capture = CaptureState("absent.json", exists=False)
    rubric = grade(
        change, _evidence(capture=capture, specgraph=_specgraph(nsmf))
    )
    blast = rubric.factors[2]
    assert blast.finding == (
        "affects AMF (1 NF) per specgraph references; "
        "capture absent.json does not exist"
    )


def test_grade_blast_not_determinable_with_no_capture_or_specgraph():
    change = parse_change(json.loads(UPGRADE_JSON))
    rubric = grade(change, _evidence())
    blast = rubric.factors[2]
    assert blast.finding == (
        "not determinable — no capture or specgraph evidence consulted"
    )
    assert blast.citation == "no capture or specgraph evidence consulted"


def test_grade_a_missing_capture_is_named_never_asserted_clear():
    change = parse_change(json.loads(UPGRADE_JSON))
    capture = CaptureState("absent.json", exists=False)
    rubric = grade(change, _evidence(capture=capture))
    blast = rubric.factors[2]
    assert blast.finding == (
        "not determinable — SMF has no determinable partners; "
        "absent.json does not exist"
    )
    assert blast.citation == "absent.json"


def test_grade_target_absent_from_the_capture_falls_back():
    change = parse_change(json.loads(UPGRADE_JSON))
    nsmf = {
        "id": "message:29502:8.2.2.2.2:Nsmf_PDUSession_CreateSMContext",
        "type": "message",
        "spec": "29502",
        "name": "Nsmf_PDUSession_CreateSMContext",
        "protocol": "SBI",
    }
    capture = CaptureState(
        "capture.json", n2={"flows": [], "unassociated": []}
    )
    rubric = grade(
        change, _evidence(capture=capture, specgraph=_specgraph(nsmf))
    )
    blast = rubric.factors[2]
    assert blast.finding == (
        "affects AMF (1 NF) per specgraph references; "
        "SMF not determinable in the capture"
    )


def test_grade_critical_interfaces_in_the_radius_grade_high():
    change = parse_change(json.loads(UPGRADE_JSON))
    capture = _smf_capture(
        sbi_messages=[
            {
                "ts": 2.0,
                "src_ip": "10.0.0.3",
                "dst_ip": "10.0.0.5",
                "direction": "request",
                "name": "Nudm_UEContextManagement",
            },
            {
                "ts": 2.1,
                "src_ip": "10.0.0.3",
                "dst_ip": "10.0.0.6",
                "direction": "request",
                "name": "Nausf_UEAuthentication",
            },
        ]
    )
    rubric = grade(change, _evidence(capture=capture))
    assert rubric.grade is RiskGrade.HIGH
    factor = rubric.factors[1]
    assert factor.name == "dependency criticality"
    assert factor.finding == (
        "critical interface Nudm_UEContextManagement, Nausf_UEAuthentication "
        "in the blast radius"
    )
    assert factor.citation == (
        "capture.json:sbi/messages/0, capture.json:sbi/messages/1"
    )


def test_grade_a_quiet_radius_is_non_critical():
    change = parse_change(json.loads(UPGRADE_JSON))
    rubric = grade(change, _evidence(capture=_smf_capture()))
    assert rubric.grade is RiskGrade.INSUFFICIENT_EVIDENCE
    factor = rubric.factors[1]
    assert factor.name == "dependency criticality"
    assert factor.finding == "no critical interface in the blast radius"
    assert factor.citation == "capture.json"


def test_grade_unknown_peers_keep_criticality_unknown():
    change = parse_change(json.loads(UPGRADE_JSON))
    capture = _smf_capture(
        sbi_messages=[
            {
                "ts": 2.0,
                "src_ip": "10.0.0.6",
                "dst_ip": "10.0.0.3",
                "direction": "request",
                "name": "Nsmf_PDUSession_CreateSMContext",
            }
        ]
    )
    rubric = grade(change, _evidence(capture=capture))
    assert rubric.grade is RiskGrade.INSUFFICIENT_EVIDENCE
    factor = rubric.factors[1]
    assert factor.finding == (
        "not determinable — 1 peer(s) with no determinable role could "
        "hide a critical interface"
    )
    assert factor.citation == "capture.json:sbi/messages/0"


def test_grade_a_critical_interface_beats_unknown_peers():
    change = parse_change(json.loads(UPGRADE_JSON))
    capture = _smf_capture(
        sbi_messages=[
            {
                "ts": 2.0,
                "src_ip": "10.0.0.6",
                "dst_ip": "10.0.0.3",
                "direction": "request",
                "name": "Nsmf_PDUSession_CreateSMContext",
            },
            {
                "ts": 2.1,
                "src_ip": "10.0.0.3",
                "dst_ip": "10.0.0.5",
                "direction": "request",
                "name": "Nudm_UEContextManagement",
            },
        ]
    )
    rubric = grade(change, _evidence(capture=capture))
    assert rubric.grade is RiskGrade.HIGH
    factor = rubric.factors[1]
    assert factor.finding == (
        "critical interface Nudm_UEContextManagement in the blast radius"
    )
    assert factor.citation == "capture.json:sbi/messages/1"


def test_grade_config_criticality_names_the_config_key():
    change = parse_change(json.loads(CONFIG_JSON))
    rubric = grade(change, _evidence())
    factor = rubric.factors[1]
    assert factor.finding == (
        "not determinable — the Change names a config key, "
        "not a network function"
    )
    assert factor.citation == "change record"


def test_grade_critical_specgraph_reference_grades_high():
    change = parse_change(json.loads(UPGRADE_JSON))
    nsmf = {
        "id": "message:29502:8.2.2.2.2:Nsmf_PDUSession_CreateSMContext",
        "type": "message",
        "spec": "29502",
        "name": "Nsmf_PDUSession_CreateSMContext",
        "protocol": "SBI",
    }
    rubric = grade(change, _evidence(specgraph=_specgraph(nsmf)))
    assert rubric.grade is RiskGrade.HIGH
    factor = rubric.factors[1]
    assert factor.finding == (
        "critical interface Namf_Communication_N1N2MessageTransfer "
        "in the blast radius"
    )
    assert factor.citation == (
        "specgraph.json:message:29518:5.2:Namf_Communication_N1N2MessageTransfer"
    )


def test_grade_quiet_specgraph_references_are_non_critical():
    change = parse_change(json.loads(UPGRADE_JSON))
    nsmf = {
        "id": "message:29502:8.2.2.2.2:Nsmf_PDUSession_CreateSMContext",
        "type": "message",
        "spec": "29502",
        "name": "Nsmf_PDUSession_CreateSMContext",
        "protocol": "SBI",
    }
    nnssf = {
        "id": "message:29531:x:Nnssf_NSSelection_Get",
        "type": "message",
        "spec": "29531",
        "name": "Nnssf_NSSelection_Get",
        "protocol": "SBI",
    }
    specgraph = SpecGraphState(
        "specgraph.json",
        entities=(nsmf, nnssf),
        edges=({"src": nsmf["id"], "dst": nnssf["id"], "kind": "co_mentioned"},),
    )
    rubric = grade(change, _evidence(specgraph=specgraph))
    assert rubric.grade is RiskGrade.INSUFFICIENT_EVIDENCE
    factor = rubric.factors[1]
    assert factor.finding == (
        "no critical interface per the specgraph references; "
        "no capture consulted"
    )
    assert factor.citation == (
        "specgraph.json:message:29531:x:Nnssf_NSSelection_Get"
    )


def test_grade_criticality_not_determinable_without_a_radius():
    change = parse_change(json.loads(UPGRADE_JSON))
    rubric = grade(change, _evidence())
    factor = rubric.factors[1]
    assert factor.finding == (
        "not determinable — no capture or specgraph evidence consulted"
    )
    assert factor.citation == "no capture or specgraph evidence consulted"


def test_grade_target_absent_from_the_capture_keeps_criticality_not_determinable():
    change = parse_change(json.loads(UPGRADE_JSON))
    capture = CaptureState("capture.json", n2={"flows": [], "unassociated": []})
    rubric = grade(change, _evidence(capture=capture))
    factor = rubric.factors[1]
    assert factor.finding == (
        "not determinable — no blast radius to scan in capture.json"
    )
    assert factor.citation == "capture.json"


def test_grade_a_missing_capture_keeps_criticality_not_determinable():
    change = parse_change(json.loads(UPGRADE_JSON))
    capture = CaptureState("absent.json", exists=False)
    rubric = grade(change, _evidence(capture=capture))
    factor = rubric.factors[1]
    assert factor.finding == (
        "not determinable — no blast radius to scan; "
        "absent.json does not exist"
    )
    assert factor.citation == "absent.json"


def test_grade_low_when_every_factor_is_determinable_and_quiet():
    change = parse_change(json.loads(UPGRADE_JSON))
    rubric = grade(
        change,
        _evidence(
            history=StoreState("changes.jsonl"),
            triage_episodes=StoreState("triage.jsonl"),
            dispatch_episodes=StoreState("dispatch.jsonl"),
            reports=ReportsState("reports"),
            capture=_smf_capture(),
        ),
    )
    assert rubric.grade is RiskGrade.LOW
    factor = rubric.factors[1]
    assert factor.finding == "no critical interface in the blast radius"
