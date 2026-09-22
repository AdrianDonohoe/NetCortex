"""The evidence the rubric is applied to: stores and their state.

Sibling of dispatch's evidence module. StoreState reports what a store
actually holds — a missing store must never read as an observed
emptiness, so absence and emptiness are distinct states. It also owns
its own wire format: the rubric asks the store for parsed records, the
way dispatch's MemoryStore and EpisodeStore own their parsing.

Episode stores come in two wire formats — triage's flat Episode has no
incident id, so the record number stands in for it — and both are
parsed here, never by the rubric. Post-incident reports are Markdown
files in a directory; a mention is a file whose text contains the
target as a whole word, case-insensitively.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .change import Change, ChangeError, parse_change


@dataclass(frozen=True)
class StoreState:
    """What an evidence store holds: its path, its non-empty lines, existence."""

    path: str | None
    lines: tuple[str, ...] = ()
    exists: bool = True

    @property
    def entries(self) -> int:
        return len(self.lines)

    @property
    def consulted(self) -> bool:
        """True when the store was read and can attest to what it holds."""
        return self.path is not None and self.exists

    def describe(self) -> str:
        if self.path is None:
            return "not consulted"
        if not self.exists:
            return f"{self.path} does not exist"
        if not self.lines:
            return f"{self.path} is empty"
        if self.entries == 1:
            return f"{self.path} has 1 entry"
        return f"{self.path} has {self.entries} entries"

    def change_records(self) -> list[tuple[int, Change, str]]:
        """Parse the Change History wire format: (line, Change, outcome).

        Malformed lines are skipped — they are neither a match nor evidence.
        """
        records: list[tuple[int, Change, str]] = []
        for idx, line in enumerate(self.lines, start=1):
            try:
                record = json.loads(line)
                change = parse_change(record["change"])
                outcome = record.get("outcome", "")
            except (json.JSONDecodeError, KeyError, TypeError, ChangeError):
                continue
            records.append((idx, change, outcome))
        return records


@dataclass(frozen=True)
class EpisodeMention:
    """One Episode that touches the Change's target.

    label names the Episode in its store's own vocabulary — triage has
    no incident id, so "record N (incident_type)" stands in for it.
    narrative is the Episode's own story, collapsed to one line so wire
    data can never inject structure into the report.
    """

    label: str
    narrative: str
    citation: str  # "store.jsonl:3"


@dataclass(frozen=True)
class ReportFile:
    """One post-incident report: its path and non-empty lines."""

    path: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class ReportsState:
    """The post-incident reports directory: its path, its .md files, existence.

    is_dir is False when the path exists but is not a directory (triage
    writes its reports to single file paths); unreadable counts report
    files that could not be read. Both keep the store from being
    reported clear — nothing unread is ever asserted clear.
    """

    path: str | None
    files: tuple[ReportFile, ...] = ()
    exists: bool = True
    is_dir: bool = True
    unreadable: int = 0

    @property
    def entries(self) -> int:
        return len(self.files)

    @property
    def consulted(self) -> bool:
        """True when the directory was read and can attest to what it holds."""
        return (
            self.path is not None
            and self.exists
            and self.is_dir
            and self.unreadable == 0
        )

    def describe(self) -> str:
        if self.path is None:
            return "not consulted"
        if not self.exists:
            return f"{self.path} does not exist"
        if not self.is_dir:
            return f"{self.path} is not a directory"
        if self.unreadable == 1:
            suffix = "; 1 unreadable"
        elif self.unreadable:
            suffix = f"; {self.unreadable} unreadable"
        else:
            suffix = ""
        if not self.files:
            return f"{self.path} holds no reports{suffix}"
        if self.entries == 1:
            return f"{self.path} holds 1 report{suffix}"
        return f"{self.path} holds {self.entries} reports{suffix}"


def _line_mentions(lines: tuple[str, ...], target: str) -> list[int]:
    """Line numbers whose text mentions the target as a whole word.

    Case-insensitive: stores may record network functions lowercase.
    """
    pattern = rf"\b{re.escape(target)}\b"
    return [
        idx
        for idx, line in enumerate(lines, start=1)
        if re.search(pattern, line, re.IGNORECASE)
    ]


def _episode_mentions(store: StoreState, target: str, label_of) -> list[EpisodeMention]:
    """Episodes touching the target; label_of(idx, episode) names the mention.

    Malformed lines are skipped — they are neither a match nor evidence.
    """
    mentions: list[EpisodeMention] = []
    for idx in _line_mentions(store.lines, target):
        try:
            episode = json.loads(store.lines[idx - 1])
            label = " ".join(label_of(idx, episode).split())
            narrative = (
                " ".join(str(episode.get("narrative")).split())
                or "no narrative recorded"
            )
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            continue
        mentions.append(
            EpisodeMention(label, narrative, f"{store.path}:{idx}")
        )
    return mentions


def triage_episode_mentions(
    store: StoreState, target: str
) -> list[EpisodeMention]:
    """triage's Episodes that touch the target.

    triage's wire format is a flat Episode with no incident id, so the
    record number stands in for it: "record 2 (upf_timeout)".
    """

    def label_of(idx: int, episode: dict) -> str:
        return f"record {idx} ({episode['incident_type']})"

    return _episode_mentions(store, target, label_of)


def dispatch_episode_mentions(
    store: StoreState, target: str
) -> list[EpisodeMention]:
    """dispatch's Episodes that touch the target, by incident id."""

    def label_of(idx: int, episode: dict) -> str:
        return episode.get("incident_id") or f"record {idx}"

    return _episode_mentions(store, target, label_of)


def report_mentions(
    reports: ReportsState, target: str
) -> list[tuple[str, tuple[int, ...]]]:
    """Reports whose text mentions the target: (path, matching lines)."""
    mentions: list[tuple[str, tuple[int, ...]]] = []
    for report in reports.files:
        lines = _line_mentions(report.lines, target)
        if lines:
            mentions.append((report.path, tuple(lines)))
    return mentions


@dataclass(frozen=True)
class Evidence:
    """The evidence the rubric is applied to.

    The stores' lines feed the rubric's historical assessment; captures
    and the test plan join with the tickets that consult them.
    """

    history: StoreState
    triage_episodes: StoreState
    dispatch_episodes: StoreState
    reports: ReportsState
