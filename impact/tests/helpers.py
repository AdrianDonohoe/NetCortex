"""Shared test inputs for the impact context."""

import json

UPGRADE = {"type": "upgrade", "nf": "SMF", "from": "2.4.1", "to": "2.4.2"}
CONFIG = {"type": "config", "key": "udm.sbi.uri", "from": "udm-1", "to": "udm-2"}
UPGRADE_JSON = json.dumps(UPGRADE)
CONFIG_JSON = json.dumps(CONFIG)
