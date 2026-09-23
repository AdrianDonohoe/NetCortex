"""The Change record: the impact context's input artifact.

A Change is a structured record with a deliberately small vocabulary of
two: an NF software upgrade, and a config change. Config differences
enter as structured fields, never as raw diffs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChangeError(ValueError):
    """A Change record that does not parse."""


class ChangeType(str, Enum):
    UPGRADE = "upgrade"
    CONFIG = "config"


# The human's Outcome vocabulary on a Change Record.
OUTCOMES = ("applied", "rejected", "rolled-back")

# The outcomes that read as failures to the historical-evidence factor.
FAILED_OUTCOMES = ("rejected", "rolled-back")


@dataclass(frozen=True)
class Change:
    type: ChangeType
    target: str  # the NF for an upgrade; the config key for a config change
    before: str
    after: str

    def describe(self) -> str:
        return f"{self.type.value} {self.target} {self.before} → {self.after}"


def parse_change(data: object) -> Change:
    """Parse a Change from its record; raise ChangeError naming the problem."""
    if not isinstance(data, dict):
        raise ChangeError("a Change record must be a JSON object")
    try:
        ctype = ChangeType(data.get("type"))
    except ValueError:
        raise ChangeError(
            f"unknown change type {data.get('type')!r} "
            f"(expected 'upgrade' or 'config')"
        ) from None
    label = _target_label(ctype)
    target = data.get(label)
    if not isinstance(target, str) or not target:
        raise ChangeError(f"a {ctype.value} Change needs a non-empty {label!r} field")
    before = data.get("from")
    after = data.get("to")
    if not isinstance(before, str) or not before:
        raise ChangeError("a Change needs a non-empty 'from' field")
    if not isinstance(after, str) or not after:
        raise ChangeError("a Change needs a non-empty 'to' field")
    return Change(type=ctype, target=target, before=before, after=after)


def _target_label(ctype: ChangeType) -> str:
    """The field that carries the target: nf for upgrades, key for configs."""
    return "nf" if ctype is ChangeType.UPGRADE else "key"


def to_record(change: Change) -> dict:
    """The Change's stored form — the shape parse_change reads back."""
    return {
        "type": change.type.value,
        _target_label(change.type): change.target,
        "from": change.before,
        "to": change.after,
    }
