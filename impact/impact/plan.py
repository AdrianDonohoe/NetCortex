"""The human's test plan: consumed and prioritized, never run.

The plan is a structured input like the capture — malformed plans fail
loudly rather than silently thinning the report's checks. Items are
placed by proximity to the Change's target: the target itself (distance
0), then its partners (distance 1), plan order preserved within each
group. Items outside the radius, or without an NF pin, are the caller's
excluded count — never dropped silently. A watch point carries the
human's threshold verbatim; nothing here evaluates it (the read-only
boundary).
"""

from __future__ import annotations

from dataclasses import dataclass

from .capture import BlastResult


@dataclass(frozen=True)
class PlanItem:
    """One check the human wants: name, optional NF pin, optional watch point."""

    name: str
    nf: str | None = None
    kpi: str | None = None
    threshold: str | None = None

    @property
    def is_watch_point(self) -> bool:
        return self.kpi is not None and self.threshold is not None


@dataclass(frozen=True)
class PlacedItem:
    """A plan item inside the blast radius, with its proximity and plan index."""

    item: PlanItem
    distance: int  # 0 = the target itself, 1 = a partner
    index: int  # the item's index in the plan, for the citation pointer


@dataclass(frozen=True)
class PlanState:
    """What the plan holds: path, items, existence."""

    path: str | None
    items: tuple[PlanItem, ...] = ()
    exists: bool = True

    def describe(self) -> str:
        if self.path is None:
            return "not consulted"
        if not self.exists:
            return f"{self.path} does not exist"
        if not self.items:
            return f"{self.path} holds no items"
        if len(self.items) == 1:
            return f"{self.path} holds 1 item"
        return f"{self.path} holds {len(self.items)} items"


_FIELDS = ("name", "nf", "kpi", "threshold")


def parse_plan(data: dict) -> tuple[PlanItem, ...]:
    """Validate the plan wire format — {"items": [...]} — failing loudly.

    Unknown fields are refused too: a typo'd 'threshold' would otherwise
    silently demote a watch point to a plain check.
    """
    if not isinstance(data, dict):
        raise ValueError("a test plan is a JSON object")
    raw = data.get("items")
    if not isinstance(raw, list):
        raise ValueError("a test plan needs an 'items' list")
    items: list[PlanItem] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"plan item {index} is not a JSON object")
        unknown = set(entry) - set(_FIELDS)
        if unknown:
            field = sorted(unknown)[0]
            raise ValueError(f"plan item {index} has an unknown field '{field}'")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"plan item {index} needs a non-empty 'name'")
        nf = entry.get("nf")
        kpi = entry.get("kpi")
        threshold = entry.get("threshold")
        for field, value in (("nf", nf), ("kpi", kpi), ("threshold", threshold)):
            if value is not None and not isinstance(value, str):
                raise ValueError(
                    f"plan item {index} field '{field}' is not a string"
                )
        nf = nf.strip() or None if nf is not None else None
        kpi = kpi.strip() or None if kpi is not None else None
        threshold = threshold.strip() or None if threshold is not None else None
        if (kpi is None) != (threshold is None):
            raise ValueError(
                f"plan item {index}: 'kpi' and 'threshold' come together"
            )
        items.append(PlanItem(name.strip(), nf, kpi, threshold))
    return tuple(items)


def placed_items(
    plan: PlanState, result: BlastResult | None
) -> tuple[PlacedItem, ...]:
    """The plan items inside the blast radius, ordered by proximity.

    Distance 0 (the target itself) before distance 1 (its partners),
    plan order preserved within each group. Items outside the radius or
    without an NF pin are the caller's excluded count.
    """
    if result is None or result.target is None:
        return ()
    placed: list[PlacedItem] = []
    for plan_index, item in enumerate(plan.items):
        if item.nf is None:
            continue
        distance = result.proximity_of(item.nf)
        if distance is None:
            continue
        placed.append(PlacedItem(item, distance, plan_index))
    placed.sort(key=lambda placed_item: (placed_item.distance, placed_item.index))
    return tuple(placed)
