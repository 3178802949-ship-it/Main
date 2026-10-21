"""Shared immutable schema and preserved legacy runtime bootstrap."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime'
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))
SCHEMA = json.loads((ROOT / 'data/original/spin_era_v013_frozen_attribute_schema.json').read_text())


def load_schema():
    return json.loads(json.dumps(SCHEMA))


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

