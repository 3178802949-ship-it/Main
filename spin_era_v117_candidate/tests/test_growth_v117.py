import copy
import json
import unittest

import Card
from Training import v117 as training
from common import SCHEMA
import career_v117 as career
import career_v116 as old


class Growth117Tests(unittest.TestCase):
    def card(self):
        return Card.make_ma18()

    def state(self, seed=11617001):
        return training.initialize(self.card(), seed=seed)

    def plan(self, phase=0):
        return dict(month=0, phase=phase, technical=[dict(group='read'), dict(group='bh')], body='stamina')

    def test_preparation_preserves_current_ability_but_repairs_young_ceiling(self):
        source = Card.get_preset('ma_long', 2004)
        before = copy.deepcopy(source)
        prepared = career.prepare_card(source, 11617001)
        self.assertEqual(source, before)
        self.assertEqual(source['children'], prepared['children'])
        self.assertEqual(source['P6'], prepared['P6'])
        self.assertEqual(source['CA'], prepared['CA'])
        self.assertLessEqual(abs(prepared['career117_profile']['reachable_envelope'] - source['PA']), 2)
        self.assertLessEqual(prepared['pa_range'][1] - prepared['pa_range'][0], 6)

    def test_physical_decline_limits_execution_without_deleting_learning(self):
        state = self.state()
        before = copy.deepcopy(state['children'])
        for group in state['children']:
            for key in state['children'][group]:
                state['children'][group][key] = 148
        learned = copy.deepcopy(state['children'])
        for key in state['P6']:
            state['P6'][key] = 90
        performance = career.performance_card(state)
        self.assertEqual(state['children'], learned)
        self.assertTrue(performance['body_limitations'])
        self.assertLess(performance['children']['fh']['power'], learned['fh']['power'])
        self.assertEqual(performance['CA'], compute(performance))

    def test_fatigue_and_age_apply_to_direct_growth_and_permits(self):
        base = self.state()
        young, old_tired = copy.deepcopy(base), copy.deepcopy(base)
        direct_young = direct_old = permits_young = permits_old = 0
        for seed in range(40):
            a, b = copy.deepcopy(young), copy.deepcopy(old_tired)
            a['seed'] = b['seed'] = seed
            aa = training._train(a, 'bh.defense', 5, 18, old.environment('national'), 0, 0, 1)
            bb = training._train(b, 'bh.defense', 5, 50, old.environment('national'), 0, 0, career.fatigue_factor(100))
            direct_young += aa['direct_applied']; direct_old += bb['direct_applied']
            a['children']['bh']['defense'] = b['children']['bh']['defense'] = 132
            aa = training._train(a, 'bh.defense', 5, 18, old.environment('national'), 0, 1, 1)
            bb = training._train(b, 'bh.defense', 5, 50, old.environment('national'), 0, 1, career.fatigue_factor(100))
            permits_young += aa['permit_awarded']; permits_old += bb['permit_awarded']
        self.assertGreater(direct_young, direct_old * 3)
        self.assertGreater(permits_young, permits_old * 3)

    def test_two_phases_and_portable_continuation_are_exact(self):
        a = self.state()
        training.settle_phase(a, self.plan(), old.environment('national'), 'a', record=False)
        b = training.load_state(training.dump_state(a))
        ra = training.settle_phase(a, self.plan(1), old.environment('national'), 'b', record=False)
        rb = training.settle_phase(b, self.plan(1), old.environment('national'), 'b', record=False)
        self.assertEqual(ra, rb)
        self.assertEqual(training.dump_state(a), training.dump_state(b))
        self.assertEqual(a['month'], 1)

    def test_invalid_and_duplicate_plan_do_not_mutate(self):
        state = self.state()
        before = training.dump_state(state)
        with self.assertRaises(ValueError):
            training.settle_phase(state, self.plan(1), old.environment('national'), 'bad')
        self.assertEqual(training.dump_state(state), before)
        training.settle_phase(state, self.plan(), old.environment('national'), 'dup')
        before = training.dump_state(state)
        with self.assertRaises(ValueError):
            training.settle_phase(state, self.plan(1), old.environment('national'), 'dup')
        self.assertEqual(training.dump_state(state), before)

    def test_time_fraction_scales_every_growth_channel(self):
        state = self.state()
        plan = self.plan(); plan.update(training_fraction=0, recovery_fraction=0)
        receipt = training.settle_phase(state, plan, old.environment('national'), 'zero')
        self.assertTrue(all(x['direct_applied'] == x['permit_awarded'] == x['xp_awarded'] == 0 for x in receipt['focused'] + receipt['general']))
        self.assertTrue(all(x['xp_awarded'] == 0 for x in receipt['body']))
        self.assertEqual(receipt['fatigue']['cost'], 0)
        self.assertEqual(receipt['fatigue']['recovery'], 0)

    def test_champion_window_is_bounded_and_does_not_give_points(self):
        state = self.state()
        path = 'bh.defense'
        event = dict(id='gold', month=0, kind='champion', source='WORLD_EVENT', evidence_ref='event1',
            paths=[path], usage={path: 10}, challenge=1., review_quality=1.)
        values = copy.deepcopy(state['children']); body = dict(state['P6'])
        result = career.register_champion(state, event)
        self.assertTrue(result['granted'])
        self.assertEqual(state['children'], values); self.assertEqual(state['P6'], body)
        self.assertEqual(state['windows'][0]['multiplier'], 1.25)
        with self.assertRaises(ValueError):
            career.register_champion(state, event)
        event.update(id='gold2', evidence_ref='event2'); career.register_champion(state, event)
        event.update(id='gold3', evidence_ref='event3'); self.assertFalse(career.register_champion(state, event)['granted'])

    def test_rehab_and_injury_cap_reduction(self):
        state = self.state()
        cap = state['P_max']['speed']
        career.injury(state, 'injury', 0, severity=2)
        self.assertEqual(state['P_max']['speed'], cap - 2)
        training.settle_phase(state, self.plan(), old.environment('national'), 'rehab0')
        with self.assertRaises(ValueError):
            training.settle_phase(state, self.plan(1), old.environment('national'), 'rehab1')

    def test_body_xp_bank_cannot_cancel_aging_ceiling(self):
        state = self.state()
        state['P6'] = dict(state['P_max'])
        state['career_v117']['physiological_P'] = dict(state['P_max'])
        for key in state['P6']:
            state['P_xp'][key] = 1_000_000
        learned = copy.deepcopy(state['children'])
        career.age_and_body(state, 35, old.environment('national'), 204)
        before = dict(state['P6'])
        for key in state['P6']:
            result = training._body(state, key, 1, 35, old.environment('national'), 1.)
            self.assertEqual(state['P6'][key], before[key])
            self.assertLess(state['P6'][key], state['P_max'][key])
            self.assertLessEqual(state['P_xp'][key], result['xp_bank_cap'])
            self.assertLessEqual(state['P6'][key], result['physical_ceiling'] + 0.0001)
        self.assertTrue(all(0 <= learned[g][k] - value < .02
                            for g, sub in state['children'].items() for k, value in sub.items()))

    def test_zero_time_does_not_convert_old_xp_bank(self):
        state = self.state()
        for path in state['xp']:
            state['xp'][path] = 10000.
            state['permits'][path] = 100
        for key in state['P_xp']:
            state['P_xp'][key] = 10000.
        before = copy.deepcopy(state['children'])
        plan = self.plan(); plan.update(training_fraction=0, recovery_fraction=0)
        receipt = training.settle_phase(state, plan, old.environment('national'), 'no-time')
        self.assertEqual(state['children'], before)
        self.assertTrue(all(x['new'] == x['old'] for x in receipt['body']))

    def test_compact_receipts_and_strategy_branch_guard(self):
        prepared = career.prepare_card(self.card(), 12)
        with self.assertRaisesRegex(ValueError, 'STRATEGY_MISMATCH'):
            career.prepare_card(prepared, 12, 'xp_only')
        state = self.state()
        for month in range(14):
            for phase in range(2):
                plan = self.plan(phase); plan['month'] = month
                training._settle(state, plan, old.environment('national'), f'{month}:{phase}', (), True)
        self.assertEqual(len(state['training_release']['phase_log']), 24)
        self.assertEqual(state['training_release']['receipts_archived'], 4)
        self.assertNotIn('CA_effective', career.performance_card(state))
        audit = state['audit']
        self.assertAlmostEqual(audit['XP_FOCUS'] + audit['XP_GENERAL'] - audit['XP_SPENT'], sum(state['xp'].values()))
        self.assertEqual(audit['PERMITS_AWARDED'] - audit['PERMITS_SPENT'], sum(state['permits'].values()))
        self.assertAlmostEqual(audit['P_XP_AWARDED'] - audit['P_XP_SPENT'] - audit['P_XP_EXPIRED_AT_BANK_CAP'], sum(state['P_xp'].values()))

    def test_general_training_retains_excellence(self):
        state = self.state()
        receipt = training._train(state, 'bh.defense', 1, 18, old.environment('national'), 0, 0, 1., True)
        self.assertTrue(receipt['exceptional'])
        self.assertGreater(receipt['xp_awarded'], 0)
        self.assertGreater(receipt['direct_applied'], 0)


def compute(value):
    from card_training_v112 import compute_card
    return compute_card(value, SCHEMA)['CA_calculated']

