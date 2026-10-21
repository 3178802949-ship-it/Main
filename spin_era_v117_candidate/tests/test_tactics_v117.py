"""Behavioral V1.1.7 checks: separate plans, actual contacts and replayable load."""
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
from common import canonical_json
from Game import engine_v117 as engine
from Game import tactics_v117 as plans
from Game import geometry as geo
from Game import observed_tactics as observed
import specialist_rubber_v116 as rubber


def make_card(pid='v117_synthetic', *, style='attacker', hand='right', rubbers=None, value=124):
    card = Card.make_ma18()
    card.update(player_id=pid, name_zh='独立合成专项测试卡', source_prototype='SYNTHETIC',
                hand=hand, style=style, rubbers=rubbers or dict(fh='inverted', bh='inverted'))
    card['children'] = {g: dict.fromkeys(sub, value) for g, sub in card['children'].items()}
    return Card.recompute(card)


def state_for(card, end=0, *, depth=1.12, x=0.):
    state = engine.core.warmup(card, random.Random(311), 25)
    # Pair all execution tests at neutral daily form, without changing production warm-up.
    state['g_roll'] = dict.fromkeys(state['g_roll'], 0)
    state.update(hgr_position=engine._stance(end, depth), hgr_contact=dict(x=x, y=engine._sign(end) * depth),
                 hgr_rally_load=0., hgr_match_load=0.)
    state['hgr_position']['x'] = x
    return state


def ball_for(end=0, **changes):
    ball = dict(origin='rally', spin='top', pace=125., quality=125., landed='fh', target='fh',
                length='long', return_state='neutral_return', backspin_strength=0., spin_strength=125.,
                absolute_target=dict(x=.55, y=engine._sign(end) * geo.LENGTH_DEPTH['long']), arc='normal')
    ball.update(changes)
    return ball


def quality(card, action, wing='fh', *, state=None, ball=None, seed=117010):
    state = state or state_for(card)
    result = engine._quality(card, state, ball or ball_for(), 'good', action,
                             random.Random(seed), 4, False, wing)
    return result, state


def probability(options, name):
    return next(item['probability'] for item in options if item['plan'] == name)


def all_shots(match):
    return [s for game in match['games'] for point in game['points'] for s in point['shots']]


class SpecialistPlan117Tests(unittest.TestCase):
    def test_chopper_short_pips_long_pips_have_disjoint_plan_menus(self):
        cards = [make_card(style='modern_chopper'),
                 make_card(rubbers=dict(fh='short_pips', bh='raw_pips')),
                 make_card(rubbers=dict(fh='long_pips', bh='long_pips'))]
        menus = [{row['plan'] for row in plans.plan_distribution(c, state_for(c), ball_for())} for c in cards]
        self.assertEqual([len(menu) for menu in menus], [5, 4, 4])
        self.assertTrue(all(not a.intersection(b) for i, a in enumerate(menus) for b in menus[i + 1:]))

    def test_equipment_does_not_silently_change_the_other_face_or_grant_a_role(self):
        card = make_card(rubbers=dict(fh='inverted', bh='short_pips'))
        self.assertEqual(plans.specialist_kind(card, ball_for(landed='fh')), 'attacker')
        self.assertEqual(plans.specialist_kind(card, ball_for(landed='bh')), 'short_pips')
        invalid = dict(card, tactical_family='long_pips')
        with self.assertRaises(ValueError):
            plans.plan_distribution(invalid, state_for(card), ball_for())
        with self.assertRaises(ValueError):
            plans.plan_distribution(dict(card, tactical_plan='chop_heavy'), state_for(card), ball_for())

    def test_weak_ball_favors_chopper_counter_and_changes_real_preparation(self):
        card = make_card(style='modern_chopper')
        strong = plans.plan_distribution(card, state_for(card), ball_for(quality=143.))
        weak = plans.plan_distribution(card, state_for(card), ball_for(quality=105.))
        self.assertGreater(probability(weak, 'chop_counter'), probability(strong, 'chop_counter') * 8)
        near, deep = state_for(card), state_for(card)
        near['v117_plan'] = dict(plan='chop_counter')
        deep['v117_plan'] = dict(plan='chop_heavy')
        near_contact = engine.reach(card, near, ball_for(), random.Random(1), 4, 0)[3]['contact']
        deep_contact = engine.reach(card, deep, ball_for(), random.Random(1), 4, 0)[3]['contact']
        self.assertEqual(abs(near_contact['y']), 1.10)
        self.assertEqual(abs(deep_contact['y']), 1.72)

    def test_tactical_choices_use_observation_and_ignore_opponent_hidden_ratings(self):
        own, other = make_card(), make_card('other', style='modern_chopper')
        state, other_state = state_for(own), state_for(other, 1, depth=1.7, x=.25)
        for _ in range(4):
            observed.observe_shot(state, stroke_side='fh', quality=95., action_family='counter')
            observed.observe_shot(state, stroke_side='bh', quality=140., action_family='counter')
        first = engine.target_distribution(own, state, ball_for(), other, other_state,
                                           'fh_fast_loop', 'observed_weak_side', 0)
        changed = copy.deepcopy(other)
        changed['children'] = {g: dict.fromkeys(sub, 30 if g == 'fh' else 150) for g, sub in changed['children'].items()}
        changed = Card.recompute(changed)
        other_state['g_roll'] = dict.fromkeys(other_state['g_roll'], -40)
        other_state['read_bonus'] = 80
        second = engine.target_distribution(own, state, ball_for(), changed, other_state,
                                            'fh_fast_loop', 'observed_weak_side', 0)
        self.assertEqual(first, second)

    def test_known_outgoing_quality_changes_chopper_target_distance_prediction(self):
        own, other = make_card(), make_card('other', style='modern_chopper')
        state, other_state = state_for(own), state_for(other, 1, depth=1.7)
        def projected(q):
            return engine.target_distribution(own, state, ball_for(), other, other_state,
                'fh_fast_loop', 'wide_movement', 0, outgoing_spin='top', outgoing_quality=q)
        weak, strong = projected(105.), projected(145.)
        self.assertTrue(all(row['geometry']['receiver_contact']['y'] == 1.10 for row in weak))
        self.assertTrue(all(row['geometry']['receiver_contact']['y'] == 1.68 for row in strong))
        self.assertTrue(any(a['geometry']['distance_m'] != b['geometry']['distance_m'] for a, b in zip(weak, strong)))

    def test_plan_changes_legal_preferences_and_ball_properties_without_g_or_quality(self):
        card = make_card(style='modern_chopper')
        state, ball = state_for(card), ball_for()
        before = copy.deepcopy((card, state))
        heavy = engine.action_distribution(card, state, ball, 'good', 'chop_heavy')
        counter = engine.action_distribution(card, state, ball, 'good', 'chop_counter')
        chop_share = lambda options: sum(row['probability'] for row in options if rubber.action_spec(row['action'])['family'] == 'chop')
        self.assertGreater(chop_share(heavy), chop_share(counter) + .35)
        self.assertEqual((card, state), before)
        contact = rubber.resolve_contact('inverted', 'fh_chop', ball, base_spin='back', base_pace=115., base_strength=130.)
        a = plans.contact_properties(contact, 'chop_heavy', 'chop')
        b = plans.contact_properties(contact, 'chop_float', 'chop')
        self.assertEqual((a['spin'], b['spin']), ('back', 'dead'))
        self.assertGreater(a['spin_strength'], b['spin_strength'] + 100)
        self.assertEqual(contact['spin_strength'], 130.)
        self.assertNotIn('quality', a)


class Contact117Tests(unittest.TestCase):
    def test_own_daily_forehand_form_applies_to_forehand_chop_without_backhand_leakage(self):
        card = make_card(style='modern_chopper')
        neutral = state_for(card)
        own, other = copy.deepcopy(neutral), copy.deepcopy(neutral)
        own['g_roll']['fh'] = 6
        other['g_roll']['bh'] = 6
        q0 = quality(card, 'fh_chop', state=neutral)[0][0]
        q_own = quality(card, 'fh_chop', state=own)[0][0]
        q_other = quality(card, 'fh_chop', state=other)[0][0]
        self.assertAlmostEqual(q_own - q0, 3.12, places=2)
        self.assertEqual(q_other, q0)
        bh0 = quality(card, 'bh_chop', 'bh', state=state_for(card))[0][0]
        bh_state = state_for(card)
        bh_state['g_roll']['bh'] = 6
        self.assertAlmostEqual(quality(card, 'bh_chop', 'bh', state=bh_state)[0][0] - bh0, 3.12, places=2)

    def test_short_pips_under_attack_uses_power_as_its_primary_actual_driver(self):
        base = make_card(rubbers=dict(fh='short_pips', bh='raw_pips'))
        power, spin = copy.deepcopy(base), copy.deepcopy(base)
        power['children']['fh']['power'] += 20
        spin['children']['fh']['spin'] += 20
        power, spin = Card.recompute(power), Card.recompute(spin)
        q0 = quality(base, 'fh_sp_under_attack')[0][0]
        qp = quality(power, 'fh_sp_under_attack')[0][0]
        qs = quality(spin, 'fh_sp_under_attack')[0][0]
        self.assertAlmostEqual(qp - q0, 11., places=2)
        self.assertAlmostEqual(qs - q0, 2., places=2)
        self.assertEqual(rubber.action_spec('fh_sp_under_attack')['technique_path'], 'fh.power')

    def test_ordinary_plus_one_skill_has_measurable_quality_and_reliability_effect(self):
        base = make_card()
        improved = copy.deepcopy(base)
        improved['children']['fh']['power'] += 1
        improved = Card.recompute(improved)
        q0, s0 = quality(base, 'fh_fast_loop')
        q1, s1 = quality(improved, 'fh_fast_loop')
        self.assertGreater(q1[0], q0[0] + .3)
        self.assertLess(engine.technical_error_adjustment(s1['v117_contact_skill']),
                        engine.technical_error_adjustment(s0['v117_contact_skill']))
        self.assertLess(q1[0] - q0[0], 1.)

    def test_spin_strength_and_arc_change_actual_reach_with_paired_noise(self):
        card = make_card()
        def run(strength, arc):
            return [engine.reach(card, state_for(card), ball_for(spin_strength=strength, arc=arc),
                                 random.Random(117100 + i), 5, 0) for i in range(96)]
        weak, strong, high, flat = run(80, 'normal'), run(150, 'normal'), run(125, 'high'), run(125, 'flat')
        self.assertGreater(statistics.mean(r[1] for r in weak), statistics.mean(r[1] for r in strong) + 2)
        self.assertGreater(statistics.mean(r[1] for r in high), statistics.mean(r[1] for r in flat) + 3)
        self.assertGreater(sum(r[0] == 'good' for r in weak), sum(r[0] == 'good' for r in strong))
        self.assertTrue(all(r[3]['input_arc'] == 'high' for r in high))

    def test_all_contact_recipes_use_valid_paths_and_chop_diversifies_learning(self):
        paths = set(Card.PATHS)
        for action in set(rubber.ACTION_SPECS) | set(engine.legacy.TECH):
            spec = rubber.action_spec(action)
            wing = spec['wing'] or 'fh'
            components = engine.technique_components(action, wing)
            self.assertLess(abs(sum(components.values()) - 1), 1e-6, action)
            self.assertTrue(set(components) <= paths, action)
        self.assertEqual(engine.technique_components('bh_lp_chop', 'bh'),
                         {'bh.defense': .42, 'bh.spin': .27, 'bh.placement': .23, 'bh.continuity': .08})

    def test_lower_effective_skills_reduce_quality_without_erasing_learned_values(self):
        card = make_card(value=135)
        card['learned_children'] = copy.deepcopy(card['children'])
        limited = copy.deepcopy(card)
        for key in limited['children']['fh']:
            limited['children']['fh'][key] -= 12
        limited['P6']['burst'] -= 15
        limited = Card.recompute(limited)
        q0, q1 = quality(card, 'fh_fast_loop')[0], quality(limited, 'fh_fast_loop')[0]
        self.assertLess(q1[0], q0[0] - 10)
        self.assertLess(q1[1], q0[1])
        self.assertEqual(limited['learned_children'], card['learned_children'])


class Match117Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = [make_card('v117_short', rubbers=dict(fh='short_pips', bh='raw_pips')),
                     make_card('v117_chopper', hand='left', style='modern_chopper',
                               rubbers=dict(fh='inverted', bh='long_pips'))]
        cls.before = copy.deepcopy(cls.cards)
        cls.result = engine.play_match(cls.cards, 117311, keep_points=True)
        cls.shots = all_shots(cls.result)

    def test_same_seed_replays_and_source_cards_and_runner_hooks_remain_unchanged(self):
        hooks = tuple(getattr(engine.core, k) for k in ('point', 'between_games', 'attempt_in_game_adaptation'))
        again = engine.play_match(self.cards, 117311, keep_points=True)
        self.assertEqual(canonical_json(self.result), canonical_json(again))
        self.assertEqual(self.cards, self.before)
        self.assertEqual(hooks, tuple(getattr(engine.core, k) for k in ('point', 'between_games', 'attempt_in_game_adaptation')))

    def test_actual_logs_keep_canonical_paths_and_distinct_specialist_plans(self):
        contacts = [shot for shot in self.shots if shot.get('technique_path')]
        self.assertTrue(any('_sp_' in s['action'] for s in contacts))
        self.assertTrue(any('_lp_' in s['action'] for s in contacts))
        self.assertTrue(any(s['specialist_plan'].startswith('pips_') for s in contacts if s['player'] == 0))
        self.assertTrue(any(s['specialist_plan'].startswith('chop_') for s in contacts if s['player'] == 1))
        for shot in contacts:
            self.assertEqual(shot['technique_path'], rubber.action_spec(shot['action'])['technique_path'])
            self.assertEqual(shot['action_family'], rubber.action_spec(shot['action'])['family'])
            self.assertLess(abs(sum(shot['technique_components'].values()) - 1), 1e-6)
            self.assertIn(shot['technique_path'], Card.PATHS)

    def test_outgoing_ball_arc_and_spin_strength_are_consumed_by_next_real_contact(self):
        links = []
        for game in self.result['games']:
            for point in game['points']:
                for previous, current in zip(point['shots'][1:], point['shots'][2:]):
                    if 'input_arc' in current:
                        self.assertEqual(current['input_arc'], previous['arc'])
                        self.assertEqual(current['input_spin_strength'], previous['spin_strength'])
                        self.assertEqual(current['movement']['input_arc'], previous['arc'])
                        links.append((previous, current))
        self.assertGreater(len(links), 25)
        self.assertTrue(any(a['arc'] != 'normal' for a, _ in links))

    def test_workload_counts_real_contacts_distance_and_single_contact_exposure(self):
        for player in (0, 1):
            contacts = [s for s in self.shots if s['player'] == player and s.get('technique_path')]
            own = [s for s in self.shots if s['player'] == player]
            workload = self.result['workload']['per_player'][player]
            self.assertEqual(workload['contacts'], len(contacts))
            distance = sum(s.get('movement', {}).get('distance_m', 0) + s.get('recovery_distance_m', 0) for s in own)
            self.assertAlmostEqual(workload['movement_m'], distance, places=4)
            self.assertAlmostEqual(workload['effort'], len(contacts) * .08 + distance * .18 + workload['active_attacks'] * .03, places=4)
            exposure = self.result['exposure_by_player'][player]
            self.assertEqual(sum(exposure['primary_path_counts'].values()), len(contacts))
            self.assertEqual(exposure['contacts'], len(contacts))

    def test_summary_removes_only_detail_and_preserves_outcome_and_workload(self):
        summary = engine.play_match(self.cards, 117311, keep_points=False)
        for key in ('winner', 'games_won', 'mean_strokes', 'workload', 'exposure_by_player'):
            self.assertEqual(summary[key], self.result[key])
        self.assertTrue(all('points' not in game for game in summary['games']))
        self.assertNotIn('tactical_choice_audit', summary)


if __name__ == '__main__':
    unittest.main()
