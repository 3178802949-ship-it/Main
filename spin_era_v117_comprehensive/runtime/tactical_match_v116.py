"""Optional V1.1.6 tactical-choice experiment; not part of career calibration.

Read changes sensitivity to the fit of a response to the actual situation.
It does not add power, body attributes, XP or CA. This wrapper preserves the
legacy shot-quality function and the game's other tactical-reading pathways.

Like the legacy engine, temporarily replacing a module callback is not safe for
concurrent matches in a shared Python process. Use isolated processes instead.
"""
from __future__ import annotations

import copy
import math

import game_v115 as legacy

PATCH_TAG = 'V1.1.6_OPTIONAL_TACTICAL_FIT_EXPERIMENT'


def _style_multiplier(state, action):
    multiplier = 1.0
    if state.get('policy') == 'receive_initiative' and action not in legacy.DEFENSIVE:
        multiplier *= 1.38
    if state.get('policy') == 'defensive_pivot' and action in legacy.DEFENSIVE:
        multiplier *= 1.7
    if state.get('policy') == 'bh_squeeze' and action.startswith('bh_'):
        multiplier *= 1.35
    if (state.get('execute_weakness') and state.get('scouted_weakness') == 'bh'
            and action.startswith('bh_')):
        multiplier *= 1.23
    return multiplier


def action_distribution(card, state, ball, pos):
    """Return a deterministic audit of the candidates, without drawing or mutation.

    At effective read=120 the weights equal legacy choose_policy's weights.
    Removing its common read term avoids a normalization cancellation. Only the
    action-specific fit term receives the read sensitivity factor (.7 to 1.3).
    """
    scenario = legacy.context(ball)
    decision_read = legacy.core.gg(card, state, 'read')
    normalized = legacy.core.clamp((decision_read - 90) / 60, 0, 1)
    temperature = .70 + .60 * normalized
    candidates = []
    for action in legacy.SCENARIOS[scenario]:
        group, child = legacy.TECH[action][0].split('.')
        value = card['children'][group][child]
        wing = 'fh' if action.startswith('fh_') else 'bh' if action.startswith('bh_') else 'table'
        aptitude = (.38 * value + .24 * legacy.core.gg(card, state, 'receive')
                    + .17 * 120 + .11 * legacy.core.gg(card, state, 'table')
                    + .10 * legacy.core.gg(card, state, wing))
        fit = legacy.fit(action, ball, pos, scenario)
        base_weight = max(.006, min(9, math.exp((aptitude - 115) / 27 + temperature * fit / 13)))
        style = _style_multiplier(state, action)
        candidates.append(dict(action=action, aptitude=aptitude, fit=fit,
                               base_weight=base_weight, style_multiplier=style,
                               weight=base_weight * style))
    total = sum(item['weight'] for item in candidates)
    for item in candidates:
        item['probability'] = item['weight'] / total
    return dict(scenario=scenario, decision_read=decision_read,
                fit_temperature=temperature, candidates=candidates)


def play_match(cards, seed, *, keep_points=True, fatigue=(25, 25), max_games=7):
    """Execute a legacy BO7 with audited optional decision-fit sensitivity.

    The original choice callback is restored even if the game raises. Cards are
    read-only. The audit records draws and their actual contemporaneous context;
    it is separate from the immutable 608-career calibration evidence.
    """
    saved = legacy.choose_policy
    audit = []

    def choose(card, state, ball, pos, rng):
        record = action_distribution(card, state, ball, pos)
        candidates = record['candidates']
        chosen = rng.choices([c['action'] for c in candidates],
                             weights=[c['weight'] for c in candidates])[0]
        record.update(player_id=card.get('player_id'), position=pos,
                      ball=copy.deepcopy(ball), chosen=chosen)
        audit.append(record)
        return chosen

    try:
        legacy.choose_policy = choose
        result = legacy.play_match(cards, seed=seed, keep_points=keep_points,
                                   fatigue=fatigue, max_games=max_games)
    finally:
        legacy.choose_policy = saved
    result['tactical_patch'] = PATCH_TAG
    result['tactical_choice_audit'] = audit
    return result
