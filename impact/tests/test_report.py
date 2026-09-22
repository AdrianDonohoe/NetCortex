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
