"""The Change record: the input artifact's parsing contract."""

import json

import pytest

from impact.change import Change, ChangeError, ChangeType, parse_change

UPGRADE_JSON = '{"type": "upgrade", "nf": "SMF", "from": "2.4.1", "to": "2.4.2"}'
CONFIG_JSON = '{"type": "config", "key": "udm.sbi.uri", "from": "udm-1", "to": "udm-2"}'


def test_upgrade_parses():
    change = parse_change(json.loads(UPGRADE_JSON))
    assert change == Change(
        type=ChangeType.UPGRADE, target="SMF", before="2.4.1", after="2.4.2"
    )


def test_config_parses():
    change = parse_change(json.loads(CONFIG_JSON))
    assert change == Change(
        type=ChangeType.CONFIG,
        target="udm.sbi.uri",
        before="udm-1",
        after="udm-2",
    )


def test_describe():
    assert (
        parse_change(json.loads(UPGRADE_JSON)).describe()
        == "upgrade SMF 2.4.1 → 2.4.2"
    )
    assert (
        parse_change(json.loads(CONFIG_JSON)).describe()
        == "config udm.sbi.uri udm-1 → udm-2"
    )


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ('{"type": "patch", "nf": "SMF", "from": "a", "to": "b"}', "unknown change type"),
        ('{"type": "upgrade", "from": "a", "to": "b"}', "'nf'"),
        ('{"type": "config", "key": "", "from": "a", "to": "b"}', "'key'"),
        ('{"type": "upgrade", "nf": "SMF", "to": "b"}', "'from'"),
        ('{"type": "upgrade", "nf": "SMF", "from": "a"}', "'to'"),
    ],
)
def test_malformed_is_refused(raw, message):
    with pytest.raises(ChangeError, match=message):
        parse_change(json.loads(raw))


def test_non_object_is_refused():
    with pytest.raises(ChangeError, match="JSON object"):
        parse_change(json.loads("[1, 2]"))
