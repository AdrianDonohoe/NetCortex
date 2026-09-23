"""The CLI seam: annotate's annotation loop and assess's read-only guarantee."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import UPGRADE

REPO = Path(__file__).resolve().parent.parent

REPORT_BODY = "# Impact Report\n\n**Change:** upgrade SMF 2.4.1 → 2.4.2\n"


def _annotate(tmp_path, *flags, cwd=None, report_path=None, change_text=None):
    if report_path is None:
        report_path = tmp_path / "report.md"
        if not report_path.exists():  # leave a prior annotation in place
            report_path.write_text(REPORT_BODY)
    record = tmp_path / "change.json"
    record.write_text(
        change_text if change_text is not None else json.dumps(UPGRADE)
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "impact.cli",
            "annotate",
            str(report_path),
            "--change",
            str(record),
            *flags,
        ],
        capture_output=True,
        text=True,
        cwd=cwd or REPO,
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )


def _store_line(change, outcome):
    return json.dumps({"change": change, "outcome": outcome}) + "\n"


def test_annotate_appends_a_change_record_to_the_store(tmp_path):
    store = tmp_path / "changes.jsonl"
    proc = _annotate(tmp_path, "--outcome", "applied", "--history-path", str(store))
    assert proc.returncode == 0, proc.stderr
    assert store.read_text() == _store_line(UPGRADE, "applied")


def test_annotate_creates_the_default_store(tmp_path):
    # cwd=tmp_path so the default impact/memory/changes.jsonl resolves there
    proc = _annotate(tmp_path, "--outcome", "rejected", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    store = tmp_path / "impact" / "memory" / "changes.jsonl"
    assert store.read_text() == _store_line(UPGRADE, "rejected")


def test_annotate_appends_not_overwrites(tmp_path):
    store = tmp_path / "changes.jsonl"
    past = {"type": "upgrade", "nf": "AMF", "from": "1.0", "to": "1.1"}
    store.write_text(_store_line(past, "rejected"))
    proc = _annotate(tmp_path, "--outcome", "applied", "--history-path", str(store))
    assert proc.returncode == 0, proc.stderr
    lines = store.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["change"] == past
    assert json.loads(lines[1])["outcome"] == "applied"


def test_annotate_records_the_outcome_onto_the_report(tmp_path):
    store = tmp_path / "changes.jsonl"
    proc = _annotate(
        tmp_path, "--outcome", "applied", "--history-path", str(store)
    )
    assert proc.returncode == 0, proc.stderr
    report = tmp_path / "report.md"
    assert report.read_text() == REPORT_BODY + (
        "\n## Outcome\n\n- **Verdict:** **applied**\n"
    )


@pytest.mark.parametrize("outcome", ["applied", "rejected", "rolled-back"])
def test_annotate_accepts_each_outcome_word(tmp_path, outcome):
    store = tmp_path / "changes.jsonl"
    proc = _annotate(tmp_path, "--outcome", outcome, "--history-path", str(store))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(store.read_text())["outcome"] == outcome


def test_annotate_refuses_an_unknown_outcome_word(tmp_path):
    store = tmp_path / "changes.jsonl"
    proc = _annotate(tmp_path, "--outcome", "fixed", "--history-path", str(store))
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert not store.exists()


def test_annotate_refuses_a_report_that_already_carries_an_outcome(tmp_path):
    store = tmp_path / "changes.jsonl"
    first = _annotate(
        tmp_path, "--outcome", "applied", "--history-path", str(store)
    )
    assert first.returncode == 0, first.stderr
    annotated = (tmp_path / "report.md").read_text()
    second = _annotate(
        tmp_path, "--outcome", "rejected", "--history-path", str(store)
    )
    assert second.returncode == 1
    assert "already carries an Outcome" in second.stderr
    assert (tmp_path / "report.md").read_text() == annotated
    assert len(store.read_text().splitlines()) == 1


def test_annotate_fails_loudly_on_a_missing_report(tmp_path):
    store = tmp_path / "changes.jsonl"
    proc = _annotate(
        tmp_path,
        "--outcome",
        "applied",
        "--history-path",
        str(store),
        report_path=tmp_path / "nope.md",
    )
    assert proc.returncode == 1
    assert "error" in proc.stderr
    assert not store.exists()


def test_annotate_fails_loudly_on_a_bad_change(tmp_path):
    store = tmp_path / "changes.jsonl"
    proc = _annotate(
        tmp_path,
        "--outcome",
        "applied",
        "--history-path",
        str(store),
        change_text='{"type": "upgrade"}',
    )
    assert proc.returncode == 1
    assert "error" in proc.stderr
    assert not store.exists()
    assert (tmp_path / "report.md").read_text() == REPORT_BODY


def test_assess_never_writes_the_store(tmp_path):
    store = tmp_path / "changes.jsonl"
    store.write_text(_store_line(UPGRADE, "rejected"))
    before = store.read_bytes()
    record = tmp_path / "change.json"
    record.write_text(json.dumps(UPGRADE))
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "impact.cli",
            "assess",
            str(record),
            "--history-path",
            str(store),
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert proc.returncode == 0, proc.stderr
    assert store.read_bytes() == before
    assert "## CHANGE RISK: HIGH" in proc.stdout
