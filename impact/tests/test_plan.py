"""The test plan: wire validation, proximity placement, honesty states."""

import pytest

from impact.capture import AffectedNF, BlastResult, Role
from impact.plan import PlanItem, PlanState, parse_plan, placed_items


def _result():
    return BlastResult(
        Role("SMF", "10.0.0.3", "n4/messages/0"),
        (
            AffectedNF(role="UPF", ip="10.0.0.4", evidence="n4/messages/0"),
            AffectedNF(role="AMF", ip="10.0.0.2", evidence="flows/0/messages/0"),
        ),
        0,
        (),
    )


def _plan(*items):
    return PlanState("plan.json", items=tuple(items))


def test_parse_plan_accepts_the_wire_format():
    items = parse_plan(
        {
            "items": [
                {"name": "Ping UPF reachability", "nf": "UPF"},
                {
                    "name": "Reject rate stays zero",
                    "nf": "UPF",
                    "kpi": "reject count",
                    "threshold": "<= 0",
                },
                {"name": "Bare check"},
            ]
        }
    )
    assert items == (
        PlanItem("Ping UPF reachability", "UPF"),
        PlanItem("Reject rate stays zero", "UPF", "reject count", "<= 0"),
        PlanItem("Bare check"),
    )


def test_parse_plan_refuses_malformed_plans():
    with pytest.raises(ValueError, match="items"):
        parse_plan({"checks": []})
    with pytest.raises(ValueError, match="JSON object"):
        parse_plan([])
    with pytest.raises(ValueError, match="plan item 1 is not"):
        parse_plan({"items": [{"name": "ok"}, "oops"]})
    with pytest.raises(ValueError, match="non-empty 'name'"):
        parse_plan({"items": [{"nf": "UPF"}]})
    with pytest.raises(ValueError, match="non-empty 'name'"):
        parse_plan({"items": [{"name": "  "}]})
    with pytest.raises(ValueError, match="not a string"):
        parse_plan({"items": [{"name": "ok", "nf": 7}]})
    with pytest.raises(ValueError, match="come together"):
        parse_plan({"items": [{"name": "ok", "kpi": "reject count"}]})
    with pytest.raises(ValueError, match="come together"):
        parse_plan({"items": [{"name": "ok", "threshold": "<= 0"}]})


def test_parse_plan_refuses_unknown_fields():
    with pytest.raises(ValueError, match="unknown field 'treshold'"):
        parse_plan(
            {"items": [{"name": "Reject rate", "nf": "UPF", "treshold": "<= 0"}]}
        )


def test_parse_plan_strips_nf_kpi_and_threshold():
    items = parse_plan(
        {
            "items": [
                {
                    "name": " check ",
                    "nf": " upf ",
                    "kpi": " reject count ",
                    "threshold": " <= 0 ",
                }
            ]
        }
    )
    assert items == (PlanItem("check", "upf", "reject count", "<= 0"),)


def test_parse_plan_blank_kpi_with_a_threshold_fails_loudly():
    with pytest.raises(ValueError, match="come together"):
        parse_plan({"items": [{"name": "ok", "kpi": "  ", "threshold": "<= 0"}]})


def test_state_describes_itself_honestly():
    assert PlanState(None).describe() == "not consulted"
    assert PlanState("absent.json", exists=False).describe() == (
        "absent.json does not exist"
    )
    assert _plan().describe() == "plan.json holds no items"
    assert _plan(PlanItem("one")).describe() == "plan.json holds 1 item"
    assert _plan(PlanItem("one"), PlanItem("two")).describe() == (
        "plan.json holds 2 items"
    )


def test_placed_items_order_by_proximity_then_plan_order():
    plan = _plan(
        PlanItem("Ping UPF reachability", "UPF"),
        PlanItem("SMF comes up cleanly", "SMF"),
        PlanItem("AMF registration under load", "AMF"),
    )
    placed = placed_items(plan, _result())
    assert [(p.item.name, p.distance) for p in placed] == [
        ("SMF comes up cleanly", 0),
        ("Ping UPF reachability", 1),
        ("AMF registration under load", 1),
    ]


def test_placement_is_case_insensitive():
    plan = _plan(PlanItem("check", "upf"), PlanItem("target", "smf"))
    placed = placed_items(plan, _result())
    assert [(p.item.name, p.distance) for p in placed] == [
        ("target", 0),
        ("check", 1),
    ]


def test_items_without_an_nf_or_outside_the_radius_are_not_placed():
    plan = _plan(
        PlanItem("Bare check"),
        PlanItem("UDM auth round trip", "UDM"),
        PlanItem("Ping UPF reachability", "UPF"),
    )
    placed = placed_items(plan, _result())
    assert [p.item.name for p in placed] == ["Ping UPF reachability"]


def test_no_radius_places_nothing():
    plan = _plan(PlanItem("Ping UPF reachability", "UPF"))
    assert placed_items(plan, None) == ()
    assert placed_items(plan, BlastResult(None, (), 0, ())) == ()
