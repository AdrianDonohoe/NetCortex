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

from .change import ChangeError, parse_change
from .evidence import Evidence, StoreState
from .report import render_report
from .rubric import grade


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
        "--episodes-path",
        metavar="PATH",
        help="an Episode store, triage's or dispatch's (absent = not consulted)",
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with open(args.change, encoding="utf-8") as fh:
            change = parse_change(json.load(fh))
        evidence = Evidence(
            history=_store_state(args.history_path),
            episodes=_store_state(args.episodes_path),
        )
        report = render_report(change, grade(change, evidence), evidence)
    except (ChangeError, json.JSONDecodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
