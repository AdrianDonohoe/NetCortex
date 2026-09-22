"""The Impact Report: the golden seam and the cited-vs-predicted honesty hook."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import CONFIG, UPGRADE
from impact.report import Claim, UnmarkedClaimError

REPO = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
TRIAGE = FIXTURES / "triage_episodes.jsonl"
DISPATCH = FIXTURES / "dispatch_episodes.jsonl"
REPORTS = FIXTURES / "reports"
CAPTURE = FIXTURES / "capture_n2.json"
CAPTURE_N4 = FIXTURES / "capture_n4_only.json"
CAPTURE_UNKNOWN = FIXTURES / "capture_unknown_peer.json"
CAPTURE_CRITICAL = FIXTURES / "capture_critical.json"
SPECGRAPH = FIXTURES / "specgraph.json"
PLAN = FIXTURES / "plan.json"

SECTION_HEADINGS = (
    "## CHANGE RISK: INSUFFICIENT EVIDENCE",
    "## Affected Network Functions",
    "## Historical Evidence",
    "## Recommended Pre-Checks",
    "## Rollback Criteria",
)


def _assess(tmp_path, change, *flags):
    record = tmp_path / "change.json"
    if isinstance(change, str):
        record.write_text(change)
    else:
        record.write_text(json.dumps(change))
    return subprocess.run(
        [sys.executable, "-m", "impact.cli", "assess", str(record), *flags],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def _non_heading_lines(report):
    return [
        line
        for line in report.splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _assert_marker_discipline(report):
    for line in _non_heading_lines(report):
        markers = line.count("[cited: ") + line.count("[predicted]")
        assert markers == 1, f"marker discipline broken on: {line!r}"


def test_empty_evidence_renders_the_full_report(tmp_path):
    proc = _assess(tmp_path, UPGRADE)
    assert proc.returncode == 0, proc.stderr
    for heading in SECTION_HEADINGS:
        assert heading in proc.stdout
    assert "SMF — the Change's own target" in proc.stdout


def test_every_claim_line_carries_exactly_one_marker(tmp_path):
    proc = _assess(tmp_path, UPGRADE)
    assert proc.returncode == 0, proc.stderr
    _assert_marker_discipline(proc.stdout)


def test_config_change_renders_honestly(tmp_path):
    proc = _assess(tmp_path, CONFIG)
    assert proc.returncode == 0, proc.stderr
    assert "config udm.sbi.uri udm-1 → udm-2" in proc.stdout
    for heading in SECTION_HEADINGS:
        assert heading in proc.stdout
    assert (
        "No NFs determinable — the Change names a config key, "
        "not a network function" in proc.stdout
    )
    assert "the Change's own target" not in proc.stdout


def test_malformed_change_is_refused_nothing_renders(tmp_path):
    proc = _assess(tmp_path, '{"type": "patch"}')
    assert proc.returncode == 1
    assert "unknown change type" in proc.stderr
    assert proc.stdout == ""


def test_missing_store_is_reported_as_missing(tmp_path):
    absent = tmp_path / "absent.jsonl"
    proc = _assess(tmp_path, UPGRADE, "--history-path", str(absent))
    assert proc.returncode == 0, proc.stderr
    assert f"{absent} does not exist" in proc.stdout
    assert "## CHANGE RISK: INSUFFICIENT EVIDENCE" in proc.stdout


def test_empty_stores_are_named_honestly(tmp_path):
    empty = tmp_path / "changes.jsonl"
    empty.write_text("")
    proc = _assess(tmp_path, UPGRADE, "--history-path", str(empty))
    assert proc.returncode == 0, proc.stderr
    assert f"{empty} is empty" in proc.stdout
    # the factor names only what was actually read
    assert (
        "no failed Change Records in Change History; Triage Episodes not "
        "consulted; Dispatch Episodes not consulted; Post-incident reports "
        "not consulted" in proc.stdout
    )


def test_triage_episode_renders_with_record_and_breakage(tmp_path):
    proc = _assess(tmp_path, UPGRADE, "--triage-episodes", str(TRIAGE))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: MEDIUM" in proc.stdout
    assert (
        "past Episodes touch SMF: record 1 (sbi_nssf_reject)" in proc.stdout
    )
    assert f"{TRIAGE}:1" in proc.stdout
    assert (
        "Episode record 1 (sbi_nssf_reject): The Nnssf rejected the NSI "
        "request during SMF selection because no slice instance matched "
        "the requested S-NSSAI." in proc.stdout
    )
    _assert_marker_discipline(proc.stdout)


def test_dispatch_episode_renders_with_incident_id_and_breakage(tmp_path):
    proc = _assess(tmp_path, UPGRADE, "--dispatch-episodes", str(DISPATCH))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: MEDIUM" in proc.stdout
    assert "past Episodes touch SMF: inc-kpi-551cb5b7" in proc.stdout
    assert f"{DISPATCH}:1" in proc.stdout
    assert (
        "Episode inc-kpi-551cb5b7: The SMF crashed after the PFCP "
        "association loss; a restart resolved it." in proc.stdout
    )
    _assert_marker_discipline(proc.stdout)


def test_post_incident_report_mention_renders_and_contacts(tmp_path):
    proc = _assess(tmp_path, UPGRADE, "--reports", str(REPORTS))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: MEDIUM" in proc.stdout
    report = REPORTS / "triage-2026-09-04-sbi-nssf-reject.md"
    assert f"Post-incident report {report} mentions SMF" in proc.stdout
    assert f"{report}:3" in proc.stdout  # the mention is grounded by line
    _assert_marker_discipline(proc.stdout)


def test_reports_flag_given_a_file_is_never_asserted_clear(tmp_path):
    one_report = tmp_path / "one.md"
    one_report.write_text("# Post-incident report\n\nThe SMF melted.\n")
    proc = _assess(tmp_path, UPGRADE, "--reports", str(one_report))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: INSUFFICIENT EVIDENCE" in proc.stdout
    assert f"{one_report} is not a directory" in proc.stdout
    assert "no post-incident reports mention SMF" not in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_unreadable_report_is_named_never_asserted_clear(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "clean.md").write_text("# Post-incident report\n\nNothing here.\n")
    (reports / "secret.md").write_text("The SMF melted.\n")
    (reports / "secret.md").chmod(0o000)
    proc = _assess(tmp_path, UPGRADE, "--reports", str(reports))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: INSUFFICIENT EVIDENCE" in proc.stdout
    assert f"{reports} holds 1 report; 1 unreadable" in proc.stdout
    assert "no post-incident reports mention SMF" not in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_narrative_newline_cannot_forge_structure(tmp_path):
    triage = tmp_path / "triage.jsonl"
    triage.write_text(
        json.dumps(
            {
                "incident_type": "smf_x",
                "narrative": "SMF broke\n## forged heading",
                "cited_evidence": [],
                "created_at": "2026-08-18T00:00:00Z",
            }
        )
        + "\n"
    )
    proc = _assess(tmp_path, UPGRADE, "--triage-episodes", str(triage))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: MEDIUM" in proc.stdout
    assert not any(
        line.startswith("## forged heading") for line in proc.stdout.splitlines()
    )
    _assert_marker_discipline(proc.stdout)


def test_corrupt_store_lines_are_skipped_not_fatal(tmp_path):
    proc = _assess(
        tmp_path, UPGRADE,
        "--triage-episodes", str(TRIAGE),
        "--dispatch-episodes", str(DISPATCH),
    )
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: MEDIUM" in proc.stdout
    assert "record 1 (sbi_nssf_reject)" in proc.stdout
    assert "inc-kpi-551cb5b7" in proc.stdout
    # the corrupt lines mention SMF but are skipped, not rendered
    assert "smf_overload" not in proc.stdout
    assert "inc-smf-junk" not in proc.stdout


def test_success_record_keeps_evidence_insufficient(tmp_path):
    history = tmp_path / "changes.jsonl"
    history.write_text(json.dumps({"change": UPGRADE, "outcome": "success"}) + "\n")
    proc = _assess(tmp_path, UPGRADE, "--history-path", str(history))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: INSUFFICIENT EVIDENCE" in proc.stdout
    assert (
        "no failed Change Records in Change History; Triage Episodes not "
        "consulted; Dispatch Episodes not consulted; Post-incident reports "
        "not consulted" in proc.stdout
    )
    assert f"[cited: {history}]" in proc.stdout


def test_bare_claims_are_refused():
    with pytest.raises(UnmarkedClaimError):
        Claim(text="something true").render()
    assert Claim(text="a guess", predicted=True).render() == "a guess [predicted]"
    assert (
        Claim(text="a fact", source="change record").render()
        == "a fact [cited: change record]"
    )


def test_capture_derives_affected_nfs_with_procedures_and_kpis(tmp_path):
    proc = _assess(tmp_path, UPGRADE, "--capture", str(CAPTURE))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: MEDIUM" in proc.stdout
    assert "affects AMF, NSSF, UPF (3 NFs)" in proc.stdout
    assert f"- AMF [cited: {CAPTURE}:flows/0/messages/0]" in proc.stdout
    assert f"- NSSF [cited: {CAPTURE}:sbi/messages/2]" in proc.stdout
    assert f"- UPF [cited: {CAPTURE}:n4/messages/0]" in proc.stdout
    assert (
        f"Procedure pdu session establishment, outcome accept "
        f"[cited: {CAPTURE}:sbi/procedures/0]" in proc.stdout
    )
    assert (
        f"KPI procedures=3, accept=3, reject=0 [cited: {CAPTURE}:flows/0/"
        f"procedures/0, {CAPTURE}:flows/1/procedures/0, {CAPTURE}:sbi/"
        f"procedures/0]" in proc.stdout
    )
    assert (
        f"KPI procedures=2, accept=1, reject=1 [cited: {CAPTURE}:n4/"
        f"procedures/0, {CAPTURE}:n4/procedures/1]" in proc.stdout
    )
    assert (
        f"no Procedures or KPIs derivable [cited: {CAPTURE}:sbi/messages/2]"
        in proc.stdout
    )
    _assert_marker_discipline(proc.stdout)


def test_n4_only_capture_grades_the_radius_narrow(tmp_path):
    proc = _assess(tmp_path, UPGRADE, "--capture", str(CAPTURE_N4))
    assert proc.returncode == 0, proc.stderr
    assert "blast radius: affects UPF (1 NF)" in proc.stdout
    assert "## CHANGE RISK: INSUFFICIENT EVIDENCE" in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_unroleable_peer_keeps_the_radius_unknown(tmp_path):
    proc = _assess(tmp_path, UPGRADE, "--capture", str(CAPTURE_UNKNOWN))
    assert proc.returncode == 0, proc.stderr
    assert (
        "blast radius: affects UPF (1 NF); 1 peer(s) with no determinable "
        "role" in proc.stdout
    )
    assert (
        f"1 peer(s) with no determinable role "
        f"[cited: {CAPTURE_UNKNOWN}:sbi/messages/0]" in proc.stdout
    )
    assert "## CHANGE RISK: INSUFFICIENT EVIDENCE" in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_specgraph_falls_back_when_no_capture_covers_the_network(tmp_path):
    proc = _assess(tmp_path, UPGRADE, "--specgraph", str(SPECGRAPH))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: HIGH" in proc.stdout
    assert (
        "dependency criticality: critical interface "
        "Namf_Communication_N1N2MessageTransfer in the blast radius "
        f"[cited: {SPECGRAPH}:message:29518:5.2.2.2.2:"
        "Namf_Communication_N1N2MessageTransfer]" in proc.stdout
    )
    assert (
        "blast radius: affects AMF (1 NF) per specgraph references; "
        "no capture consulted" in proc.stdout
    )
    assert f"no capture consulted; specgraph reference points [cited: {SPECGRAPH}]" in proc.stdout
    assert (
        f"Service operation Nsmf_PDUSession_CreateSMContext "
        f"[cited: {SPECGRAPH}:message:29502:8.2.2.2.2:Nsmf_"
        f"PDUSession_CreateSMContext]" in proc.stdout
    )
    assert (
        f"AMF — reference dependency [cited: {SPECGRAPH}:"
        f"message:29518:5.2.2.2.2:Namf_Communication_N1N2MessageTransfer]"
        in proc.stdout
    )
    assert (
        f"None — no KPI watch points derivable from the evidence "
        f"consulted. [cited: {SPECGRAPH}]" in proc.stdout
    )
    _assert_marker_discipline(proc.stdout)


def test_missing_capture_with_specgraph_names_the_capture(tmp_path):
    absent = tmp_path / "absent.json"
    proc = _assess(
        tmp_path, UPGRADE, "--capture", str(absent), "--specgraph", str(SPECGRAPH)
    )
    assert proc.returncode == 0, proc.stderr
    assert (
        "blast radius: affects AMF (1 NF) per specgraph references; "
        f"capture {absent} does not exist" in proc.stdout
    )
    assert (
        f"capture {absent} does not exist; specgraph reference points"
        in proc.stdout
    )
    assert "no capture consulted" not in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_target_absent_from_the_capture_falls_back_to_the_specgraph(tmp_path):
    capture = tmp_path / "n2.json"
    capture.write_text(json.dumps({"flows": [], "unassociated": []}))
    proc = _assess(
        tmp_path, UPGRADE, "--capture", str(capture), "--specgraph", str(SPECGRAPH)
    )
    assert proc.returncode == 0, proc.stderr
    assert "SMF not determinable in the capture" in proc.stdout
    assert "AMF — reference dependency" in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_malformed_capture_is_refused_nothing_renders(tmp_path):
    capture = tmp_path / "bad.json"
    capture.write_text("{not json")
    proc = _assess(tmp_path, UPGRADE, "--capture", str(capture))
    assert proc.returncode == 1
    assert "error:" in proc.stderr
    assert proc.stdout == ""


def test_missing_capture_is_named_never_asserted_clear(tmp_path):
    absent = tmp_path / "absent.json"
    proc = _assess(tmp_path, UPGRADE, "--capture", str(absent))
    assert proc.returncode == 0, proc.stderr
    assert f"{absent} does not exist" in proc.stdout
    assert "## CHANGE RISK: INSUFFICIENT EVIDENCE" in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_plane_flags_without_capture_are_refused(tmp_path):
    n4 = tmp_path / "n4.json"
    n4.write_text(json.dumps({"messages": [], "procedures": [], "unpaired_requests": 0}))
    proc = _assess(tmp_path, UPGRADE, "--capture-n4", str(n4))
    assert proc.returncode == 1
    assert "--capture" in proc.stderr
    assert proc.stdout == ""


def test_critical_capture_grades_high_and_cites_the_messages(tmp_path):
    proc = _assess(tmp_path, UPGRADE, "--capture", str(CAPTURE_CRITICAL))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: HIGH" in proc.stdout
    assert (
        "dependency criticality: critical interface "
        "Nudm_UEContextManagement, Nausf_UEAuthentication in the blast "
        f"radius [cited: {CAPTURE_CRITICAL}:sbi/messages/2, "
        f"{CAPTURE_CRITICAL}:sbi/messages/3]" in proc.stdout
    )
    assert f"- UDM [cited: {CAPTURE_CRITICAL}:sbi/messages/2]" in proc.stdout
    assert f"- AUSF [cited: {CAPTURE_CRITICAL}:sbi/messages/3]" in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_quiet_evidence_grades_low(tmp_path):
    history = tmp_path / "changes.jsonl"
    history.write_text("")
    triage = tmp_path / "triage.jsonl"
    triage.write_text("")
    dispatch = tmp_path / "dispatch.jsonl"
    dispatch.write_text("")
    reports = tmp_path / "reports"
    reports.mkdir()
    proc = _assess(
        tmp_path,
        UPGRADE,
        "--history-path", str(history),
        "--triage-episodes", str(triage),
        "--dispatch-episodes", str(dispatch),
        "--reports", str(reports),
        "--capture", str(CAPTURE_N4),
    )
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: LOW" in proc.stdout
    assert "no critical interface in the blast radius" in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_plan_prioritizes_prechecks_and_sets_rollback_thresholds(tmp_path):
    proc = _assess(
        tmp_path, UPGRADE, "--capture", str(CAPTURE), "--test-plan", str(PLAN)
    )
    assert proc.returncode == 0, proc.stderr
    prechecks = proc.stdout.split("## Recommended Pre-Checks")[1].split(
        "## Rollback Criteria"
    )[0]
    rollback = proc.stdout.split("## Rollback Criteria")[1]
    assert prechecks.index("SMF comes up cleanly") < prechecks.index(
        "Ping UPF reachability"
    )
    assert prechecks.index("Ping UPF reachability") < prechecks.index(
        "AMF registration under load"
    )
    assert (
        f"Reject rate stays zero [reject count: <= 0] "
        f"[cited: {PLAN}:items/4]" in prechecks
    )
    assert "UDM auth round trip" not in prechecks
    assert (
        f"1 plan item(s) outside the blast radius or without an NF pin "
        f"are not listed [cited: {PLAN}]" in prechecks
    )
    assert (
        f"Reject rate stays zero [reject count: <= 0] "
        f"[cited: {PLAN}:items/4]" in rollback
    )
    assert "Any regression in the capture-derived" not in rollback
    _assert_marker_discipline(proc.stdout)


def test_plan_without_watch_points_keeps_the_qualitative_rollback(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps({"items": [{"name": "Ping UPF reachability", "nf": "UPF"}]})
    )
    proc = _assess(
        tmp_path, UPGRADE, "--capture", str(CAPTURE), "--test-plan", str(plan)
    )
    assert proc.returncode == 0, proc.stderr
    assert f"Ping UPF reachability [cited: {plan}:items/0]" in proc.stdout
    assert (
        "Any regression in the capture-derived Procedures and KPIs "
        "above during the Change" in proc.stdout
    )
    _assert_marker_discipline(proc.stdout)


def test_plan_without_a_radius_names_the_plan_lists_nothing(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps({"items": [{"name": "Ping UPF reachability", "nf": "UPF"}]})
    )
    proc = _assess(tmp_path, UPGRADE, "--test-plan", str(plan))
    assert proc.returncode == 0, proc.stderr
    assert (
        f"No blast radius determinable — plan items cannot be "
        f"prioritized; {plan} holds 1 item [cited: {plan}]" in proc.stdout
    )
    assert "Ping UPF reachability" not in proc.stdout
    assert (
        f"None — no blast radius determinable, so no watch-point "
        f"thresholds can be set; {plan} holds 1 item [cited: {plan}]"
        in proc.stdout
    )
    _assert_marker_discipline(proc.stdout)


def test_config_change_with_a_plan_lists_nothing(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"items": [{"name": "Ping UDM", "nf": "UDM"}]}))
    proc = _assess(tmp_path, CONFIG, "--test-plan", str(plan))
    assert proc.returncode == 0, proc.stderr
    assert "plan items cannot be prioritized" in proc.stdout
    assert "Ping UDM" not in proc.stdout
    assert (
        f"None — no blast radius determinable, so no watch-point "
        f"thresholds can be set; {plan} holds 1 item [cited: {plan}]"
        in proc.stdout
    )
    _assert_marker_discipline(proc.stdout)


def test_unpinned_plan_items_are_counted_not_silently_dropped(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "name": "No pin watch",
                        "kpi": "latency",
                        "threshold": "< 5ms",
                    }
                ]
            }
        )
    )
    proc = _assess(
        tmp_path, UPGRADE, "--capture", str(CAPTURE), "--test-plan", str(plan)
    )
    assert proc.returncode == 0, proc.stderr
    assert (
        f"1 plan item(s) outside the blast radius or without an NF pin "
        f"are not listed [cited: {plan}]" in proc.stdout
    )
    assert "No pin watch" not in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_missing_plan_is_named(tmp_path):
    absent = tmp_path / "absent-plan.json"
    proc = _assess(tmp_path, UPGRADE, "--test-plan", str(absent))
    assert proc.returncode == 0, proc.stderr
    assert f"test plan {absent} does not exist" in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_empty_plan_is_named(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"items": []}))
    proc = _assess(tmp_path, UPGRADE, "--test-plan", str(plan))
    assert proc.returncode == 0, proc.stderr
    assert f"test plan {plan} holds no items" in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_malformed_plan_is_refused_nothing_renders(tmp_path):
    bad = tmp_path / "plan.json"
    bad.write_text("{not json")
    proc = _assess(tmp_path, UPGRADE, "--test-plan", str(bad))
    assert proc.returncode == 1
    assert "error:" in proc.stderr
    assert proc.stdout == ""
    bad.write_text(json.dumps({"items": [{"nf": "UPF"}]}))
    proc = _assess(tmp_path, UPGRADE, "--test-plan", str(bad))
    assert proc.returncode == 1
    assert "non-empty 'name'" in proc.stderr
    assert proc.stdout == ""


def test_separate_plane_exports_load_and_cite_their_own_file(tmp_path):
    n2 = tmp_path / "n2.json"
    n2.write_text(json.dumps({"flows": [], "unassociated": []}))
    n4 = tmp_path / "n4.json"
    n4.write_text(
        json.dumps(
            {
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
            }
        )
    )
    proc = _assess(
        tmp_path, UPGRADE, "--capture", str(n2), "--capture-n4", str(n4)
    )
    assert proc.returncode == 0, proc.stderr
    assert "blast radius: affects UPF (1 NF)" in proc.stdout
    assert f"- UPF [cited: {n4}:n4/messages/0]" in proc.stdout
    assert f"{n2}:n4/messages/0" not in proc.stdout
    _assert_marker_discipline(proc.stdout)
