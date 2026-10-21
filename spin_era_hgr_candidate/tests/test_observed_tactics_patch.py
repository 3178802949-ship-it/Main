"""Checks of observable tactical inference and preserved V1.1.6 formulas."""
import copy
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import SCHEMA
from Game import observed_tactics as observed
import career_v114 as fixtures
import game_v112 as core
from card_training_v112 import compute_card


class ScriptedRng:
    def __init__(self, rolls):
        self.rolls = iter(rolls)

    def randint(self, a, b):
        value = next(self.rolls)
        if not a <= value <= b:
            raise AssertionError((a, b, value))
        return value

    def random(self):
        return .5


def setup():
    card = fixtures.ordinary_card(SCHEMA)
    computed = compute_card(card, SCHEMA)
    card['G9'] = computed['G9']
    card['player_id'] = 'observed-self'
    other = copy.deepcopy(card)
    other['player_id'] = 'observed-other'
    cards = [card, other]
    states = [core.warmup(c, random.Random(880 + i)) for i, c in enumerate(cards)]
    return cards, states


def expose(state, *, weak='bh', count=8):
    for side in ('fh', 'bh'):
        for i in range(count):
            observed.observe_shot(state, stroke_side=side,
                quality=98 if side == weak else 142, action_family='chop',
                error=side == weak and i % 2 == 0)


class ObservedTacticsTests(unittest.TestCase):
    def test_observation_changes_inference_without_hidden_inputs(self):
        _, states = setup()
        self.assertIsNone(observed.inferred_weakness(states[0]))
        expose(states[0], weak='bh')
        self.assertEqual(observed.inferred_weakness(states[0]), 'bh')
        expose(states[1], weak='fh')
        self.assertEqual(observed.inferred_weakness(states[1]), 'fh')
        self.assertEqual(observed.inferred_policy(states[0]), 'defensive_pivot')

    def test_unknown_side_is_not_assigned_a_forehand_or_backhand(self):
        state = {}
        observed.observe_shot(state, stroke_side='unknown', quality=125,
                              action_family='loop', length='long')
        self.assertEqual(state['observed_opponent']['total'], 1)
        self.assertEqual(sum(v['count'] for v in state['observed_opponent']['by_side'].values()), 0)
        observed.observe_shot(state, stroke_side='middle', quality=110,
                              action_family='push', length='short')
        self.assertEqual(state['observed_opponent']['by_side']['table']['count'], 1)
        self.assertIsNone(observed.inferred_weakness(state))

    def test_invalid_observation_is_rejected_without_mutation(self):
        for fields in (dict(quality=float('nan')), dict(stroke_side='left'),
                       dict(length='forever'), dict(error=1), dict(quality=True)):
            args = dict(stroke_side='fh', quality=120, action_family='loop')
            args.update(fields)
            state = {}
            with self.assertRaises(ValueError):
                observed.observe_shot(state, **args)
            self.assertEqual(state, {})

    def test_opponent_hidden_daily_form_cannot_change_self_scouting(self):
        cards, states = setup()
        expose(states[0])
        altered_cards, altered_states = copy.deepcopy(cards), copy.deepcopy(states)
        for group in core.G:
            altered_cards[1]['G9'][group] = 25 if group == 'fh' else 150
            altered_states[1]['g_roll'][group] = -35 if group == 'bh' else 35
        altered_states[1]['policy'] = 'wide_angles'
        before = copy.deepcopy(cards)
        original = observed.between_games(cards, states, random.Random(778), 1)
        altered = observed.between_games(altered_cards, altered_states, random.Random(778), 1)
        self.assertEqual(original[0], altered[0])
        self.assertEqual(cards, before)
        self.assertEqual(original[0]['knowledge_source'], 'OBSERVED_ONLY_V1')
        self.assertEqual(original[0]['opponent_read_estimate'], 120)

    def test_original_threshold_form_repair_and_psychology_are_preserved(self):
        cards, states = setup()
        # Original and observable versions use the same opponent read input in
        # this controlled case, so their non-knowledge results must be identical.
        for card in cards:
            card['G9']['read'] = 120
        for state in states:
            state['g_roll']['read'] = 0
            state['g_roll']['fh'] = -7
            state['read_bonus'] = 0
            expose(state)
        orig_states = copy.deepcopy(states)
        expected = core.between_games(cards, orig_states, ScriptedRng([1, 1, 1, 20, 1, 1, 1, 81]), 1)
        actual = observed.between_games(cards, states, ScriptedRng([1, 1, 1, 20, 1, 1, 1, 81]), 1)
        self.assertEqual(actual[0]['thresholds'], expected[0]['thresholds'])
        for a, b in zip(actual, expected):
            for key in ('successes', 'psychology', 'form_repair', 'read_delta'):
                self.assertEqual(a[key], b[key])
        self.assertEqual(actual[0]['psychology']['type'], 'breakthrough')
        self.assertEqual(actual[1]['psychology']['type'], 'collapse')
        self.assertEqual(states[0]['g_roll']['fh'], -3)
        self.assertEqual(states[0]['read_bonus'], 8)

    def test_psychology_boundaries_reuse_the_exact_legacy_rolls(self):
        for roll in (1, 20, 21, 80, 81, 100):
            cards, states = setup()
            extras = [1, -1] if 21 <= roll <= 80 else []
            scripted = [100, 100, 100, roll, *extras, 100, 100, 100, 50, 0, 0]
            expected = core.mental_check(ScriptedRng([roll, *extras]))
            actual = observed.between_games(cards, states, ScriptedRng(scripted), 2)
            self.assertEqual(actual[0]['psychology'], expected)

    def test_scout_roll_success_without_evidence_does_not_create_weakness(self):
        cards, states = setup()
        result = observed.between_games(cards, states,
            ScriptedRng([1, 1, 1, 20, 1, 1, 1, 20]), 1)
        for item, state in zip(result, states):
            self.assertTrue(item['successes']['weak'])
            self.assertFalse(item['evidence_sufficient'])
            self.assertIsNone(item['weakness'])
            self.assertFalse(item['target_usable'])
            self.assertFalse(state['execute_weakness'])

    def test_realtime_counter_uses_observed_pattern_not_actual_policy(self):
        cards, states = setup()
        expose(states[0])
        states[0]['points_seen'] = 20
        states[0]['policy'] = 'third_ball_fh'
        states[1]['policy_stage'] = 3
        changed = copy.deepcopy(states)
        changed[1]['policy'] = 'receive_initiative'
        changed[1]['g_roll']['read'] = 35
        observed.attempt_in_game_adaptation(cards, states, ScriptedRng([1]), [3, 3])
        observed.attempt_in_game_adaptation(cards, changed, ScriptedRng([1]), [3, 3])
        self.assertEqual(states[0], changed[0])
        event = states[0]['policy_events'][0]
        self.assertEqual(event['opponent_policy'], 'defensive_pivot')
        self.assertTrue(event['inferred_not_verified'])
        expected_threshold = core.clamp(25 + .41 * (core.gg(cards[0], states[0], 'read') - 110)
                                        + .09 * (20 - 6), 15, 67) * .9
        self.assertEqual(event['threshold'], round(expected_threshold, 1))
        self.assertEqual(states[0]['policy_stage'], 1)

    def test_no_observed_policy_cannot_be_revealed_by_successful_counter_roll(self):
        cards, states = setup()
        states[0]['points_seen'] = 20
        states[1]['policy_stage'] = 3
        before = copy.deepcopy(states[0])
        observed.attempt_in_game_adaptation(cards, states, ScriptedRng([1]), [3, 3])
        self.assertEqual(states[0], before)

    def test_counter_stage_limit_and_existing_cooldown_are_preserved(self):
        cards, states = setup()
        for state in states:
            expose(state)
            state.update(policy_stage=1, points_seen=30, last_counter_seen=20)
        before = copy.deepcopy(states)
        observed.attempt_in_game_adaptation(cards, states, ScriptedRng([]), [3, 3])
        self.assertEqual(states, before)
        for state in states:
            state.update(policy_stage=3, points_seen=100)
        before = copy.deepcopy(states)
        observed.attempt_in_game_adaptation(cards, states, ScriptedRng([]), [6, 6])
        self.assertEqual(states, before)


if __name__ == '__main__':
    unittest.main()
