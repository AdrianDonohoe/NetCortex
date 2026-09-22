"""The Impact Report: the golden seam and the cited-vs-predicted honesty hook."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import CONFIG, UPGRADE
from impact.report import Claim, UnmarkedClaimError

REPO = Path(__file__).resolve().parent.parent

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
    assert "historical evidence consulted" in proc.stdout.lower()
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
    assert "historical evidence consulted" in proc.stdout.lower()
    assert f"{empty} is empty" in proc.stdout
    # the factor names only what was actually read
    assert (
        "no failed Change Records in Change History; Episodes not consulted"
        in proc.stdout
    )


def test_unconsulted_store_is_never_reported_as_clear(tmp_path):
    episodes = tmp_path / "episodes.jsonl"
    episodes.write_text('{"id": "e2", "summary": "UPF session drop"}\n')
    proc = _assess(tmp_path, UPGRADE, "--episodes-path", str(episodes))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: INSUFFICIENT EVIDENCE" in proc.stdout
    assert (
        "Change History not consulted; no Episodes touch SMF" in proc.stdout
    )
    assert "no failed Change Records" not in proc.stdout


def test_failed_change_record_grades_high(tmp_path):
    history = tmp_path / "changes.jsonl"
    history.write_text(json.dumps({"change": UPGRADE, "outcome": "failed"}) + "\n")
    proc = _assess(tmp_path, UPGRADE, "--history-path", str(history))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: HIGH" in proc.stdout
    assert (
        "a failed Change Record on SMF: upgrade SMF 2.4.1 → 2.4.2"
        in proc.stdout
    )
    assert f"{history}:1" in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_episode_contact_grades_medium(tmp_path):
    episodes = tmp_path / "episodes.jsonl"
    episodes.write_text(
        '{"id": "e1", "summary": "SMF registration failure"}\n'
        '{"id": "e2", "summary": "UPF session drop"}\n'
    )
    proc = _assess(tmp_path, UPGRADE, "--episodes-path", str(episodes))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: MEDIUM" in proc.stdout
    assert "past Episodes touch SMF" in proc.stdout
    assert f"{episodes}:1" in proc.stdout
    _assert_marker_discipline(proc.stdout)


def test_success_record_keeps_evidence_insufficient(tmp_path):
    history = tmp_path / "changes.jsonl"
    history.write_text(json.dumps({"change": UPGRADE, "outcome": "success"}) + "\n")
    proc = _assess(tmp_path, UPGRADE, "--history-path", str(history))
    assert proc.returncode == 0, proc.stderr
    assert "## CHANGE RISK: INSUFFICIENT EVIDENCE" in proc.stdout
    assert (
        "no failed Change Records in Change History; Episodes not consulted"
        in proc.stdout
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
