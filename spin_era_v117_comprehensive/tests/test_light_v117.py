"""Scoring, sensitivity, evidence and storage contracts for actual light matches."""
import copy
import json
import random
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Card
from common import canonical_json
from Game import light_v117 as light


def cards():
    a = Card.make_ma18()
    a.update(hand='right', rubbers=dict(fh='inverted', bh='inverted'))
    b = copy.deepcopy(a)
    b.update(player_id='light-synthetic-peer', hand='left')
    return [a, b]


class LightMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = cards()
        cls.match = light.play_match(cls.inputs, 11791001)

    def test_exact_scoring_and_aggregate_contact_accounting(self):
        match = self.match
        self.assertEqual(max(match['games_won']), 4)
        for game in match['games']:
            self.assertGreaterEqual(max(game['score']), 11)
            self.assertGreaterEqual(abs(game['score'][0] - game['score'][1]), 2)
            self.assertEqual(sum(game['score']), game['points_count'])
            self.assertNotIn('points', game)
        self.assertEqual(sum(g['points_count'] for g in match['games']), match['points'])
        self.assertEqual(sum(match['rally_length_distribution'].values()), match['points'])
        self.assertEqual(sum(int(n) * count for n, count in match['rally_length_distribution'].items()), match['total_strokes'])
        self.assertEqual(sum(match['actions'].values()), match['total_strokes'])
        self.assertEqual(sum(match['action_family_distribution'].values()), match['total_strokes'])
        self.assertEqual(sum(p.get('serve', 0) for p in match['per_player_actions']), match['points'])

    def test_reproducible_and_source_cards_immutable(self):
        before = canonical_json(self.inputs)
        self.assertEqual(self.match, light.play_match(self.inputs, 11791001))
        self.assertEqual(before, canonical_json(self.inputs))

    def test_no_shot_trace_and_compact_portable_evidence(self):
        result = json.loads(json.dumps(self.match, allow_nan=False))
        self.assertEqual(result['narrative_scope'], 'AGGREGATE_ONLY')
        self.assertLess(len(json.dumps(result).encode()), 25000)
        self.assertTrue(result['metadata_limits']['no_shot_chronology'])
        self.assertNotIn('rallies', result)
        self.assertTrue(result['exposure_method'].startswith('SAMPLED_AGGREGATE'))

    def test_exposures_are_actual_contact_allocations_on_valid_paths(self):
        result = self.match
        contact_count = 0
        for i, ledger in enumerate(result['exposure_by_player']):
            self.assertTrue(set(ledger['usage']) <= light.PATHS)
            self.assertTrue(all(type(v) is int and v > 0 for v in ledger['usage'].values()))
            self.assertTrue(all(0 <= v <= ledger['usage'][path] for path, v in ledger['pressure'].items()))
            self.assertEqual(sum(ledger['usage'].values()), result['workload']['per_player'][i]['contacts'])
            self.assertTrue(any(v >= 8 for v in ledger['usage'].values()))
            contact_count += sum(ledger['usage'].values())
        self.assertEqual(contact_count, result['total_strokes'])
        self.assertEqual(sum(p['contacts'] for p in result['workload']['per_player']), result['total_strokes'])
        for item in result['workload']['per_player']:
            self.assertAlmostEqual(item['effort'], item['contacts'] * .08 + item['movement_m'] * .18
                                   + item['active_attacks'] * .03, places=4)
        self.assertTrue(result['exposure_scope'].startswith('ALL_SAMPLED_CONTACTS_INCLUDING_SERVE'))
        self.assertEqual(sum(sum(ledger['usage'].get(path, 0) for path in light.SERVE_RECIPE)
                             for ledger in result['exposure_by_player']), result['points'])
        self.assertAlmostEqual(sum(light.SERVE_RECIPE.values()), 1.)

    def test_all_formats_and_invalid_detailed_request(self):
        for games, required in ((3, 2), (5, 3), (7, 4)):
            match = light.play_match(self.inputs, 11791002, max_games=games)
            self.assertEqual(max(match['games_won']), required)
        with self.assertRaises(ValueError):
            light.play_match(self.inputs, 1, keep_points=True)

    def test_ca_pa_and_unrelated_story_labels_cannot_select_winner(self):
        changed = copy.deepcopy(self.inputs)
        changed[0].update(CA=20, PA=200, name_zh='必胜传奇')
        changed[1].update(CA=200, PA=100, name_zh='普通人')
        self.assertEqual(self.match, light.play_match(changed, 11791001))

    def test_own_wing_technical_and_fatigue_sensitivity(self):
        inputs = cards()
        rng = light.core.rng_of('SPIN-ERA-1.1.2', 'MATCH', 11791003)
        states = [light.core.warmup(inputs[i], rng, 25) for i in (0, 1)]
        base = light.point_probability(inputs, states, 0, 0, 'fh_fast_loop', 'fh', 'bh_press_block', 'bh')
        improved = copy.deepcopy(inputs)
        improved[0]['children']['fh']['power'] += 20
        stronger = light.point_probability(improved, states, 0, 0, 'fh_fast_loop', 'fh', 'bh_press_block', 'bh')
        self.assertGreater(stronger['p_attacker'], base['p_attacker'])
        self.assertLess(stronger['attack_error'], base['attack_error'])
        fatigued = copy.deepcopy(states)
        fatigued[0]['match_stamina'] = 30
        tired = light.point_probability(inputs, fatigued, 0, 0, 'fh_fast_loop', 'fh', 'bh_press_block', 'bh')
        self.assertLess(tired['p_attacker'], base['p_attacker'])

    def test_hand_changes_only_lane_geometry_and_unknown_is_not_assumed(self):
        inputs = cards()
        rng = light.core.rng_of('SPIN-ERA-1.1.2', 'MATCH', 11791004)
        state = light.core.warmup(inputs[0], rng, 25)
        left_lane = light._defending_lane(inputs[0], inputs[1], 'fh', state, random.Random(1))
        same_hand = copy.deepcopy(inputs[1]); same_hand['hand'] = 'right'
        right_lane = light._defending_lane(inputs[0], same_hand, 'fh', state, random.Random(1))
        self.assertNotEqual(left_lane[0], right_lane[0])
        unknown = copy.deepcopy(inputs[1]); unknown.pop('hand')
        self.assertFalse(light._defending_lane(inputs[0], unknown, 'fh', state, random.Random(1))[2])

    def test_chop_exposure_uses_spin_placement_and_continuity_not_only_defense(self):
        a, b = cards()
        b.update(style='modern_chopper', rubbers=dict(fh='inverted', bh='long_pips'))
        match = light.play_match([a, b], 11791005)
        usage = match['exposure_by_player'][1]['usage']
        self.assertTrue(any('chop' in a for a in match['per_player_actions'][1]))
        for key in ('defense', 'spin', 'placement', 'continuity'):
            self.assertGreater(usage.get('fh.' + key, 0) + usage.get('bh.' + key, 0), 0)

    def test_power_driven_pips_opening_has_matching_growth_recipe(self):
        recipe = light.contact_recipe('fh_sp_under_attack', 'fh')
        self.assertGreater(recipe['fh.power'], recipe['fh.spin'])
        self.assertAlmostEqual(sum(recipe.values()), 1.)

    def test_live_defensive_policy_changes_actual_contact_mix(self):
        card = cards()[0]
        rng = light.core.rng_of('SPIN-ERA-1.1.2', 'MATCH', 11791006)
        state = light.core.warmup(card, rng, 25)
        aggressive = copy.deepcopy(state); aggressive['policy'] = 'receive_initiative'
        defensive = copy.deepcopy(state); defensive['policy'] = 'defensive_pivot'
        first = [light._choose_contact(card, aggressive, 'fh', 'top', 125, random.Random(seed), defending=True)
                 for seed in range(200)]
        second = [light._choose_contact(card, defensive, 'fh', 'top', 125, random.Random(seed), defending=True)
                  for seed in range(200)]
        self.assertGreater(second.count('fh_press_block'), first.count('fh_press_block'))

    def test_pips_contact_properties_change_pressure_without_quality_multiplier(self):
        inputs = cards()
        inputs[0]['rubbers']['fh'] = 'short_pips'
        rng = light.core.rng_of('SPIN-ERA-1.1.2', 'MATCH', 11791007)
        states = [light.core.warmup(inputs[i], rng, 25) for i in (0, 1)]
        short = light.point_probability(inputs, states, 0, 0, 'fh_sp_punch', 'fh', 'bh_press_block', 'bh')
        raw = copy.deepcopy(inputs); raw[0]['rubbers']['fh'] = 'raw_pips'
        raw_contact = light.point_probability(raw, states, 0, 0, 'fh_sp_punch', 'fh', 'bh_press_block', 'bh')
        self.assertEqual(short['attack_skill'], raw_contact['attack_skill'])
        self.assertNotEqual(short['pace_demand'], raw_contact['pace_demand'])
        self.assertNotEqual(short['spin_demand'], raw_contact['spin_demand'])

    def test_light_shares_pure_contact_recipes_without_calling_full_runner(self):
        from Game import engine_v117
        for action in ('fh_fast_loop', 'bh_press_block', 'fh_sp_under_attack', 'bh_lp_chop', 'push_long'):
            wing = 'bh' if action.startswith('bh') else 'fh'
            self.assertEqual(light.contact_recipe(action, wing), engine_v117.technique_components(action, wing))
        with patch.object(engine_v117, 'play_match', side_effect=AssertionError('full runner called')):
            match = light.play_match(self.inputs, 11791008, max_games=3)
        self.assertEqual(match['engine'], light.TAG)

    def test_shared_menu_uses_full_probabilities_and_records_actual_wing(self):
        original = light.shared_action_distribution
        audited = []
        def audit(card, state, ball, position, plan):
            before = copy.deepcopy(state)
            result = original(card, state, ball, position, plan)
            self.assertEqual(before, state)
            audited.append((copy.deepcopy(ball), position, result))
            return result
        class RecordingRandom(random.Random):
            def choices(self, population, weights=None, **kwargs):
                self.last_weights = weights
                return super().choices(population, weights=weights, **kwargs)
        card = cards()[0]
        for seed in range(20):
            rng = RecordingRandom(seed)
            state = light.core.warmup(card, rng, 25)
            with patch.object(light, 'shared_action_distribution', side_effect=audit):
                action = light._choose_contact(card, state, 'fh', 'top', 125, rng)
            ball, position, options = audited[-1]
            self.assertEqual(rng.last_weights, [item['probability'] for item in options])
            self.assertEqual(ball['origin'], 'rally')
            self.assertIn(position, ('good', 'limited', 'bad'))
            selected = next(item for item in options if item['action'] == action)
            self.assertEqual(state['light_contact_wing'], selected['wing'])
            self.assertTrue(light.rubbers.legal_action(action, light.rubbers.rubber_for(card, selected['wing']), ball, position))

    def test_cross_wing_shared_choice_uses_actual_side_for_all_growth(self):
        choice = [dict(action='bh_counter_loop', probability=1., wing='bh', family='counter')]
        with patch.object(light, 'shared_action_distribution', return_value=choice):
            match = light.play_match(self.inputs, 11791017, max_games=3)
        for ledger in match['exposure_by_player']:
            self.assertFalse(any(path.startswith('fh.') for path in ledger['usage']))
            self.assertTrue(any(path.startswith('bh.') for path in ledger['usage']))

    def test_chopper_control_does_not_require_being_assigned_defender(self):
        card = cards()[0]
        card.update(style='modern_chopper', tactical_plan='chop_heavy')
        rng = light.core.rng_of('SPIN-ERA-1.1.2', 'MATCH', 11791009)
        state = light.core.warmup(card, rng, 25)
        actions = [light._choose_contact(card, state, 'fh', 'top', 125, random.Random(seed), defending=False)
                   for seed in range(200)]
        self.assertGreater(actions.count('fh_specialist_chop'), actions.count('fh_counter_loop'))

    def test_response_uses_actual_returned_spin_and_passive_control_can_yield_attack(self):
        inputs = cards()
        inputs[1].update(style='modern_chopper', tactical_plan='chop_heavy')
        contacts, groups = [], []
        original = light.contact_properties
        probability = light.point_probability
        def record(card, state, action, wing, incoming, *args):
            result = original(card, state, action, wing, incoming, *args)
            contacts.append((incoming, result['spin']))
            return result
        def finish(*args, **kwargs):
            groups.append(list(contacts)); contacts.clear()
            return probability(*args, **kwargs)
        with patch.object(light, 'contact_properties', side_effect=record), patch.object(light, 'point_probability', side_effect=finish):
            match = light.play_match(inputs, 11791010)
        self.assertEqual(len(groups), match['points'])
        self.assertEqual(sum(len(g) for g in groups), match['points'] * 2
                         + match['outcome_summary'].get('initiative_returned_by_passive_contact', 0))
        for group in groups:
            for first, response in zip(group, group[1:]):
                self.assertEqual(response[0], first[1])
        self.assertGreater(match['outcome_summary'].get('initiative_returned_by_passive_contact', 0), 0)

    def test_passive_pair_is_symmetric_and_has_no_burst_attack_bonus(self):
        inputs = cards(); inputs[1] = copy.deepcopy(inputs[0]); inputs[1]['player_id'] = 'passive-peer'
        rng = light.core.rng_of('SPIN-ERA-1.1.2', 'MATCH', 11791011)
        state = light.core.warmup(inputs[0], rng, 25)
        states = [copy.deepcopy(state), copy.deepcopy(state)]
        first = light.point_probability(inputs, states, 0, 0, 'fh_press_block', 'fh', 'fh_press_block', 'fh')
        second = light.point_probability(inputs, states, 1, 0, 'fh_press_block', 'fh', 'fh_press_block', 'fh')
        self.assertAlmostEqual(first['p_attacker'] + second['p_attacker'], 1.)
        self.assertEqual(first['phases'][0]['winner'], 0)
        self.assertEqual(first['phases'][1]['winner'], 0)
        states[0]['p_eff']['burst'] += 20
        stronger = light.point_probability(inputs, states, 0, 0, 'fh_press_block', 'fh', 'fh_press_block', 'fh')
        self.assertEqual(first['p_attacker'], stronger['p_attacker'])

    def test_explicit_chop_plan_changes_actual_spin_without_quality_bonus(self):
        card = cards()[0]; card.update(style='modern_chopper')
        rng = light.core.rng_of('SPIN-ERA-1.1.2', 'MATCH', 11791012)
        state = light.core.warmup(card, rng, 25)
        heavy = copy.deepcopy(state); heavy['light_plan'] = 'chop_heavy'
        floating = copy.deepcopy(state); floating['light_plan'] = 'chop_float'
        heavy_ball = light.contact_properties(card, heavy, 'fh_specialist_chop', 'fh', 'top')
        float_ball = light.contact_properties(card, floating, 'fh_specialist_chop', 'fh', 'top')
        self.assertEqual(heavy_ball['spin'], 'back')
        self.assertEqual(float_ball['spin'], 'dead')
        self.assertEqual(light.contact_skill(card, heavy, 'fh_specialist_chop', 'fh'),
                         light.contact_skill(card, floating, 'fh_specialist_chop', 'fh'))

    def test_absorbing_probabilities_match_terminal_mass_and_capped_recurrence(self):
        phases = (dict(loss=.18, arrival_miss=.03, winner=.07, continuation=.75),
                  dict(loss=.12, arrival_miss=.02, winner=.04, continuation=.84))
        p, counts = light._absorbed(*phases)
        events, _ = light._terminal_events(phases)
        self.assertAlmostEqual(sum(e['weight'] for e in events), 1.)
        self.assertAlmostEqual(sum(e['weight'] for e in events if e['winner'] == 0), p)
        pa = pb = .5
        for _ in range(41):
            pa, pb = phases[0]['winner'] + phases[0]['continuation'] * pb, phases[1]['loss'] + phases[1]['continuation'] * pa
        self.assertAlmostEqual((pa + pb) / 2, p)
        self.assertTrue(1 <= sum(counts) <= 41)

    def test_strong_return_tail_is_integrated_without_quality_bins(self):
        _, strong, first, second = light._quality_moments(131., 0., True)
        self.assertAlmostEqual(strong, 1 - light._cdf(9 / 7))
        self.assertTrue(140 * strong <= first <= 168 * strong)
        self.assertTrue(140 ** 2 * strong <= second <= 168 ** 2 * strong)
        self.assertGreater(light._quality_moments(131.01, 0., True)[1], strong)

    def test_missed_terminal_attempt_has_no_contact_and_keeps_losing_actor(self):
        phase = dict(loss=1., arrival_miss=1., winner=0., continuation=0.)
        matchup = dict(p_attacker=.5, phases=(phase, phase))
        for seed in range(20):
            result = light._draw_aggregate_point(random.Random(seed), matchup)
            self.assertEqual(result['contacts'], 1)  # service only; receiver never touches
            self.assertEqual(sum(result['contacted']), 0)
            self.assertEqual(sum(result['attempted']), 1)
            self.assertNotEqual(result['miss_actor'], result['winner'])

    def test_error_terminal_is_a_real_contact_and_has_no_recovery_action(self):
        phase = dict(loss=1., arrival_miss=0., winner=0., continuation=0.)
        result = light._draw_aggregate_point(random.Random(11791016), dict(p_attacker=.5, phases=(phase, phase)))
        self.assertEqual(result['contacts'], 2)
        self.assertEqual(sum(result['contacted']), 1)
        self.assertEqual(sum(result['attempted']), 1)
        self.assertIsNone(result['miss_actor'])
        self.assertNotEqual(result['error_actor'], result['winner'])

    def test_serve_only_match_grants_no_unreached_xp_and_counts_only_attempt_movement(self):
        original = light.point_probability
        def unreached(*args, **kwargs):
            result = original(*args, **kwargs)
            result['p_attacker'] = .5
            for phase in result['phases']:
                phase.update(loss=1., arrival_miss=1., winner=0., continuation=0.,
                             movement_m=10., unreached_movement_m=2.)
            return result
        with patch.object(light, 'point_probability', side_effect=unreached):
            match = light.play_match(self.inputs, 11791015, max_games=3)
        self.assertEqual(match['total_strokes'], match['points'])
        self.assertEqual(match['actions'], dict(serve=match['points']))
        self.assertEqual(sum(p['movement_m'] for p in match['workload']['per_player']), 2 * match['points'])
        for ledger in match['exposure_by_player']:
            self.assertTrue(all(path.startswith('serve.') for path in ledger['usage']))

    def test_aggregate_contact_count_follows_finite_survival_distribution(self):
        phases = (dict(loss=.18, arrival_miss=.03, winner=.07, continuation=.75),
                  dict(loss=.12, arrival_miss=.02, winner=.04, continuation=.84))
        p, counts = light._absorbed(*phases)
        rng = random.Random(11791013)
        samples = [light._draw_aggregate_point(rng, dict(p_attacker=p, phases=phases)) for _ in range(15000)]
        self.assertAlmostEqual(sum(sum(v['attempted']) for v in samples) / len(samples), sum(counts), delta=.08)
        self.assertTrue(all(sum(v['attempted']) <= 41 and v['contacts'] <= 42 for v in samples))

    def test_chop_reliability_does_not_grant_direct_winner_and_body_support_matters(self):
        inputs = cards(); inputs[1].update(style='modern_chopper')
        rng = light.core.rng_of('SPIN-ERA-1.1.2', 'MATCH', 11791014)
        states = [light.core.warmup(inputs[i], rng, 25) for i in (0, 1)]
        base = light.point_probability(inputs, states, 0, 0, 'fh_fast_loop', 'fh', 'fh_specialist_chop', 'fh')
        self.assertEqual(base['phases'][1]['winner'], 0)
        slower = copy.deepcopy(states)
        for key in ('speed', 'agility', 'flexibility'):
            slower[1]['p_eff'][key] -= 20
        aged = light.point_probability(inputs, slower, 0, 0, 'fh_fast_loop', 'fh', 'fh_specialist_chop', 'fh')
        self.assertGreater(aged['phases'][1]['arrival_miss'], base['phases'][1]['arrival_miss'])
        self.assertGreater(aged['p_attacker'], base['p_attacker'])


if __name__ == '__main__':
    unittest.main()
