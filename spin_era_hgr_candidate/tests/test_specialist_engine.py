"""Behavioral integration checks for physical lines and specialist contacts."""
from collections import Counter
import copy
from pathlib import Path
import random
import statistics
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Card
import Game
from Game import geometry as geo
from Game import observed_tactics as observed
from Game import specialist_engine as engine
import specialist_rubber_v116 as rubber


def make_card(player_id='geometry_synthetic', hand='right', style='attacker', rubbers=None):
    value = Card.make_ma18()
    value.update(player_id=player_id, name_zh='独立合成几何输入', source_prototype='SYNTHETIC',
                 hand=hand, style=style, rubbers=rubbers or dict(fh='inverted', bh='inverted'))
    value['children'] = {g: dict.fromkeys(children, 120) for g, children in value['children'].items()}
    return Card.recompute(value)


def state_for(card, end, *, x=0., depth=1.12):
    sign = -1 if end == 0 else 1
    value = engine.core.warmup(card, random.Random(311), 25)
    value.update(hgr_position=dict(x=x, y=sign * depth, recovery=1., momentum_x=0., momentum_y=0., movement_load=0.),
                 hgr_contact=dict(x=x, y=sign * 1.18), hgr_rally_load=0., hgr_match_load=0.)
    return value


def ball_for(end, x=.72, length='long', **changes):
    value = dict(origin='rally', spin='top', pace=125, quality=120, landed='fh', target='fh',
                 length=length, return_state='neutral_return', backspin_strength=0, spin_strength=125,
                 absolute_target=dict(x=x, y=(-1 if end == 0 else 1) * geo.LENGTH_DEPTH[length]))
    value.update(changes)
    return value


def probabilities(candidates, key):
    return {name: sum(c['probability'] for c in candidates if c[key] == name)
            for name in {c[key] for c in candidates}}


class SpecialistEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        attacker = make_card('integration_attacker')
        defender = make_card('integration_specialist', style='modern_chopper')
        defender['children']['fh'] = dict.fromkeys(defender['children']['fh'], 95)
        defender['children']['bh'] = dict.fromkeys(defender['children']['bh'], 140)
        defender = Card.recompute(defender)
        cls.pro_inputs = [attacker, defender]
        cls.pro_input_copy = copy.deepcopy(cls.pro_inputs)
        cls.pro_log = Game.play_match(cls.pro_inputs, 1168103, 'integration-two-wing-chop',
                                     ruleset=Game.PATCH_RULESET)
        pips = make_card('integration_pips', hand='left',
                         rubbers=dict(fh='short_pips', bh='raw_pips'))
        long_pips = make_card('integration_long_pips', style='modern_chopper',
                             rubbers=dict(fh='inverted', bh='long_pips'))
        cls.pips_inputs = [pips, long_pips]
        cls.pips_log = Game.play_match(cls.pips_inputs, 1168104, 'integration-pips-contacts',
                                      ruleset=Game.PATCH_RULESET)

    def test_all_four_hands_change_actual_wing_decisions_for_diagonal_paths(self):
        expected = {('right', 'right'): 'fh', ('left', 'right'): 'bh',
                    ('right', 'left'): 'bh', ('left', 'left'): 'fh'}
        for (hitter_hand, receiver_hand), wing in expected.items():
            with self.subTest(hitter=hitter_hand, receiver=receiver_hand):
                receiver = make_card(hand=receiver_hand)
                state = state_for(receiver, 1)
                source = geo.lane_to_point('fh', hitter_hand, 0)
                ball = ball_for(1, x=-source['x'])
                pos, _, mapped, movement = engine.reach(receiver, state, ball, random.Random(1), 3, 1)
                self.assertEqual(mapped, wing)
                self.assertTrue(movement['mapping_resolved'])
                choices = engine.action_distribution(receiver, state, dict(ball, landed=mapped), pos, 'patient_loop')
                by_wing = probabilities(choices, 'wing')
                self.assertGreater(by_wing[wing], .6)
                self.assertGreater(by_wing[wing], by_wing['bh' if wing == 'fh' else 'fh'])

    def test_same_physical_ball_hand_switch_changes_action_choices_without_g_or_reach_bonus(self):
        right, left = make_card(hand='right'), make_card(hand='left')
        states = [state_for(right, 1), state_for(left, 1)]
        self.assertEqual(right['G9'], left['G9'])
        self.assertEqual(states[0]['g_roll'], states[1]['g_roll'])
        ball = ball_for(1, x=-.72)
        results = [engine.reach(c, s, ball, random.Random(1), 3, 1)
                   for c, s in zip((right, left), states)]
        self.assertEqual(results[0][0:2], results[1][0:2])
        self.assertEqual(results[0][3]['distance_m'], results[1][3]['distance_m'])
        a, b = [probabilities(engine.action_distribution(c, s, dict(ball, landed=r[2]), r[0], 'patient_loop'), 'wing')
                for c, s, r in zip((right, left), states, results)]
        self.assertGreater(a['fh'], b['fh'] + .35)

    def test_mirrored_body_ball_and_hand_preserve_actual_reach_and_decision_probabilities(self):
        right, left = make_card(hand='right'), make_card(hand='left')
        a, b = state_for(right, 1, x=.3), state_for(left, 1, x=-.3)
        a['hgr_position'].update(momentum_x=.25, recovery=.6)
        b['hgr_position'].update(momentum_x=-.25, recovery=.6)
        balls = [ball_for(1, x=-.85), ball_for(1, x=.85)]
        reached = [engine.reach(c, s, ball, random.Random(17), 5, 1)
                   for c, s, ball in zip((right, left), (a, b), balls)]
        self.assertEqual(reached[0][0:3], reached[1][0:3])
        self.assertEqual(reached[0][3]['distance_m'], reached[1][3]['distance_m'])
        distributions = [engine.action_distribution(c, s, dict(ball, landed=r[2]), r[0], 'spin_pace_mix')
                         for c, s, ball, r in zip((right, left), (a, b), balls, reached)]
        self.assertEqual(distributions[0], distributions[1])
        self.assertEqual(engine.core.gg(right, a, 'read'), engine.core.gg(left, b, 'read'))

    def test_target_policy_uses_observed_weak_side_and_actual_opponent_hand(self):
        own = make_card()
        own_state = state_for(own, 0)
        for _ in range(4):
            observed.observe_shot(own_state, stroke_side='fh', quality=95, action_family='counter')
            observed.observe_shot(own_state, stroke_side='bh', quality=140, action_family='counter')
        distributions = []
        for hand in ('right', 'left'):
            other = make_card('opponent', hand=hand)
            distributions.append(engine.target_distribution(own, own_state, ball_for(0),
                other, state_for(other, 1), 'fh_fast_loop', 'observed_weak_side', 0))
        mean_x = [sum(c['target']['x'] * c['probability'] for c in d) for d in distributions]
        self.assertLess(mean_x[0], -.2)
        self.assertGreater(mean_x[1], .2)
        self.assertEqual(observed.inferred_weakness(own_state), 'fh')

    def test_target_policy_does_not_read_opponent_hidden_ability_or_daily_rolls(self):
        own, other = make_card(), make_card('opponent')
        own_state, other_state = state_for(own, 0), state_for(other, 1, x=.3)
        ball = ball_for(0)
        a = engine.target_distribution(own, own_state, ball, other, other_state,
                                       'fh_fast_loop', 'wide_movement', 0)
        changed = copy.deepcopy(other)
        changed['children'] = {g: dict.fromkeys(values, 30 if g == 'fh' else 150)
                               for g, values in changed['children'].items()}
        changed = Card.recompute(changed)
        altered_state = copy.deepcopy(other_state)
        altered_state['g_roll'] = dict.fromkeys(altered_state['g_roll'], -50)
        altered_state['read_bonus'] = 100
        b = engine.target_distribution(own, own_state, ball, changed, altered_state,
                                       'fh_fast_loop', 'wide_movement', 0)
        self.assertEqual(a, b)

    def test_target_prediction_uses_outgoing_spin_for_chopper_interception(self):
        own, other = make_card(), make_card('opponent', style='modern_chopper')
        own_state, other_state = state_for(own, 0), state_for(other, 1, depth=1.7)
        a = engine.target_distribution(own, own_state, ball_for(0), other, other_state,
            'fh_chop', 'wide_movement', 0, outgoing_spin='back')
        b = engine.target_distribution(own, own_state, ball_for(0), other, other_state,
            'fh_fast_loop', 'wide_movement', 0, outgoing_spin='top')
        self.assertTrue(all(c['geometry']['receiver_contact']['y'] == 1.18 for c in a))
        self.assertTrue(all(c['geometry']['receiver_contact']['y'] == 1.72 for c in b))

    def test_real_lateral_distance_changes_arrival_distribution_with_paired_noise(self):
        card = make_card()
        ball = ball_for(1, x=.85)
        near, far = state_for(card, 1, x=1., depth=1.18), state_for(card, 1, x=-.9, depth=1.9)
        grades = []
        for base in (near, far):
            grades.append([engine.reach(card, copy.deepcopy(base), ball, random.Random(700 + seed), 5, 1)
                           for seed in range(128)])
        self.assertGreater(statistics.mean(r[1] for r in grades[0]),
                           statistics.mean(r[1] for r in grades[1]) + 10)
        self.assertGreater(sum(r[0] == 'good' for r in grades[0]), sum(r[0] == 'good' for r in grades[1]))
        self.assertLess(sum(r[0] == 'miss' for r in grades[0]), sum(r[0] == 'miss' for r in grades[1]))
        self.assertGreater(len({r[0] for r in grades[0]}), 1)
        self.assertGreater(len({r[0] for r in grades[1]}), 1)

    def test_short_ball_requires_real_forward_movement_from_deep_defence(self):
        card = make_card(style='modern_chopper')
        base = state_for(card, 1, depth=1.75)
        long = engine.reach(card, copy.deepcopy(base), ball_for(1, x=0.), random.Random(19), 4, 1)
        short = engine.reach(card, copy.deepcopy(base), ball_for(1, x=0., length='short'), random.Random(19), 4, 1)
        self.assertGreater(short[3]['distance_m'], long[3]['distance_m'] + 1.)
        self.assertEqual(short[3]['depth_direction'], 'forward')
        self.assertLess(short[1], long[1] - 8)

    def test_movement_load_accumulates_and_changes_reach_before_any_skill_change(self):
        card = make_card()
        state = state_for(card, 1)
        before = copy.deepcopy(state['g_roll'])
        ball = ball_for(1, x=.95)
        first = engine.reach(card, state, ball, random.Random(55), 7, 1)
        for _ in range(80):
            engine.reach(card, state, ball, random.Random(55), 7, 1)
        last = engine.reach(card, state, ball, random.Random(55), 7, 1)
        self.assertGreater(last[3]['load_before'], first[3]['load_after'])
        self.assertLess(last[1], first[1] - 3)
        self.assertEqual(before, state['g_roll'])
        self.assertEqual(state['p_eff'], state_for(card, 1)['p_eff'])

    def test_professional_chop_quality_uses_each_own_wing_and_preserves_card(self):
        self.assertEqual(self.pro_inputs, self.pro_input_copy)
        chops = [s for g in self.pro_log['games'] for p in g['points'] for s in p['shots']
                 if s.get('action_family') == 'chop' and s['player'] == 1]
        by_wing = {wing: [s for s in chops if s['stroke_side'] == wing] for wing in ('fh', 'bh')}
        self.assertGreaterEqual(len(by_wing['fh']), 3)
        self.assertGreaterEqual(len(by_wing['bh']), 3)
        for wing, shots in by_wing.items():
            self.assertTrue(all(s['technique_path'] == wing + '.defense' for s in shots))
            self.assertGreater(len({s['out_quality'] for s in shots}), 1)
        self.assertGreater(statistics.mean(s['out_quality'] for s in by_wing['bh']),
                           statistics.mean(s['out_quality'] for s in by_wing['fh']) + 20)
        states = {s['return_state'] for s in chops}
        self.assertIn('direct_point_lost', states)
        self.assertTrue(states - {'direct_point_lost'})

    def test_equipment_contacts_enter_real_logs_and_path_statistics(self):
        shots = [s for g in self.pips_log['games'] for p in g['points'] for s in p['shots']]
        specialized = [s for s in shots if '_sp_' in s['action'] or '_lp_' in s['action']]
        self.assertTrue(any('_sp_' in s['action'] for s in specialized))
        self.assertTrue(any('_lp_' in s['action'] for s in specialized))
        self.assertEqual({s['rubber'] for s in specialized}, {'short_pips', 'raw_pips', 'long_pips'})
        for shot in specialized:
            self.assertEqual(shot['technique_path'], rubber.action_spec(shot['action'])['technique_path'])
            self.assertEqual(shot['action_family'], rubber.action_spec(shot['action'])['family'])
            self.assertIn(shot['action'], self.pips_log['technique_distribution'])
        paths = Counter(s['technique_path'] for s in shots if s.get('technique_path'))
        self.assertEqual(dict(paths), self.pips_log['technique_path_distribution'])
        self.assertTrue(Game.verify_log(self.pips_log))

    def test_attempted_specialist_actions_obey_actual_incoming_spin_and_length(self):
        count = 0
        for game in self.pips_log['games']:
            for point in game['points']:
                source = point['shots'][0]
                incoming = dict(spin=source['spin'], length=source['length'], quality=source['quality'])
                for shot in point['shots'][1:]:
                    if '_sp_' in shot['action'] or '_lp_' in shot['action']:
                        self.assertTrue(rubber.legal_action(shot['action'], shot['rubber'], incoming, shot['reach']), shot)
                        count += 1
                    if shot.get('return_state') != 'direct_point_lost' and 'spin' in shot:
                        incoming = dict(spin=shot['spin'], length=shot['length'], quality=shot['out_quality'])
        self.assertGreater(count, 10)

    def test_long_rally_actual_trace_accumulates_load_and_has_counterattack_contacts(self):
        checked = 0
        for game in self.pips_log['games']:
            for point in game['points']:
                if point['strokes'] < 6:
                    continue
                last = {}
                for shot in point['shots']:
                    if 'movement' not in shot:
                        continue
                    movement = shot['movement']
                    player = shot['player']
                    self.assertGreater(movement['load_after'], movement['load_before'])
                    if player in last:
                        self.assertGreaterEqual(movement['load_before'] + .00002, last[player])
                        checked += 1
                    last[player] = movement['load_after']
        self.assertGreater(checked, 3)
        shots = [s for g in self.pips_log['games'] for p in g['points'] for s in p['shots']]
        self.assertTrue(any(s.get('counterattack') and s.get('action_family') in ('attack', 'counter', 'open', 'flip', 'slow_loop')
                            for s in shots))

    def test_patient_loop_and_pace_mix_change_real_action_probabilities(self):
        card, state, ball = make_card(), state_for(make_card(), 0), ball_for(0, spin='back')
        state['hgr_last_family'] = 'slow_loop'
        patient = probabilities(engine.action_distribution(card, state, ball, 'good', 'patient_loop'), 'family')
        mixed = probabilities(engine.action_distribution(card, state, ball, 'good', 'spin_pace_mix'), 'family')
        self.assertGreater(patient.get('slow_loop', 0), mixed.get('slow_loop', 0))
        self.assertGreater(mixed.get('attack', 0) + mixed.get('counter', 0),
                           patient.get('attack', 0) + patient.get('counter', 0))


if __name__ == '__main__':
    unittest.main()
