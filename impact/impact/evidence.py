"""The evidence the rubric is applied to: stores and their state.

Sibling of dispatch's evidence module. StoreState reports what a store
actually holds — a missing store must never read as an observed
emptiness, so absence and emptiness are distinct states.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoreState:
    """What an evidence store holds: its path, whether it exists, its entries."""

    path: str | None
    entries: int
    exists: bool = True

    @property
    def empty(self) -> bool:
        return self.entries == 0

    def describe(self) -> str:
        if self.path is None:
            return "not consulted"
        if not self.exists:
            return f"{self.path} does not exist"
        if self.empty:
            return f"{self.path} is empty"
        return f"{self.path} has {self.entries} entries"


@dataclass(frozen=True)
class Evidence:
    """The evidence the rubric is applied to.

    Ticket 1 carries only the two stores it can be empty with; captures
    and the test plan join with the tickets that consult them.
    """

    history: StoreState
    episodes: StoreState

    @property
    def empty(self) -> bool:
        return self.history.empty and self.episodes.empty
