"""The capture-derived blast radius: roles, partners, per-NF evidence."""

import json

from impact.capture import (
    AffectedNF,
    BlastResult,
    CaptureState,
    Role,
    blast_radius,
    infer_roles,
    message_at,
)
from impact.change import parse_change
from helpers import UPGRADE_JSON


def _capture(**overrides):
    """A capture state the way the loader produces one: the merged n2
    export with its embedded planes extracted into the state fields."""
    n2 = {
        "kpis": {"attach_time_ms": 400.0},
        "flows": [],
        "unassociated": [],
    }
    merged = json.loads(json.dumps({**n2, **overrides}))
    return CaptureState(
        "n2.json",
        n2=merged,
        n4=merged.get("n4") if isinstance(merged.get("n4"), dict) else None,
        sbi=merged.get("sbi") if isinstance(merged.get("sbi"), dict) else None,
    )


def _msg(name, src, dst, **extra):
    return {"ts": 1.0, "name": name, "src_ip": src, "dst_ip": dst, **extra}


def test_blast_result_proximity_is_target_partner_or_outsider():
    result = BlastResult(
        Role("SMF", "10.0.0.3", "n4/messages/0"),
        (AffectedNF("UPF", "10.0.0.4", "n4/messages/0"),),
        0,
        (),
    )
    assert result.proximity_of("smf") == 0
    assert result.proximity_of("UPF") == 1
    assert result.proximity_of("AMF") is None
    assert BlastResult(None, (), 0, ()).proximity_of("SMF") is None


def test_gnb_amf_from_the_first_initial_ue_message():
    capture = _capture(
        flows=[
            {
                "flow_id": 0,
                "partial": False,
                "messages": [_msg("InitialUEMessage", "10.0.0.1", "10.0.0.2")],
                "procedures": [],
            }
        ]
    )
    roles = infer_roles(capture)
    assert Role("gNB", "10.0.0.1", "flows/0/messages/0") in roles
    assert Role("AMF", "10.0.0.2", "flows/0/messages/0") in roles


def test_smf_upf_from_pfcp_association_setup():
    capture = _capture(
        n4={
            "messages": [_msg("PFCP Association Setup Request", "10.0.0.3", "10.0.0.4")],
            "procedures": [],
            "unpaired_requests": 0,
        }
    )
    roles = infer_roles(capture)
    assert Role("SMF", "10.0.0.3", "n4/messages/0") in roles
    assert Role("UPF", "10.0.0.4", "n4/messages/0") in roles


def test_message_at_resolves_capture_pointers():
    capture = _smf_upf_capture(
        sbi={
            "messages": [
                {
                    "ts": 2.0,
                    "src_ip": "10.0.0.2",
                    "dst_ip": "10.0.0.3",
                    "direction": "request",
                    "name": "Nsmf_PDUSession_CreateSMContext",
                }
            ],
            "procedures": [],
            "unpaired_requests": 0,
        }
    )
    assert message_at(capture, "n4/messages/0")["name"] == (
        "PFCP Session Establishment Request"
    )
    assert message_at(capture, "sbi/messages/0")["name"] == (
        "Nsmf_PDUSession_CreateSMContext"
    )
    assert message_at(capture, "flows/0/messages/0")["name"] == "InitialUEMessage"


def test_message_at_returns_none_for_pointers_that_do_not_resolve():
    capture = _capture()
    assert message_at(capture, "sbi/messages/9") is None
    assert message_at(capture, "flows/9/messages/0") is None
    assert message_at(capture, "sbi/procedures/0") is None


def test_sbi_producer_role_from_the_service_family():
    capture = _capture(
        sbi={
            "messages": [
                {
                    "ts": 1.0,
                    "src_ip": "10.0.0.3",
                    "dst_ip": "10.0.0.5",
                    "direction": "request",
                    "name": "Nnssf_NSSelection_Get",
                }
            ],
            "procedures": [],
            "unpaired_requests": 0,
        }
    )
    roles = infer_roles(capture)
    assert Role("NSSF", "10.0.0.5", "sbi/messages/0") in roles


def test_unprovable_roles_are_absent_not_guessed():
    capture = _capture()
    assert infer_roles(capture) == ()


def _smf_upf_capture(**sbi):
    capture = _capture(
        flows=[
            {
                "flow_id": 0,
                "partial": False,
                "messages": [
                    _msg("InitialUEMessage", "10.0.0.1", "10.0.0.2"),
                    _msg("RegistrationRequest", "10.0.0.1", "10.0.0.2"),
                ],
                "procedures": [
                    {
                        "kind": "registration",
                        "start_msg": "RegistrationRequest",
                        "end_msg": "RegistrationAccept",
                        "outcome": "accept",
                        "duration_ms": 120.0,
                    }
                ],
            }
        ],
        n4={
            "messages": [
                _msg("PFCP Session Establishment Request", "10.0.0.3", "10.0.0.4"),
                _msg("PFCP Session Establishment Response", "10.0.0.4", "10.0.0.3"),
            ],
            "procedures": [
                {
                    "kind": "pfcp session establishment",
                    "start_msg": "PFCP Session Establishment Request",
                    "end_msg": "PFCP Session Establishment Response",
                    "outcome": "accept",
                    "duration_ms": 8.5,
                }
            ],
            "unpaired_requests": 0,
        },
        **sbi,
    )
    return capture


def test_smf_blast_radius_is_the_peers_touching_its_ip():
    capture = _smf_upf_capture()
    result = blast_radius(parse_change(json.loads(UPGRADE_JSON)), capture)
    assert result.target == Role("SMF", "10.0.0.3", "n4/messages/0")
    assert [(nf.role, nf.ip) for nf in result.affected] == [("UPF", "10.0.0.4")]
    assert result.unknown_peers == 0
    upf = result.affected[0]
    assert upf.procedures[0].pointer == "n4/procedures/0"
    assert upf.kpis.count == 1
    assert upf.kpis.successes == 1
    assert upf.kpis.failures == 0


def test_sbi_peers_join_the_radius_by_their_roles():
    capture = _smf_upf_capture(
        sbi={
            "messages": [
                {
                    "ts": 2.0,
                    "src_ip": "10.0.0.3",
                    "dst_ip": "10.0.0.5",
                    "direction": "request",
                    "name": "Nnssf_NSSelection_Get",
                }
            ],
            "procedures": [],
            "unpaired_requests": 0,
        }
    )
    result = blast_radius(parse_change(json.loads(UPGRADE_JSON)), capture)
    assert sorted(nf.role for nf in result.affected) == ["NSSF", "UPF"]


def test_a_peer_with_no_role_keeps_the_count_unknown():
    capture = _smf_upf_capture(
        sbi={
            "messages": [
                {
                    "ts": 2.0,
                    "src_ip": "10.0.0.6",
                    "dst_ip": "10.0.0.3",
                    "direction": "request",
                    "name": "Nsmf_PDUSession_CreateSMContext",
                }
            ],
            "procedures": [],
            "unpaired_requests": 0,
        }
    )
    result = blast_radius(parse_change(json.loads(UPGRADE_JSON)), capture)
    assert result.unknown_peers == 1
    assert result.unknown_peer_pointers == ("sbi/messages/0",)


def test_target_not_in_the_capture_is_honest():
    capture = _capture()
    result = blast_radius(parse_change(json.loads(UPGRADE_JSON)), capture)
    assert result == BlastResult(None, (), 0, ())


def test_n2_procedures_attribute_to_the_roles_on_their_flow():
    capture = _smf_upf_capture()
    change = parse_change(
        json.loads(UPGRADE_JSON.replace('"SMF"', '"AMF"'))
    )
    result = blast_radius(change, capture)
    assert result.target.role == "AMF"
    assert sorted(nf.role for nf in result.affected) == ["gNB"]
    gnb = result.affected[0]
    assert gnb.procedures[0].pointer == "flows/0/procedures/0"
    assert gnb.procedures[0].kind == "registration"


def test_per_nf_kpis_count_accept_and_reject():
    capture = _smf_upf_capture()
    capture.n4["procedures"].append(
        {
            "kind": "pfcp session establishment",
            "start_msg": "PFCP Session Establishment Request",
            "end_msg": "PFCP Session Establishment Response",
            "outcome": "reject",
            "duration_ms": 3.0,
        }
    )
    result = blast_radius(parse_change(json.loads(UPGRADE_JSON)), capture)
    upf = result.affected[0]
    assert upf.kpis.count == 2
    assert upf.kpis.successes == 1
    assert upf.kpis.failures == 1


def test_sbi_procedures_attribute_through_flow_correlation():
    capture = _smf_upf_capture(
        sbi={
            "messages": [
                {
                    "ts": 2.0,
                    "src_ip": "10.0.0.2",
                    "dst_ip": "10.0.0.3",
                    "direction": "request",
                    "name": "Nsmf_PDUSession_CreateSMContext",
                },
                {
                    "ts": 2.1,
                    "src_ip": "10.0.0.3",
                    "dst_ip": "10.0.0.2",
                    "direction": "response",
                    "name": "Nsmf_PDUSession_CreateSMContext",
                },
            ],
            "procedures": [
                {
                    "kind": "pdu session establishment",
                    "start_msg": "Nsmf_PDUSession_CreateSMContext",
                    "end_msg": "Nsmf_PDUSession_CreateSMContext",
                    "outcome": "accept",
                    "duration_ms": 30.0,
                    "flow_id": 0,
                }
            ],
            "unpaired_requests": 0,
        }
    )
    capture.n2["flows"][0]["sbi_refs"] = [0]
    result = blast_radius(parse_change(json.loads(UPGRADE_JSON)), capture)
    amf = next(nf for nf in result.affected if nf.role == "AMF")
    assert "sbi/procedures/0" in [p.pointer for p in amf.procedures]
