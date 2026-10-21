"""Bounded forward planning, legacy separation and inherited entry preflight."""
from pathlib import Path
import copy
from datetime import date
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Area
from Area import v117 as forward


class CalendarV117Tests(unittest.TestCase):
    def test_2027_to_2028_refresh_has_explicit_forward_era_and_calendar(self):
        previous = forward.get_era(2027)
        current = forward.get_era(2028)
        self.assertEqual(previous['classification'], 'SIMULATED_FORWARD')
        self.assertEqual(current['requested_year'], 2028)
        self.assertEqual(current['career_horizon_end'], forward.HORIZON_END)
        self.assertTrue(forward.validate_calendar(forward.calendar_for_year(2028))['valid'])
        self.assertNotEqual(current['requested_year'], previous['requested_year'])

    def test_2029_and_wrong_year_types_are_rejected(self):
        for bad in (1999, 2029, True, 2028., '2028'):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    forward.get_era(bad)
                with self.assertRaises(ValueError):
                    forward.calendar_for_year(bad)

    def test_cutoff_is_inclusive_and_never_silently_clamps(self):
        self.assertEqual(forward.ensure_date('2028-07-30'), '2028-07-30')
        self.assertEqual(forward.ensure_date(date(2028, 7, 30)), '2028-07-30')
        for bad in ('2028-07-31', '2029-01-01', '1999-12-31', '2028-02-30', None, True):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                forward.ensure_date(bad)

    def test_event_and_training_plan_dates_after_cutoff_fail(self):
        calendar = forward.calendar_for_year(2028)
        calendar['events'][0].update(start_date='2028-08-01', end_date='2028-08-04')
        checked = forward.validate_calendar(calendar)
        self.assertFalse(checked['valid'])
        self.assertTrue(any('OUTSIDE_CAREER_HORIZON' in s for s in checked['errors']))
        with self.assertRaises(ValueError):
            forward.ensure_date('2028-08-01')  # World's proposed next training date.

    def test_forward_templates_keep_provenance_and_no_historical_champions(self):
        for year, base in ((2027, 2025), (2028, 2026)):
            calendar = forward.calendar_for_year(year)
            self.assertEqual(calendar['planning_reference_year'], base)
            self.assertFalse(calendar['complete'])
            self.assertFalse(calendar['historical_calendar_verified'])
            for event in calendar['events']:
                self.assertEqual(event['status'], 'SIMULATED')
                self.assertTrue(event['future_schedule'])
                self.assertTrue(event['provenance'])
                self.assertFalse(event['confirmed'])
                self.assertNotIn('historical_reference', event)
                self.assertLessEqual(event['end_date'], forward.HORIZON_END)
            checked = forward.validate_calendar(calendar)
            self.assertTrue(checked['valid'], checked)
            self.assertFalse(checked['publication_ready'])

    def test_2028_olympic_single_and_team_window_are_simulations(self):
        events = [e for e in forward.calendar_for_year(2028)['events'] if e['level'] == 'olympics']
        self.assertEqual({e['kind'] for e in events}, {'adult_singles', 'team'})
        for event in events:
            self.assertEqual((event['start_date'], event['end_date']), forward.OLYMPIC_WINDOW_2028)
            self.assertGreaterEqual(date.fromisoformat(event['start_date']).day, 16)
            self.assertFalse(event['confirmed'])

    def test_worlds_disciplines_stay_distinct_in_forward_years(self):
        for year, expected in ((2027, 'adult_singles'), (2028, 'team')):
            calendar = forward.calendar_for_year(year)
            event = next(e for e in calendar['events'] if e['level'] == 'world_championships')
            self.assertEqual(event['kind'], expected)
            event['kind'] = 'team' if expected == 'adult_singles' else 'adult_singles'
            self.assertTrue(any('DISCIPLINE_YEAR' in s for s in forward.validate_calendar(calendar)['errors']))

    def test_future_olympic_year_and_youth_grand_guards_remain_active(self):
        calendar = forward.calendar_for_year(2027)
        event = calendar['events'][0]
        event.update(category='grand', level='olympics')
        self.assertFalse(forward.validate_calendar(calendar)['valid'])
        calendar = forward.calendar_for_year(2028)
        event = next(e for e in calendar['events'] if e['level'] == 'olympics')
        event['kind'] = 'youth_singles'
        self.assertFalse(forward.validate_calendar(calendar)['valid'])

    def test_future_event_requires_explicit_schedule_declaration(self):
        calendar = forward.calendar_for_year(2028)
        calendar['events'][0].pop('future_schedule')
        self.assertFalse(forward.validate_calendar(calendar)['valid'])
        calendar = forward.calendar_for_year(2028)
        calendar['events'][0]['historical_schedule_verified'] = True
        self.assertFalse(forward.validate_calendar(calendar)['valid'])

    def test_forward_reference_mode_has_no_confirmed_dates(self):
        calendar = forward.calendar_for_year(2028, 'historical_reference')
        self.assertTrue(all(e['status'] == 'PLANNED' and e['start_date'] is None for e in calendar['events']))
        result = forward.validate_calendar(calendar)
        self.assertTrue(result['valid'], result)
        player = dict(player_id='p', age=25, region='Asia')
        self.assertFalse(forward.check_entry(calendar, calendar['events'][0]['event_id'], player)['eligible'])

    def test_age_region_duplicates_and_conflicts_use_existing_entry_logic(self):
        calendar = forward.calendar_for_year(2028)
        asian = next(e for e in calendar['events'] if e['category'] == 'continental')
        player = dict(player_id='p', age=22, region='Asia')
        self.assertTrue(forward.check_entry(calendar, asian['event_id'], player)['eligible'])
        self.assertFalse(forward.check_entry(calendar, asian['event_id'], dict(player, region='Europe'))['eligible'])
        self.assertFalse(forward.check_entry(calendar, asian['event_id'], player, [asian['event_id']])['eligible'])
        asian['min_age'] = 23
        self.assertFalse(forward.check_entry(calendar, asian['event_id'], player)['eligible'])
        olympics = [e for e in calendar['events'] if e['level'] == 'olympics']
        checked = forward.check_entry(calendar, olympics[0]['event_id'], player, [olympics[1]['event_id']])
        self.assertTrue(any('DATE_CONFLICT' in e for e in checked['errors']))

    def test_ordinary_major_count_is_not_fixed_to_nine(self):
        calendar = forward.calendar_for_year(2028)
        calendar['events'] = [e for e in calendar['events'] if e['category'] != 'major']
        self.assertTrue(forward.validate_calendar(calendar)['valid'])

    def test_legacy_area_contract_and_global_year_sets_are_unchanged(self):
        olympic = set(Area.OLYMPIC_YEARS)
        singles = set(Area.SINGLES_WORLDS)
        forward.validate_calendar(forward.calendar_for_year(2028))
        self.assertEqual(Area.OLYMPIC_YEARS, olympic)
        self.assertEqual(Area.SINGLES_WORLDS, singles)
        self.assertNotIn(2028, Area.OLYMPIC_YEARS)
        with self.assertRaises(ValueError):
            forward._BASE_ERA(2028)

    def test_return_values_are_copies_and_packaged_templates_match(self):
        for year in (2027, 2028):
            path = ROOT / 'data' / f'calendar_{year}_v117.json'
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            calendar = forward.calendar_for_year(year)
            self.assertEqual(calendar, json.loads(path.read_text()))
            calendar['events'][0]['name'] = 'changed'
            self.assertNotEqual(calendar, forward.calendar_for_year(year))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_malformed_calendar_is_reported_without_crashing(self):
        for bad in (None, {'events': None}, {'year': 2028, 'mode': 'sandbox', 'events': [None]}):
            self.assertFalse(forward.validate_calendar(bad)['valid'])
            self.assertFalse(forward.check_entry(bad, 'missing', {'age': 20})['eligible'])

    def test_unhashable_and_boolean_years_do_not_reach_legacy_membership(self):
        for bad in ([], {}, True, None):
            calendar = forward.calendar_for_year(2028)
            calendar['year'] = bad
            self.assertFalse(forward.validate_calendar(calendar)['valid'])
            self.assertFalse(forward.check_entry(calendar, calendar['events'][0]['event_id'], {'age': 22})['eligible'])


if __name__ == '__main__':
    unittest.main()
