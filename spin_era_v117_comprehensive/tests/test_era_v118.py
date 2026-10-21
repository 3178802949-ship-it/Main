"""Dated facts, author priors and explicit bounded era context."""
import copy
from datetime import date
import unittest

from Area import v117, v118


class EraV118Tests(unittest.TestCase):
    def test_old_calendar_values_and_horizon_are_retained(self):
        for year in (2000, 2006, 2026, 2027, 2028):
            current, old = v118.calendar_for_year(year), v117.calendar_for_year(year)
            self.assertEqual(current['events'], old['events'])
            self.assertTrue(v118.validate_calendar(current)['valid'])
        self.assertEqual(v118.ensure_date('2028-07-30'), '2028-07-30')
        with self.assertRaises(ValueError):
            v118.context_for_date('2028-07-31')

    def test_future_interview_is_not_historical_personality_fact(self):
        sources = [dict(source_id='interview', source_date='2015-06-01', cue='细致准备')]
        result = v118.filter_temporal_sources(sources, '2006-02-01')
        self.assertEqual(result['available'], [])
        self.assertEqual(result['design_priors'], [])
        self.assertEqual(result['excluded'][0]['reason'], 'FUTURE_SOURCE')
        result = v118.filter_temporal_sources(sources, '2006-02-01', allow_design_priors=True)
        self.assertEqual(result['available'], [])
        self.assertEqual(result['design_priors'][0]['temporal_scope'], 'OUT_OF_WORLD_DESIGN_PRIOR')
        self.assertTrue(result['design_priors'][0]['not_in_world_knowledge'])

    def test_current_paper_can_be_design_basis_without_entering_old_world(self):
        source = dict(source_id='later-paper', publication_year=2024, purpose='DESIGN_BASIS')
        part = v118.filter_temporal_sources([source], 2006, allow_design_priors=True)
        self.assertEqual(part['design_priors'][0]['reason'], 'FUTURE_SOURCE')
        self.assertEqual(part['available'], [])

    def test_exact_day_and_year_only_sources_have_conservative_cutoffs(self):
        sources = [dict(id='year-only', source_year=2006), dict(id='dated', source_date='2006-02-01')]
        part = v118.filter_temporal_sources(sources, '2006-02-01')
        self.assertEqual([x['id'] for x in part['available']], ['dated'])
        part = v118.filter_temporal_sources(sources, 2006)
        self.assertEqual(len(part['available']), 2)
        self.assertEqual(part['temporal_precision'], 'YEAR_END')
        self.assertEqual(v118.context_for_date(2028)['as_of'], '2028-07-30')

    def test_undated_material_never_becomes_known_fact_by_default(self):
        part = v118.filter_temporal_sources([dict(id='unknown', cue='未知')], 2020)
        self.assertEqual(part['available'], [])
        self.assertEqual(part['excluded'][0]['reason'], 'UNDATED_SOURCE')
        part = v118.filter_temporal_sources([dict(id='unknown')], 2020, allow_design_priors=True)
        self.assertEqual(part['design_priors'][0]['reason'], 'UNDATED_SOURCE')

    def test_invalid_exact_date_cannot_fall_back_to_older_year(self):
        source = dict(id='bad', source_date='2020-02-31', source_year=2000)
        part = v118.filter_temporal_sources([source], 2026)
        self.assertEqual(part['available'], [])
        self.assertEqual(part['excluded'][0]['reason'], 'INVALID_DECLARED_DATE')

    def test_future_snapshot_is_rejected_but_old_snapshot_is_only_a_baseline(self):
        result = v118.validate_context('2006-02-01', cards=[dict(player_id='future', year=2008),
            dict(player_id='older', year=2004), dict(player_id='later_day', year=2006, snapshot_date='2006-04-01')])
        self.assertFalse(result['valid'])
        self.assertIn('FUTURE_PLAYER_SNAPSHOT:future', result['errors'])
        self.assertIn('FUTURE_PLAYER_SNAPSHOT_DATE:later_day', result['errors'])
        self.assertIn('OLDER_SNAPSHOT_IS_NOT_AUTOMATICALLY_GROWN:older', result['warnings'])

    def test_no_equipment_chronology_is_invented_without_evidence(self):
        item = dict(id='unsourced-equipment', verified_not_before='2014-01-01')
        result = v118.validate_context(2006, rule_items=[item])
        self.assertTrue(result['valid'])
        self.assertIn('UNVERIFIED_CHRONOLOGY_NO_AUTOMATIC_BAN:unsourced-equipment', result['warnings'])
        item.update(constraint_status='SOURCE_EVIDENCED', evidence_ref='CALLER_DECLARED_REFERENCE_NOT_AUTHENTICATED')
        result = v118.validate_context(2006, rule_items=[item])
        self.assertFalse(result['valid'])
        self.assertIn('BEFORE_DECLARED_RULE_AVAILABILITY:unsourced-equipment', result['errors'])
        self.assertTrue(v118.validate_context(2016, rule_items=[item])['valid'])

    def test_invalid_sources_and_constraints_return_diagnostics(self):
        result = v118.validate_context(2006, cards=[None, dict(player_id='x', year=True)],
            sources=[None, dict(id='bad-date', source_date=True)],
            rule_items=[None, dict(id='bad', verified_not_before=True, constraint_status='SOURCE_EVIDENCED', evidence_ref='ref')])
        self.assertFalse(result['valid'])
        self.assertEqual(result['source_partition']['available'], [])

    def test_validation_does_not_mutate_any_input(self):
        payload = dict(cards=[dict(player_id='a', year=2006)], sources=[dict(id='x', publication_year=2008)],
                       rule_items=[dict(id='equipment')])
        before = copy.deepcopy(payload)
        v118.validate_context('2006-02-01', **payload, allow_design_priors=True)
        self.assertEqual(payload, before)

    def test_context_does_not_self_certify_real_calendars(self):
        result = v118.validate_context(date(2028, 7, 30))
        self.assertFalse(result['complete_real_2025_2026_calendars_present'])
        self.assertIn('NOT_OFFICIAL', result['validation_boundary'])
        for bad in (True, 1999, 2029, '2006'):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                v118.context_for_date(bad)


if __name__ == '__main__':
    unittest.main()
