"""Preference priors, temporal separation and unchanged match mathematics."""
import copy
import hashlib
import math
import random
import unittest

import Card
import Game
from Game import v118 as new
from Game import preferences_v118 as pref
from Game import engine_v117 as engine
from common import canonical_json
import specialist_rubber_v116 as rubber


def card(pid='v118_test', *, hand='right', style='attacker', face='inverted'):
    result = Card.make_ma18()
    result.update(player_id=pid, source_prototype='SYNTHETIC', hand=hand, style=style,
                  rubbers=dict(fh='inverted', bh=face))
    if face == 'anti_spin':
        result['experimental_anti_spin'] = True
    return result


def profile(**changes):
    axes = dict.fromkeys(pref.AXES, .5)
    axes.update(changes)
    return dict(version=pref.STYLE_VERSION, axes=axes)


def context(c, *, position='good', spin='top', length='long', origin='rally'):
    state = engine.core.warmup(c, random.Random(11881), 25)
    ball = dict(origin=origin, spin=spin, pace=125., quality=125., landed='fh', target='fh',
        length=length, return_state='neutral_return', backspin_strength=125. if spin == 'back' else 0.,
        spin_strength=125., arc='normal')
    plan = 'chop_heavy' if c['style'] == 'modern_chopper' else 'patient_loop'
    if c['rubbers']['bh'] in ('short_pips', 'raw_pips'):
        plan = 'pips_early_pressure'
    elif c['rubbers']['bh'] in ('long_pips', 'anti_spin') and c['style'] != 'modern_chopper':
        plan = 'long_pips_reverse_hold'
    return state, ball, engine.action_distribution(c, state, ball, position, plan)


class PreferenceV118Tests(unittest.TestCase):
    def test_registered_axes_reject_unknown_nonfinite_boolean_and_out_of_range(self):
        for change in ({'risk': True}, {'risk': float('nan')}, {'risk': 2.}, {'unknown': .7}):
            with self.subTest(change=change):
                c = card(); c['style_profile'] = profile(**change)
                with self.assertRaises(ValueError):
                    pref.axes_of(c)
        c = card(); c['style_profile'] = profile(); del c['style_profile']['axes']['risk']
        with self.assertRaises(ValueError):
            pref.axes_of(c)

    def test_neutral_and_observation_only_preferences_return_the_original_pool(self):
        c = card(); state, ball, options = context(c)
        for declaration in (None, profile(), profile(rally=1., away_table=0., spin_variation=1.)):
            with self.subTest(declaration=declaration):
                if declaration is not None:
                    c['style_profile'] = declaration
                self.assertIs(pref.apply_preferences(options, c, state, ball, 'good'), options)

    def test_preference_changes_choice_without_touching_card_or_state(self):
        c = card(); c['style_profile'] = profile(forehand_use=1., backhand_use=0., initiative=.9)
        state, ball, options = context(c)
        before = canonical_json([c, state, options])
        adjusted = pref.apply_preferences(options, c, state, ball, 'good')
        self.assertEqual(canonical_json([c, state, options]), before)
        self.assertEqual([x['action'] for x in options], [x['action'] for x in adjusted])
        base_fh = sum(x['probability'] for x in options if x['wing'] == 'fh')
        new_fh = sum(x['probability'] for x in adjusted if x['wing'] == 'fh')
        self.assertGreater(new_fh, base_fh)
        self.assertAlmostEqual(sum(x['probability'] for x in adjusted), 1., places=12)

    def test_risk_does_not_override_limited_or_bad_arrival(self):
        c = card()
        for position in ('limited', 'bad'):
            state, ball, options = context(c, position=position)
            c['style_profile'] = profile(risk=1.)
            high = pref.apply_preferences(options, c, state, ball, position)
            c['style_profile'] = profile(risk=0.)
            low = pref.apply_preferences(options, c, state, ball, position)
            self.assertEqual(high, low)
            self.assertIs(high, options)

    def test_weak_preferred_wing_does_not_receive_artificial_proficiency(self):
        c = card()
        c['children']['fh'] = dict.fromkeys(c['children']['fh'], 60)
        c['children']['bh'] = dict.fromkeys(c['children']['bh'], 145)
        c = Card.recompute(c)
        state, ball, _ = context(c, position='bad')
        ball['landed'] = 'bh'
        options = engine.action_distribution(c, state, ball, 'bad', 'patient_loop')
        c['style_profile'] = profile(forehand_use=1., backhand_use=0., risk=1.)
        adjusted = pref.apply_preferences(options, c, state, ball, 'bad')
        base_fh = sum(x['probability'] for x in options if x['wing'] == 'fh')
        preferred_fh = sum(x['probability'] for x in adjusted if x['wing'] == 'fh')
        self.assertGreater(preferred_fh, base_fh)
        self.assertLess(preferred_fh, .5)
        self.assertEqual(set(c['children']['fh'].values()), {60})

    def test_first_three_axis_requires_an_actual_early_phase(self):
        c = card(); c['style_profile'] = profile(first_three=1.)
        state, ball, options = context(c)
        self.assertIs(pref.apply_preferences(options, c, state, ball, 'good'), options)
        ball['origin'] = 'service_return'
        self.assertNotEqual(pref.apply_preferences(options, c, state, ball, 'good'), options)

    def test_all_style_multipliers_are_bounded_and_only_legal_candidates_remain(self):
        for hand in ('right', 'left'):
            for face in ('inverted', 'short_pips', 'raw_pips', 'long_pips', 'anti_spin'):
                c = card(hand=hand, face=face)
                c['style_profile'] = profile(**{name: float(i % 2) for i, name in enumerate(pref.AXES)})
                for position in ('good', 'limited', 'bad'):
                    for spin in ('top', 'back', 'dead'):
                        with self.subTest(hand=hand, face=face, position=position, spin=spin):
                            state, ball, options = context(c, position=position, spin=spin)
                            adjusted = pref.apply_preferences(options, c, state, ball, position)
                            self.assertEqual([(x['action'], x['wing']) for x in adjusted],
                                             [(x['action'], x['wing']) for x in options])
                            for item in adjusted:
                                material = rubber.rubber_for(c, item['wing'])
                                self.assertTrue(rubber.legal_action(item['action'], material, ball, position))
                                factor = pref.multiplier(pref.axes_of(c), c, state, ball, position, item)
                                self.assertTrue(.9 - 1e-12 <= factor <= 1.1 + 1e-12)

    def test_projection_excludes_private_personality_potential_and_learning(self):
        c = card(); c['style_profile'] = profile(initiative=.7)
        c['personality_profile'] = dict(secret='will not enter the engine')
        projected = new.match_card(c)
        self.assertIn('style_profile', projected)
        for name in ('personality_profile', 'PA', 'pa_range', 'learning_factor', 'historical_reference', 'xp'):
            self.assertNotIn(name, projected)
        self.assertEqual(set(projected['style_profile']), {'version', 'axes'})


class MatchV118Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = [card('v118_A'), card('v118_B', hand='left')]
        cls.neutral = {}
        cls.old = {}
        for mode in ('summary', 'full'):
            cls.old[mode] = Game.play_match(cls.cards, 118801, f'neutral-{mode}',
                ruleset=Game.V117_RULESET, detail_level=mode)
            neutral_cards = copy.deepcopy(cls.cards)
            for c in neutral_cards:
                c['style_profile'] = profile()
            cls.neutral[mode] = new.play_match(neutral_cards, 118801, f'neutral-{mode}', detail_level=mode)

    def test_neutral_replays_exact_points_scores_exposures_and_load(self):
        for mode in self.neutral:
            for key in ('games', 'games_won', 'winner', 'points', 'exposure_by_player', 'workload'):
                with self.subTest(mode=mode, key=key):
                    self.assertEqual(self.neutral[mode][key], self.old[mode][key])
            self.assertTrue(all(x['weighted_calls'] == 0 for x in self.neutral[mode]['style_preference_audit']))

    def test_changing_narrative_personality_cannot_change_result_or_input_digest(self):
        a, b = copy.deepcopy(self.cards), copy.deepcopy(self.cards)
        a[0]['personality_profile'] = dict(cues=['reserved'], sensitive='not match data')
        b[0]['personality_profile'] = dict(cues=['expressive'], sensitive='different')
        ma = new.play_match(a, 118802, 'personality-control')
        mb = new.play_match(b, 118802, 'personality-control')
        self.assertEqual(ma, mb)

    def test_non_neutral_real_execution_is_repeatable_and_inputs_are_immutable(self):
        cards = copy.deepcopy(self.cards)
        cards[0]['style_profile'] = profile(forehand_use=.9, initiative=.8, risk=.75)
        before = canonical_json(cards)
        a = new.play_match(cards, 118803, 'style-real')
        b = new.play_match(cards, 118803, 'style-real')
        self.assertEqual(a, b)
        self.assertEqual(canonical_json(cards), before)
        self.assertGreater(a['style_preference_audit'][0]['weighted_calls'], 0)
        self.assertTrue(new.verify_log(a))
        self.assertTrue(all('points' not in game for game in a['games']))

    def test_compact_log_retains_style_audit_and_actual_full_hash(self):
        full = self.neutral['full']
        compact = new.compact_log(full)
        self.assertTrue(new.verify_log(compact))
        self.assertEqual(compact['style_preference_audit'], full['style_preference_audit'])
        self.assertEqual(compact['full_log_sha256'], full['log_sha256'])
        self.assertTrue(all('points' not in game for game in compact['games']))
        self.assertEqual(new.compact_log(compact), compact)

    def test_review_binds_actual_player_and_rejects_foreign_rule_or_bad_hash(self):
        match = self.neutral['summary']
        state = dict(id=self.cards[0]['player_id'], month=0)
        event = new.review_event(state, match, state['id'])
        self.assertEqual(event['participant_id'], state['id'])
        self.assertLessEqual(len(event['paths']), 3)
        with self.assertRaises(ValueError):
            new.review_event(state, self.old['summary'], state['id'])
        tampered = copy.deepcopy(match); tampered['winner'] = 1 - tampered['winner']
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            new.verify_log(tampered)

    def test_actual_short_format_is_light_only_and_performance_only(self):
        cards = [new.match_card(c) for c in self.cards]
        self.assertTrue(all('PA' not in c for c in cards))
        result = new.play_match(cards, 118804, 'light-bo3', max_games=3)
        self.assertEqual(max(result['games_won']), 2)
        with self.assertRaisesRegex(ValueError, 'BO7'):
            new.play_match(cards, 118804, 'bad-full-bo3', max_games=3, detail_level='full')


if __name__ == '__main__':
    unittest.main()
