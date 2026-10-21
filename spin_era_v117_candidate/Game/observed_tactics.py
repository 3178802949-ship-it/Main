"""Tactical knowledge built from visible exchanges, never opponent daily ratings.

Self checks, psychological rolls and counter thresholds retain the frozen V1.1.6
formulas. Only the source of knowledge about an opponent changes. Observations
are provisional match state; they do not change a card, G, P, XP or PA.
"""
from __future__ import annotations

import math

from common import RUNTIME  # Bootstrap the preserved runtime imports.
import game_v112 as core

OBSERVATION_VERSION = 'OBSERVED_ONLY_V1'
MIN_SIDE_SAMPLES = 3
MIN_POLICY_SAMPLES = 6
UNOBSERVED_READ_ESTIMATE = 120.0


def _ledger(state):
    if 'observed_opponent' not in state:
        state['observed_opponent'] = dict(version=OBSERVATION_VERSION, total=0,
            by_side={side: dict(count=0, quality_sum=0.0, errors=0)
                     for side in ('fh', 'bh', 'table')}, families={}, lengths={})
    return state['observed_opponent']


def observe_shot(observer_state, *, stroke_side, quality, action_family,
                 length='long', error=False):
    """Record a visible opponent contact/error without accessing an opponent card.

    Ambiguous/unknown anatomy is not assigned a forehand or backhand. Clearly
    identifiable table-touch families can still inform the table category.
    """
    if stroke_side not in ('fh', 'bh', 'middle', 'table', 'unknown', None):
        raise ValueError('invalid observed stroke side')
    if type(quality) not in (int, float) or not math.isfinite(quality) or not 0 <= quality <= 200:
        raise ValueError('invalid observed shot quality')
    if not isinstance(action_family, str) or not action_family:
        raise ValueError('observed action family required')
    if length not in ('short', 'half', 'long') or type(error) is not bool:
        raise ValueError('invalid observed length or error flag')
    ledger = _ledger(observer_state)
    family = action_family.lower()
    ledger['total'] += 1
    ledger['families'][family] = ledger['families'].get(family, 0) + 1
    ledger['lengths'][length] = ledger['lengths'].get(length, 0) + 1
    side = stroke_side if stroke_side in ('fh', 'bh', 'table') else None
    if side is None and any(label in family for label in ('push', 'touch', 'flick', 'flip')):
        side = 'table'
    if side is not None:
        entry = ledger['by_side'][side]
        entry['count'] += 1
        entry['quality_sum'] += quality
        entry['errors'] += int(error)
    return ledger


def _weakness_scores(state):
    observed = state.get('observed_opponent', {})
    scores = {}
    for side in ('fh', 'bh', 'table'):
        entry = observed.get('by_side', {}).get(side, {})
        count = entry.get('count', 0)
        if count >= MIN_SIDE_SAMPLES:
            # An inference about visible performance, not an estimate of hidden G.
            scores[side] = (entry['quality_sum'] / count
                            - 12.0 * entry.get('errors', 0) / count)
    return scores if len(scores) >= 2 else {}


def inferred_weakness(state):
    """Return the weakest *observed* category, or None without comparisons."""
    scores = _weakness_scores(state)
    return min(scores, key=lambda side: (scores[side], side)) if scores else None


def inferred_policy(state):
    """Classify a coarse observed pattern; this is a hypothesis, not hidden policy."""
    ledger = state.get('observed_opponent', {})
    total = ledger.get('total', 0)
    if total < MIN_POLICY_SAMPLES:
        return 'unknown'
    families = ledger.get('families', {})
    def share(*fragments):
        return sum(n for family, n in families.items()
                   if any(fragment in family for fragment in fragments)) / total
    if share('chop', 'lob', 'rescue') >= .40:
        return 'defensive_pivot'
    if share('flip', 'flick', 'twist') >= .35:
        return 'receive_initiative'
    # Forehand attacking volume supports a tentative third-ball posture, not a
    # claim that the opponent is targeting the observer's backhand.
    sides = ledger.get('by_side', {})
    if (share('open', 'loop', 'attack', 'counter') >= .45
            and sides.get('fh', {}).get('count', 0) / total >= .55):
        return 'third_ball_fh'
    if len([n for n in families.values() if n >= 2]) >= 3:
        return 'change_spin'
    return 'unknown'


def between_games(cards, state, rng, game_idx):
    """Apply the original checks with observable opponent evidence only.

    The opponent-read term uses an explicit neutral estimate (120). There is
    currently no calibrated observation model for an opponent's reading skill.
    No card or daily-form data from the other actor is accessed in this loop.
    """
    checks = []
    for idx in (0, 1):
        card = cards[idx]
        s = state[idx]
        rolls = {key: rng.randint(1, 100) for key in ('self', 'weak', 'execute')}
        t_self = int(core.clamp(51 + .38 * (core.gg(card, s, 'read') - 110), 25, 82))
        t_weak = int(core.clamp(46 + .40 * (core.gg(card, s, 'read') - 110)
                              - .14 * (UNOBSERVED_READ_ESTIMATE - 110), 22, 80))
        t_exec = int(core.clamp(48 + .42 * (core.gg(card, s, 'read') - 110)
                              + .08 * (core.gg(card, s, 'stable') - 110), 24, 82))
        thresholds = dict(self=t_self, weak=t_weak, execute=t_exec)
        ok = {key: rolls[key] <= thresholds[key] for key in rolls}
        fix = None
        if ok['self']:
            possible = [key for key in ('serve', 'receive', 'fh', 'bh', 'feet', 'table', 'spirit')
                        if s['g_roll'][key] < 0]
            if possible:
                key = min(possible, key=lambda item: s['g_roll'][item])
                delta = min(4, -s['g_roll'][key])
                s['g_roll'][key] += delta
                fix = dict(G=key, delta=delta)
        # Consume the same three tie-break draws as the original weak-side
        # selection, while comparing observed performance rather than true G.
        jitter = {side: .05 * rng.random() for side in ('fh', 'bh', 'table')}
        scores = _weakness_scores(s)
        weak = max(scores, key=lambda side: 127 - scores[side] + jitter[side]) if scores else None
        s['scouted_weakness'] = weak if ok['weak'] else None
        s['execute_weakness'] = ok['execute'] and ok['weak'] and weak is not None
        s['read_bonus'] = 4 * sum((ok['weak'], ok['execute']))
        psych = core.mental_check(rng)
        s['mental'] = psych['type']
        s['stable_bonus'] = psych['stable_delta']
        s['clutch_bonus'] = psych['clutch_extra_delta']
        value = dict(player=card.get('player_id', str(idx)), after_game=game_idx,
            rolls=rolls, thresholds=thresholds, successes=ok, psychology=psych,
            weakness=s['scouted_weakness'], target_usable=s['execute_weakness'],
            form_repair=fix, read_delta=s['read_bonus'], knowledge_source=OBSERVATION_VERSION,
            observed_samples=s.get('observed_opponent', {}).get('total', 0),
            evidence_sufficient=bool(scores), opponent_read_estimate=UNOBSERVED_READ_ESTIMATE,
            opponent_read_estimate_source='NEUTRAL_UNOBSERVED_NOT_REAL_DAILY_RATING')
        s['game_check_history'].append(value)
        checks.append(value)
    return checks


def attempt_in_game_adaptation(cards, state, rng, score, game_idx=0):
    """Retain V1.1.6 counter timing/rolls, using an inferred enemy posture."""
    if sum(score) < 6 or sum(score) % 6 != 0:
        return
    for i in (0, 1):
        st, card = state[i], cards[i]
        if st['policy_stage'] >= 3:
            continue
        stage_now = st['policy_stage']
        minimum_gap = (0, 12, 18)[stage_now]
        if st['points_seen'] - st.get('last_counter_seen', -999) < minimum_gap:
            continue
        read = core.gg(card, st, 'read')
        roll = rng.randint(1, 100)
        threshold = core.clamp(25 + .41 * (read - 110) + .09 * (st['points_seen'] - 6), 15, 67)
        threshold *= (0.9, 0.48, 0.25)[stage_now]
        if roll > threshold:
            continue
        enemy = inferred_policy(st)
        if enemy == 'unknown':
            # Passing a roll cannot reveal a strategy that has not been seen.
            continue
        st['last_counter_seen'] = st['points_seen']
        old = st['policy']
        counters = {'third_ball_fh': 'receive_initiative', 'receive_initiative': 'bh_squeeze',
                    'bh_squeeze': 'wide_angles', 'wide_angles': 'change_spin',
                    'change_spin': 'third_ball_fh', 'defensive_pivot': 'change_spin'}
        st['policy'] = counters.get(enemy, 'change_spin')
        if st['policy'] == old:
            st['policy'] = 'wide_angles' if old != 'wide_angles' else 'change_spin'
        st['policy_stage'] += 1
        st['counter_attempts'] += 1
        st['policy_events'].append(dict(game=game_idx + 1, point_at=sum(score),
            stage=st['policy_stage'], read_D100=roll, threshold=round(threshold, 1),
            opponent_policy=enemy, knowledge_source=OBSERVATION_VERSION,
            observed_samples=st.get('observed_opponent', {}).get('total', 0),
            inferred_not_verified=True, **{'from': old, 'to': st['policy'],
            'type': ['counter', 'counter_counter', 'counter_counter_counter'][min(2, st['policy_stage'] - 1)]}))
