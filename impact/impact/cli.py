"""impact CLI: assess a proposed Change and write an Impact Report.

Read-only by design: nothing here applies anything, not even in the
sandbox lab. The report is the deliverable; a human decides and
applies. Exit codes: 0 on success, 1 on any input or evidence error,
with the error named on stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .capture import CaptureState
from .change import parse_change
from .evidence import Evidence, ReportFile, ReportsState, StoreState
from .plan import PlanState, parse_plan
from .report import render_report
from .rubric import grade
from .specgraph import SpecGraphState


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="impact",
        description="Pre-change advisory: assess a proposed Change and write an Impact Report.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    assess = sub.add_parser(
        "assess",
        help="assess a proposed Change against the platform's evidence and write an Impact Report",
    )
    assess.add_argument(
        "change", metavar="CHANGE.json", help="the Change record (a JSON file)"
    )
    assess.add_argument(
        "--history-path",
        metavar="PATH",
        help="the Change History store (absent = not consulted)",
    )
    assess.add_argument(
        "--triage-episodes",
        metavar="PATH",
        help="triage's Episode store (absent = not consulted)",
    )
    assess.add_argument(
        "--dispatch-episodes",
        metavar="PATH",
        help="dispatch's Episode store (absent = not consulted)",
    )
    assess.add_argument(
        "--reports",
        metavar="DIR",
        help="a directory of post-incident reports (absent = not consulted)",
    )
    assess.add_argument(
        "--capture",
        metavar="N2.json",
        help="a decoded capture export (the merged export embeds n4 and sbi; absent = not consulted)",
    )
    assess.add_argument(
        "--capture-n4",
        metavar="N4.json",
        help="a separate decoded N4 export (wins over the embedded section; requires --capture)",
    )
    assess.add_argument(
        "--capture-sbi",
        metavar="SBI.json",
        help="a separate decoded SBI export (wins over the embedded section; requires --capture)",
    )
    assess.add_argument(
        "--specgraph",
        metavar="PATH",
        help="the cached specgraph export (the fallback when no capture locates the target; absent = not consulted)",
    )
    assess.add_argument(
        "--test-plan",
        metavar="PLAN.json",
        help="the human's test plan, consumed and prioritized, never run (absent = not consulted)",
    )
    return parser


def _store_state(path: str | None) -> StoreState:
    if path is None:
        return StoreState(None, exists=False)
    store = Path(path)
    if not store.exists():
        return StoreState(path, exists=False)
    with store.open(encoding="utf-8") as fh:
        lines = tuple(line.strip() for line in fh if line.strip())
    return StoreState(path, lines)


def _reports_state(path: str | None) -> ReportsState:
    if path is None:
        return ReportsState(None, exists=False)
    directory = Path(path)
    if not directory.exists():
        return ReportsState(path, exists=False)
    if not directory.is_dir():
        return ReportsState(path, is_dir=False)
    files: list[ReportFile] = []
    unreadable = 0
    for report_path in sorted(directory.rglob("*.md")):
        try:
            with report_path.open(encoding="utf-8") as fh:
                lines = tuple(line.strip() for line in fh if line.strip())
        except (OSError, UnicodeDecodeError):
            unreadable += 1  # named in the report, never asserted clear
            continue
        files.append(ReportFile(str(report_path), lines))
    return ReportsState(path, tuple(files), unreadable=unreadable)


def _capture_state(
    path: str | None, n4_path: str | None, sbi_path: str | None
) -> CaptureState:
    """Load the decoded capture export; the merged export embeds planes.

    An explicit --capture-n4/--capture-sbi wins over the embedded
    section, mirroring triage's load_capture. Malformed JSON propagates
    — a structured input fails loudly, unlike lenient store lines.
    """
    if path is None:
        if n4_path is not None or sbi_path is not None:
            raise ValueError("--capture-n4 and --capture-sbi require --capture")
        return CaptureState(None)
    capture_path = Path(path)
    if not capture_path.exists():
        return CaptureState(str(capture_path), exists=False)
    n2 = json.loads(capture_path.read_text(encoding="utf-8"))
    if not isinstance(n2, dict):
        raise ValueError(f"{capture_path} is not a decoded capture export")
    n4 = None
    if n4_path is not None:
        n4 = json.loads(Path(n4_path).read_text(encoding="utf-8"))
    elif isinstance(n2.get("n4"), dict):
        n4 = n2["n4"]
    if not isinstance(n4, dict) and n4 is not None:
        raise ValueError(f"{n4_path} is not a decoded N4 export")
    sbi = None
    if sbi_path is not None:
        sbi = json.loads(Path(sbi_path).read_text(encoding="utf-8"))
    elif isinstance(n2.get("sbi"), dict):
        sbi = n2["sbi"]
    if not isinstance(sbi, dict) and sbi is not None:
        raise ValueError(f"{sbi_path} is not a decoded SBI export")
    return CaptureState(
        str(capture_path),
        n2=n2,
        n4=n4,
        sbi=sbi,
        n4_path=str(n4_path) if n4_path is not None else None,
        sbi_path=str(sbi_path) if sbi_path is not None else None,
    )


def _specgraph_state(path: str | None) -> SpecGraphState:
    if path is None:
        return SpecGraphState(None)
    specgraph_path = Path(path)
    if not specgraph_path.exists():
        return SpecGraphState(str(specgraph_path), exists=False)
    data = json.loads(specgraph_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{specgraph_path} is not a specgraph export")
    return SpecGraphState(
        str(specgraph_path),
        entities=tuple(data.get("entities") or ()),
        edges=tuple(data.get("edges") or ()),
    )


def _plan_state(path: str | None) -> PlanState:
    """Load the test plan; malformed plans fail loudly like the capture."""
    if path is None:
        return PlanState(None)
    plan_path = Path(path)
    if not plan_path.exists():
        return PlanState(str(plan_path), exists=False)
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    return PlanState(str(plan_path), items=parse_plan(data))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with open(args.change, encoding="utf-8") as fh:
            change = parse_change(json.load(fh))
        evidence = Evidence(
            history=_store_state(args.history_path),
            triage_episodes=_store_state(args.triage_episodes),
            dispatch_episodes=_store_state(args.dispatch_episodes),
            reports=_reports_state(args.reports),
            capture=_capture_state(
                args.capture, args.capture_n4, args.capture_sbi
            ),
            specgraph=_specgraph_state(args.specgraph),
            plan=_plan_state(args.test_plan),
        )
        report = render_report(change, grade(change, evidence), evidence)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
