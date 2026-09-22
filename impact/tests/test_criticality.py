"""Dependency criticality: recognizing and scanning for critical interfaces."""

import pytest

from impact.capture import AffectedNF, BlastResult, CaptureState, Role
from impact.criticality import CriticalHit, capture_hits, is_critical, specgraph_hits
from impact.specgraph import RefPartner, SpecGraphState


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Nudm_UEContextManagement", True),
        ("Nausf_UEAuthentication", True),
        ("Namf_Communication_N1N2MessageTransfer", True),
        ("Nsmf_PDUSession_CreateSMContext", False),
        ("Nnssf_NSSelection_Get", False),
        ("Namf_Communication_EBIAssignment", False),
        ("PFCP Association Setup Request", False),
    ],
)
def test_is_critical(name, expected):
    assert is_critical(name) is expected


def _capture():
    return CaptureState(
        "capture.json",
        n2={"flows": [], "unassociated": []},
        n4={
            "messages": [
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
        sbi={
            "messages": [
                {
                    "ts": 2.0,
                    "name": "Nsmf_PDUSession_CreateSMContext",
                    "src_ip": "10.0.0.2",
                    "dst_ip": "10.0.0.3",
                },
                {
                    "ts": 3.0,
                    "name": "Nudm_UEContextManagement",
                    "src_ip": "10.0.0.3",
                    "dst_ip": "10.0.0.6",
                },
                {
                    "ts": 4.0,
                    "name": "Nausf_UEAuthentication",
                    "src_ip": "10.0.0.3",
                    "dst_ip": "10.0.0.7",
                },
            ],
            "procedures": [],
            "unpaired_requests": 0,
        },
    )


def test_capture_hits_find_critical_interfaces_at_the_evidence_pointers():
    result = BlastResult(
        Role("SMF", "10.0.0.3", "n4/messages/0"),
        (
            AffectedNF(role="AUSF", ip="10.0.0.7", evidence="sbi/messages/2"),
            AffectedNF(role="UDM", ip="10.0.0.6", evidence="sbi/messages/1"),
            AffectedNF(role="AMF", ip="10.0.0.2", evidence="sbi/messages/0"),
        ),
        0,
        (),
    )
    assert capture_hits(_capture(), result) == (
        CriticalHit("Nudm_UEContextManagement", "sbi/messages/1"),
        CriticalHit("Nausf_UEAuthentication", "sbi/messages/2"),
    )


def test_capture_hits_scan_the_targets_own_evidence_pointer():
    result = BlastResult(
        Role("SMF", "10.0.0.3", "sbi/messages/1"),
        (),
        0,
        (),
    )
    assert capture_hits(_capture(), result) == (
        CriticalHit("Nudm_UEContextManagement", "sbi/messages/1"),
    )


def test_capture_hits_a_quiet_radius_is_empty():
    result = BlastResult(
        Role("SMF", "10.0.0.3", "n4/messages/0"),
        (AffectedNF(role="AMF", ip="10.0.0.2", evidence="sbi/messages/0"),),
        0,
        (),
    )
    assert capture_hits(_capture(), result) == ()


def test_capture_hits_without_a_located_target_is_empty():
    assert capture_hits(_capture(), BlastResult(None, (), 0, ())) == ()


def _specgraph():
    namf = {
        "id": "message:29518:5.2:Namf_Communication_N1N2MessageTransfer",
        "type": "message",
        "spec": "29518",
        "name": "Namf_Communication_N1N2MessageTransfer",
        "protocol": "SBI",
    }
    nnssf = {
        "id": "message:29531:x:Nnssf_NSSelection_Get",
        "type": "message",
        "spec": "29531",
        "name": "Nnssf_NSSelection_Get",
        "protocol": "SBI",
    }
    return SpecGraphState(
        "specgraph.json",
        entities=(namf, nnssf),
        edges=(),
    )


def test_specgraph_hits_resolve_reference_ids_to_entity_names():
    partners = (
        RefPartner("AMF", ("message:29518:5.2:Namf_Communication_N1N2MessageTransfer",)),
        RefPartner("NSSF", ("message:29531:x:Nnssf_NSSelection_Get",)),
    )
    assert specgraph_hits(_specgraph(), partners) == (
        CriticalHit(
            "Namf_Communication_N1N2MessageTransfer",
            "message:29518:5.2:Namf_Communication_N1N2MessageTransfer",
        ),
    )


def test_specgraph_hits_skip_ids_the_state_does_not_hold():
    partners = (RefPartner("AMF", ("message:unknown",)),)
    assert specgraph_hits(_specgraph(), partners) == ()
