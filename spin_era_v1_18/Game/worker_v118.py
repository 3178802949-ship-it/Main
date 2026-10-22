"""Isolated V1.1.7 综合版 worker; scoped preference hooks never escape this process."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from common import RUNTIME
from Game import engine_v117 as detailed
from Game import light_v117 as light
from Game import preferences_v118 as preferences


def main():
    request = json.load(sys.stdin)
    audit = {card['player_id']: preferences.new_audit(card) for card in request['cards']}
    original = detailed.action_distribution
    old_light = light.shared_action_distribution

    def action_distribution(card, state, ball, position, tactic):
        options = original(card, state, ball, position, tactic)
        return preferences.apply_preferences(options, card, state, ball, position,
            audit=audit[card['player_id']])

    try:
        detailed.action_distribution = action_distribution
        light.shared_action_distribution = action_distribution
        engine = detailed if request['detail_level'] == 'full' else light
        result = engine.play_match(request['cards'], request['seed'],
            keep_points=request['detail_level'] == 'full', fatigue=tuple(request['fatigue']),
            max_games=request['max_games'])
    finally:
        detailed.action_distribution = original
        light.shared_action_distribution = old_light
    result['style_preference_audit'] = [audit[card['player_id']] for card in request['cards']]
    fingerprints = result.setdefault('mechanics_source_sha256', {})
    root = Path(__file__).resolve().parents[1]
    for path in (Path(__file__), Path(preferences.__file__)):
        fingerprints[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    json.dump(result, sys.stdout, ensure_ascii=False, allow_nan=False)


if __name__ == '__main__':
    main()
