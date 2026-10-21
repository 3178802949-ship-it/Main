"""Behavioral contracts for modular category training, not old calibration."""
import copy
import unittest

from common import SCHEMA
import Training
import career_v114 as fixtures
import career_v116 as career


def plan(month=0, phase=0, specialized=False):
    selections = [{'group': 'read'}, {'group': 'bh'}]
    if specialized:
        selections = [{'group': 'read', 'specialize': ['self_read', 'choice']},
                      {'group': 'bh', 'specialize': ['defense', 'placement']}]
    return dict(month=month, phase=phase, mode='train', technical=selections, body='stamina')


def rest(month, phase):
    return dict(month=month, phase=phase, mode='rest')


class TrainingTests(unittest.TestCase):
    def state(self, seed=116, value=None, start_age=18):
        card = fixtures.ordinary_card(SCHEMA)
        if value is not None:
            card['children'] = {g: dict.fromkeys(sub, value) for g, sub in card['children'].items()}
        paths = [f'{g}.{k}' for g, sub in card['children'].items() for k in sub]
        profile = dict(body_max=dict.fromkeys(career.P, 145), talent=dict.fromkeys(paths, 60.),
                       neuromotor=dict.fromkeys(paths, 1.), mental=15., focus=[])
        return Training.initialize(card, seed=seed, development_profile=profile, start_age=start_age)

    def test_category_training_covers_others_without_free_extra_dice(self):
        state = self.state()
        receipt = Training.settle_phase(state, plan(), career.environment(), 'phase0')
        self.assertEqual(receipt['budget'], dict(focused_technical=4, general_technical=7,
                                                focused_body=2, general_body=5))
        for group in ('read', 'bh'):
            entries = [e for e in receipt['focused'] if e['group'] == group]
            self.assertEqual(len(entries), 2)
            self.assertEqual(len({e['path'] for e in entries}), 2)
        self.assertEqual({e['path'].split('.')[0] for e in receipt['general']},
                         set(Training.GROUPS) - {'read', 'bh'})
        self.assertEqual({e['path'] for e in receipt['body'] if e['type'] == 'general_body'},
                         set(career.P) - {'stamina'})
        self.assertEqual(state['month'], 0)
        self.assertEqual(state['training_release']['phase'], 1)
        self.assertEqual(len(state['settled_drills']), 4)

    def test_specialization_targets_two_children_costing_more_fatigue_not_more_rolls(self):
        a, b = self.state(), self.state()
        normal = Training.settle_phase(a, plan(), career.environment(), 'normal')
        spec = Training.settle_phase(b, plan(specialized=True), career.environment(), 'special')
        self.assertEqual(spec['budget'], normal['budget'])
        self.assertEqual([e['path'] for e in spec['focused']],
                         ['read.self_read', 'read.choice', 'bh.defense', 'bh.placement'])
        self.assertEqual(spec['fatigue']['cost'] - normal['fatigue']['cost'], 6)
        self.assertAlmostEqual(b['fatigue'] - a['fatigue'], 6)

    def test_invalid_specialization_and_repeated_categories_do_not_mutate_state(self):
        cases = [
            [{'group': 'read', 'specialize': ['choice', 'choice']}, {'group': 'bh'}],
            [{'group': 'read', 'specialize': ['power', 'choice']}, {'group': 'bh'}],
            [{'group': 'read'}, {'group': 'read'}],
        ]
        for selection in cases:
            with self.subTest(selection=selection):
                state = self.state(); before = copy.deepcopy(state)
                p = plan(); p['technical'] = selection
                with self.assertRaises(ValueError):
                    Training.settle_phase(state, p, career.environment(), 'invalid')
                self.assertEqual(state, before)

    def test_nonportable_plan_metadata_cannot_poison_long_term_save(self):
        for invalid in (float('nan'), {1, 2}):
            state = self.state(); before = copy.deepcopy(state)
            p = plan(); p['note'] = invalid
            with self.assertRaises(ValueError):
                Training.settle_phase(state, p, career.environment(), 'invalid_metadata')
            self.assertEqual(state, before)

    def test_month_budget_clock_and_duplicate_ids(self):
        state = self.state()
        receipts = Training.settle_month(state, [plan(0, 0), plan(0, 1)], career.environment(), 'month0')
        self.assertEqual(len(receipts), 2)
        self.assertEqual(state['month'], 1)
        self.assertEqual(state['training_release']['phase'], 0)
        self.assertEqual(state['audit']['TRAINING_ROLLS'], 8)
        self.assertEqual(state['audit']['GENERAL_TECHNICAL_ROLLS'], 14)
        self.assertEqual(state['audit']['P_ROLLS'], 4)
        self.assertEqual(state['audit']['P_GENERAL_ROLLS'], 10)
        self.assertEqual(len(state['training_release']['monthly_aging']), 1)
        before = copy.deepcopy(state)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            Training.settle_phase(state, plan(1, 0), career.environment(), 'month0:phase0')
        self.assertEqual(state, before)

    def excellence_seed(self):
        # Select a deterministic positive fixture, not an in-game event reroll.
        for seed in range(1, 100):
            for group in set(Training.GROUPS) - {'read', 'bh'}:
                r = career.rng_for(seed, 'release-general', 0, 0, group)
                pool = list(SCHEMA['subskill_weights_pct'][group])
                r.choices(pool, weights=[SCHEMA['subskill_weights_pct'][group][k] for k in pool])
                if r.randint(1, 100) <= 3:
                    return seed
        self.fail('no positive deterministic general excellence fixture')

    def test_general_training_can_earn_audited_excellence_permits_without_focused_selection(self):
        state = self.state(seed=self.excellence_seed(), value=130)
        receipt = Training.settle_phase(state, plan(), career.environment(), 'general_excellence')
        exceptional = [e for e in receipt['general'] if e['exceptional']]
        self.assertTrue(exceptional)
        self.assertTrue(all(e['roll'] <= 3 and e['permit_awarded'] == 1 for e in exceptional))
        self.assertTrue(all(e['new'] == e['old'] for e in exceptional))  # no XP for a full level yet
        for e in exceptional:
            self.assertAlmostEqual(state['xp'][e['path']], e['xp_awarded'])
            self.assertEqual(state['permits'][e['path']], 1)

    def test_low_general_excellence_can_add_one_level_and_never_two_to_four(self):
        state = self.state(seed=self.excellence_seed(), value=110)
        receipt = Training.settle_phase(state, plan(), career.environment(), 'young_general')
        exceptional = [e for e in receipt['general'] if e['exceptional']]
        self.assertTrue(exceptional)
        self.assertTrue(all(e['new'] - e['old'] == 1 for e in exceptional))
        self.assertTrue(all(e['direct_applied'] == 1 and e['permit_awarded'] == 0 for e in exceptional))

    def test_general_excellence_never_bypasses_cap_or_cuts_an_existing_oversoftcap_value(self):
        state = self.state(seed=self.excellence_seed(), value=150)
        receipt = Training.settle_phase(state, plan(), career.environment(), 'capped')
        exceptional = [e for e in receipt['general'] if e['exceptional']]
        self.assertTrue(exceptional)
        self.assertTrue(all(e['new'] == 150 and e['permit_awarded'] == 0 for e in exceptional))

    def coach_seed(self):
        for seed in range(1, 100):
            for group in sorted(set(Training.GROUPS) - {'read', 'bh'}):
                r = career.rng_for(seed, 'release-general', 0, 0, group)
                pool = list(SCHEMA['subskill_weights_pct'][group])
                child = r.choices(pool, weights=[SCHEMA['subskill_weights_pct'][group][k] for k in pool])[0]
                ordinary_roll = r.randint(1, 100)
                coach_roll = career.rng_for(seed, 'release-coach-correction', 0, 0, f'{group}.{child}').randint(1, 100)
                if ordinary_roll > 3 and coach_roll <= 33:
                    return seed
        self.fail('no positive deterministic coaching fixture')

    def test_quality_coaching_still_consolidates_banked_xp_using_the_existing_permit_cost(self):
        state = self.state(seed=self.coach_seed(), value=130)
        state['xp'] = dict.fromkeys(state['xp'], 100.)
        receipt = Training.settle_phase(state, plan(), career.environment('frontier'), 'coached')
        coached = [e for e in receipt['general'] if e['coach_permit']]
        self.assertTrue(coached)
        for entry in coached:
            self.assertFalse(entry['exceptional'])
            self.assertLessEqual(entry['coach_roll'], entry['coach_threshold'])
            self.assertLessEqual(entry['coach_probability'], .33)
            self.assertEqual(entry['permit_awarded'], 1)
            self.assertEqual(entry['new'], entry['old'] + 1)
            self.assertAlmostEqual(entry['xp_balance'], entry['xp_before'] + entry['xp_awarded'] - career.legacy.xp_cost(entry['old']))
            self.assertEqual(entry['permit_balance'], 0)
        self.assertEqual(state['audit']['COACHED_CONSOLIDATION_PERMITS'], len(coached))
        self.assertEqual(state['audit']['GENERAL_COACH_CORRECTION_PERMITS'], len(coached))

    def test_club_retains_general_excellence_without_extra_coaching_permits(self):
        state = self.state(seed=self.excellence_seed(), value=130)
        state['xp'] = dict.fromkeys(state['xp'], 100.)
        receipt = Training.settle_phase(state, plan(), career.environment('club'), 'club')
        self.assertTrue(any(e['exceptional'] for e in receipt['general']))
        for entry in receipt['general']:
            self.assertEqual(entry['coach_probability'], 0)
            self.assertEqual(entry['coach_permit'], 0)
            self.assertEqual(entry['permit_awarded'], int(entry['exceptional']))
        self.assertEqual(state['audit']['COACHED_CONSOLIDATION_PERMITS'], 0)

    def test_coaching_requires_advanced_skill_room_and_half_a_level_of_practice(self):
        for case, value, bank in [('practice_shortage', 130, 0.), ('below_advanced', 127, 100.), ('at_cap', 150, 100.)]:
            with self.subTest(case=case):
                state = self.state(seed=self.coach_seed(), value=value)
                state['xp'] = dict.fromkeys(state['xp'], bank)
                receipt = Training.settle_phase(state, plan(), career.environment('frontier'), case)
                self.assertTrue(all(not e['coach_eligible'] and e['coach_roll'] is None and e['coach_permit'] == 0
                                    for e in receipt['general']))

    def test_excellence_and_coaching_never_award_two_permits_for_the_same_general_drill(self):
        state = self.state(seed=self.excellence_seed(), value=130)
        state['xp'] = dict.fromkeys(state['xp'], 100.)
        receipt = Training.settle_phase(state, plan(), career.environment('frontier'), 'exclusive')
        excellence = [e for e in receipt['general'] if e['exceptional']]
        self.assertTrue(excellence)
        for entry in excellence:
            self.assertEqual(entry['excellence_permit'], 1)
            self.assertEqual(entry['coach_permit'], 0)
            self.assertIsNone(entry['coach_roll'])
        self.assertTrue(all(e['permit_awarded'] <= 1 for e in receipt['general']))

    def test_specialization_keeps_the_general_budget_when_quality_coaching_is_enabled(self):
        normal, specific = self.state(seed=self.coach_seed(), value=130), self.state(seed=self.coach_seed(), value=130)
        for state in (normal, specific):
            state['xp'] = dict.fromkeys(state['xp'], 100.)
        a = Training.settle_phase(normal, plan(), career.environment('frontier'), 'normal_coached')
        b = Training.settle_phase(specific, plan(specialized=True), career.environment('frontier'), 'specific_coached')
        self.assertEqual(a['budget'], b['budget'])
        self.assertEqual([e['path'] for e in a['general']], [e['path'] for e in b['general']])
        self.assertEqual([e['roll'] for e in a['general']], [e['roll'] for e in b['general']])
        self.assertEqual([e['coach_roll'] for e in a['general']], [e['coach_roll'] for e in b['general']])

    def test_fatigue_reduces_xp_but_keeps_budget_and_rolls(self):
        normal, tired = self.state(value=130), self.state(value=130)
        normal['fatigue'], tired['fatigue'] = 18, 85
        a = Training.settle_phase(normal, plan(specialized=True), career.environment(), 'normal')
        b = Training.settle_phase(tired, plan(specialized=True), career.environment(), 'tired')
        self.assertEqual(a['budget'], b['budget'])
        self.assertEqual([e['roll'] for e in a['focused']], [e['roll'] for e in b['focused']])
        self.assertLess(sum(e['xp_awarded'] for e in b['focused']), sum(e['xp_awarded'] for e in a['focused']))
        self.assertAlmostEqual(b['fatigue']['efficiency'], .75)

    def test_rest_consumes_phase_and_reduces_fatigue_without_awarding_training(self):
        state = self.state(); state['fatigue'] = 70
        before_xp, before_permits = dict(state['xp']), dict(state['permits'])
        receipt = Training.settle_phase(state, rest(0, 0), career.environment(), 'rest0')
        self.assertEqual(receipt['focused'], [])
        self.assertEqual(receipt['general'], [])
        self.assertEqual(receipt['body'], [])
        self.assertEqual(state['xp'], before_xp)
        self.assertEqual(state['permits'], before_permits)
        self.assertEqual(state['fatigue'], 48)
        self.assertEqual(state['training_release']['phase'], 1)
        Training.settle_phase(state, plan(0, 1), career.environment(), 'after_rest')
        self.assertEqual(state['month'], 1)

    def test_workload_above_the_display_ceiling_is_not_free_recovery(self):
        state = self.state(); state['fatigue'] = 95
        receipt = Training.settle_phase(state, plan(specialized=True), career.environment('national'), 'overload')
        self.assertEqual(receipt['fatigue']['unclamped_peak'], 116)
        self.assertEqual(receipt['fatigue']['peak'], 100)
        self.assertEqual(receipt['fatigue']['overload'], 16)
        self.assertEqual(state['fatigue'], 100)
        normal = self.state(); normal['fatigue'] = 95
        receipt = Training.settle_phase(normal, plan(), career.environment('national'), 'normal_load')
        self.assertAlmostEqual(normal['fatigue'], 95 + 15 - 15.4)
        self.assertGreater(normal['fatigue'], 90)

    def test_rehabilitation_allows_only_one_training_phase_and_failed_month_rolls_back(self):
        state = self.state()
        career.major_injury(state, 'injury', 0, severity=2)
        before = copy.deepcopy(state)
        with self.assertRaisesRegex(ValueError, 'REHABILITATION'):
            Training.settle_month(state, [plan(0, 0), plan(0, 1)], career.environment(), 'bad_month')
        self.assertEqual(state, before)
        Training.settle_month(state, [plan(0, 0), rest(0, 1)], career.environment(), 'rehab_month')
        self.assertEqual(state['audit']['TRAINING_ROLLS'], 4)
        self.assertEqual(state['month'], 1)

    def test_bad_learning_event_batch_is_transactional(self):
        state = self.state(); before = copy.deepcopy(state)
        valid = dict(id='review', month=0, source='SYNTHETIC', evidence_ref='fixture:review',
                     kind='match_review', paths=['bh.spin'], usage={'bh.spin': 12}, challenge=1., review_quality=1.)
        bad = dict(valid, id='invalid', month=1, evidence_ref='fixture:invalid')
        with self.assertRaises(ValueError):
            Training.settle_phase(state, plan(), career.environment(), 'settlement', events=[valid, bad])
        self.assertEqual(state, before)

    def test_partial_old_helper_and_clock_mixing_are_rejected(self):
        state = self.state()
        career.train(state, 'bh.spin', 40, 18, career.environment(), 0)
        with self.assertRaisesRegex(ValueError, 'MIXED'):
            Training.settle_phase(state, plan(), career.environment(), 'mixed')
        state = self.state()
        career.run_month(state, SCHEMA, career.environment())
        with self.assertRaisesRegex(ValueError, 'CLOCK'):
            Training.settle_phase(state, plan(1), career.environment(), 'mixed_clock')

    def test_save_after_phase_zero_resumes_exactly_and_month_mode_matches_phase_mode(self):
        continuous, batched = self.state(), self.state()
        Training.settle_phase(continuous, plan(), career.environment(), 'month:phase0')
        resumed = Training.load_state(Training.dump_state(continuous))
        Training.settle_phase(continuous, plan(0, 1), career.environment(), 'month:phase1')
        Training.settle_phase(resumed, plan(0, 1), career.environment(), 'month:phase1')
        Training.settle_month(batched, [plan(), plan(0, 1)], career.environment(), 'month')
        self.assertEqual(continuous, resumed)
        self.assertEqual(continuous, batched)

    def test_real_start_age_controls_aging_and_annual_record(self):
        state = self.state(start_age=35)
        for month in range(12):
            Training.settle_month(state, [rest(month, 0), rest(month, 1)], career.environment(), f'rest{month}', record=False)
        self.assertEqual(state['training_release']['monthly_aging'][0]['age'], 35)
        self.assertEqual(state['yearly'][0]['age'], 36)
        self.assertEqual(state['month'], 12)
        self.assertEqual(state['training_log'], [])

    def test_preset_age_and_independent_learning_factors_are_not_rerolled(self):
        card = fixtures.ordinary_card(SCHEMA)
        paths = [f'{g}.{k}' for g, sub in card['children'].items() for k in sub]
        card['age_approx'] = 31
        card['learning_factor'] = {p: 1.17 for p in paths}
        card['style_preference'] = {p: .87 for p in paths}
        state = Training.initialize(card, seed=47)
        self.assertEqual(state['start_age'], 31)
        self.assertEqual(state['learning_factor'], card['learning_factor'])
        self.assertEqual(state['style_preference'], card['style_preference'])
        card['learning_factor'].pop(paths[0])
        with self.assertRaises(ValueError):
            Training.initialize(card)

    def test_compact_mode_preserves_actual_outcomes_and_receipts(self):
        full, compact = self.state(), self.state()
        a = Training.settle_month(full, [plan(), plan(0, 1)], career.environment(), 'm')
        b = Training.settle_month(compact, [plan(), plan(0, 1)], career.environment(), 'm', record=False)
        self.assertEqual(a, b)
        for key in ('children', 'P6', 'PA', 'xp', 'permits', 'P_xp', 'fatigue', 'audit', 'settled_drills', 'month'):
            self.assertEqual(full[key], compact[key], key)
        self.assertEqual(compact['training_log'], [])
        self.assertTrue(full['training_log'])


if __name__ == '__main__':
    unittest.main()
