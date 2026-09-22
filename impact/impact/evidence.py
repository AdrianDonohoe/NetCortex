"""The evidence the rubric is applied to: stores and their state.

Sibling of dispatch's evidence module. StoreState reports what a store
actually holds — a missing store must never read as an observed
emptiness, so absence and emptiness are distinct states. It also owns
its own wire format: the rubric asks the store for parsed records, the
way dispatch's MemoryStore and EpisodeStore own their parsing.
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

    def mention_lines(self, target: str) -> list[int]:
        """Line numbers whose text mentions the target as a whole word."""
        pattern = rf"\b{re.escape(target)}\b"
        return [
            idx
            for idx, line in enumerate(self.lines, start=1)
            if re.search(pattern, line)
        ]


@dataclass(frozen=True)
class Evidence:
    """The evidence the rubric is applied to.

    The two stores' lines feed the rubric's historical assessment;
    captures and the test plan join with the tickets that consult them.
    """

    history: StoreState
    episodes: StoreState
