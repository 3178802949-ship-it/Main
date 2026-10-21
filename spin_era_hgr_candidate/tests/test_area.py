"""Era, reference provenance and ordinary-calendar preflight checks."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Area


class AreaTests(unittest.TestCase):
    def calendar(self, year=2006):
        return Area.calendar_for_year(year)

    def major(self, calendar):
        return next(e for e in calendar['events'] if e['category'] == 'major')

    def world(self, calendar, kind):
        return next(e for e in calendar['events'] if e['level'] == 'world_championships' and e['kind'] == kind)

    def test_all_seven_era_boundaries_and_forward_context(self):
        ids = {Area.get_era(year)['era_id'] for year in (2000, 2004, 2008, 2012, 2016, 2021, 2024)}
        self.assertEqual(len(ids), 7)
        self.assertEqual(Area.get_era(2020)['era_id'], '2016_2021')
        self.assertEqual(Area.get_era(2021)['era_id'], '2021_2024')
        self.assertIn('NO_BUILT_ROSTER', Area.get_era(2027)['status'])
        for bad in (1999, 2028, True, 2006.0):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Area.get_era(bad)

    def test_era_objects_are_copies_and_not_npc_growth(self):
        a = Area.get_era(2006)
        a['innovations'].clear()
        self.assertGreater(len(Area.get_era(2006)['innovations']), 0)
        self.assertIn('NOT_AUTOMATIC_NPC', a['scope'])

    @patch('Area._presets')
    def test_exact_preset_filtering_never_substitutes_future(self, presets):
        presets.return_value = [dict(player_id='p', year=2004, CA=140),
                                dict(player_id='p', year=2008, CA=170),
                                dict(player_id='q', year=2004, CA=130)]
        self.assertEqual(len(Area.list_presets(year=2004)), 2)
        self.assertEqual(Area.get_preset('p', 2004)['CA'], 140)
        with self.assertRaises(KeyError):
            Area.get_preset('p', 2006)
        with self.assertRaises(KeyError):
            Area.get_preset('p', 2000, allow_prior=True)
        old = Area.get_preset('p', 2006, allow_prior=True)
        self.assertEqual(old['year'], 2004)
        self.assertEqual(old['selection']['mode'], 'PRIOR_BASELINE_NOT_GROWN')
        old['CA'] = 999
        self.assertEqual(presets.return_value[0]['CA'], 140)

    @patch('Area._presets')
    def test_duplicate_exact_roster_keys_are_not_silently_resolved(self, presets):
        presets.return_value = [dict(player_id='p', year=2004), dict(player_id='p', year=2004)]
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            Area.get_preset('p', 2004)

    def test_2006_template_is_valid_sandbox_with_no_nine_station_requirement(self):
        c = self.calendar()
        result = Area.validate_calendar(c)
        self.assertTrue(result['valid'], result)
        self.assertEqual(result['coverage'], dict(events=6, grand_events=2, major_events=3, continental_events=1))
        self.assertNotIn('major9_required', c)
        self.assertFalse(result['publication_ready'])
        self.assertFalse(result['historical_calendar_verified'])
        self.assertTrue(any('FULL_CALENDAR' in x for x in result['warnings']))
        self.assertTrue(all('historical_reference' not in e for e in c['events']))

    def test_ordinary_major_count_is_configurable(self):
        c = self.calendar()
        c['events'] = [e for e in c['events'] if e['category'] != 'major']
        self.assertTrue(Area.validate_calendar(c)['valid'])
        self.assertEqual(Area.validate_calendar(c)['coverage']['major_events'], 0)

    def test_source_anchors_are_readonly_references_not_titles_or_verified_dates(self):
        c = Area.calendar_for_year(2026, mode='historical_reference')
        self.assertTrue(any(e['level'] == 'world_cup' for e in c['events']))
        self.assertTrue(all(e['provenance'] == 'SOURCE_ARCHIVE_UNVERIFIED' for e in c['events']))
        self.assertTrue(all(e['start_date'] is None for e in c['events']))
        r = Area.validate_calendar(c)
        self.assertTrue(r['valid'], r)
        self.assertFalse(r['historical_calendar_verified'])
        p = dict(player_id='p', age=30, region='Asia')
        self.assertFalse(Area.check_entry(c, c['events'][0]['event_id'], p)['eligible'])

    def test_2006_worlds_must_be_team_not_singles(self):
        c = self.calendar()
        event = self.world(c, 'team')
        event['kind'] = 'adult_singles'
        r = Area.validate_calendar(c)
        self.assertFalse(r['valid'])
        self.assertTrue(any('DISCIPLINE_YEAR' in x for x in r['errors']))

    def test_2020_olympics_not_held_and_2021_requires_nominal_2020(self):
        c = self.calendar(2021)
        olympic = next(e for e in c['events'] if e['level'] == 'olympics')
        self.assertEqual(olympic['nominal_year'], 2020)
        self.assertTrue(Area.validate_calendar(c)['valid'])
        olympic.pop('nominal_year')
        self.assertFalse(Area.validate_calendar(c)['valid'])
        c = self.calendar(2020)
        event = self.major(c)
        event.update(category='grand', level='olympics')
        self.assertTrue(any('OLYMPIC_YEAR' in x for x in Area.validate_calendar(c)['errors']))

    def test_no_fictional_2021_to_2023_individual_world_cup(self):
        for year in (2021, 2022, 2023):
            c = self.calendar(year)
            self.assertFalse(any(e['level'] == 'world_cup' for e in c['events']))
            event = self.major(c)
            event.update(category='grand', level='world_cup')
            self.assertFalse(Area.validate_calendar(c)['valid'])
        self.assertTrue(any(e['level'] == 'world_cup' for e in self.calendar(2024)['events']))

    def test_wrong_level_cannot_bypass_year_checks_by_category_rename(self):
        c = self.calendar()
        e = self.major(c)
        e.update(category='other', level='olympics')
        self.assertTrue(any('REQUIRES_GRAND' in x for x in Area.validate_calendar(c)['errors']))

    def test_senior_grand_levels_cannot_be_youth_events(self):
        c = self.calendar(2024)
        e = next(e for e in c['events'] if e['category'] == 'grand')
        e['kind'] = 'youth_singles'
        self.assertTrue(any('YOUTH_EVENT' in x for x in Area.validate_calendar(c)['errors']))

    def test_modern_wtt_level_is_not_backported_to_2006(self):
        c = self.calendar()
        self.major(c)['level'] = 'wtt_grand_smash'
        self.assertFalse(Area.validate_calendar(c)['valid'])

    def test_duplicate_ids_invalid_dates_and_cross_year_ranges_fail(self):
        c = self.calendar()
        c['events'].append(copy.deepcopy(c['events'][0]))
        self.assertFalse(Area.validate_calendar(c)['valid'])
        for dates in [('2006-02-30', '2006-03-01'), ('2006-05-02', '2006-05-01'), ('2006-12-31', '2007-01-02')]:
            c = self.calendar()
            self.major(c).update(start_date=dates[0], end_date=dates[1])
            self.assertFalse(Area.validate_calendar(c)['valid'])

    def test_calendar_and_event_flags_require_correct_types(self):
        for changes in ({'year': True}, {'year': '2006'}, {'mode': 'official_guess'}, {'complete': 'yes'}):
            c = self.calendar(); c.update(changes)
            self.assertFalse(Area.validate_calendar(c)['valid'])
        c = self.calendar(); self.major(c)['confirmed'] = 'yes'
        self.assertFalse(Area.validate_calendar(c)['valid'])

    def test_continent_precheck_maps_delegations_and_does_not_claim_qualification(self):
        c = self.calendar()
        e = next(e for e in c['events'] if e['category'] == 'continental')
        player = dict(player_id='p', nation_prototype='中国', birth_year=1988)
        r = Area.check_entry(c, e['event_id'], player)
        self.assertTrue(r['eligible'], r)
        self.assertFalse(r['official_qualification_confirmed'])
        self.assertIn('PRECHECK_ONLY', ' '.join(r['warnings']))
        player['nation_prototype'] = '瑞典'
        self.assertIn('CONTINENT_INELIGIBLE', Area.check_entry(c, e['event_id'], player)['errors'])
        player.pop('nation_prototype')
        self.assertIn('REGION_REQUIRED', Area.check_entry(c, e['event_id'], player)['errors'])

    def test_exact_birth_date_handles_age_cutoff(self):
        c = self.calendar(); e = self.major(c); e['min_age'] = 18
        p = dict(player_id='p', birth_year=1988, region='Asia')
        self.assertIn('AGE_CUTOFF_REQUIRES_EXACT_BIRTHDAY', Area.check_entry(c, e['event_id'], p)['errors'])
        p['birth_date'] = '1988-12-01'
        self.assertIn('AGE_INELIGIBLE', Area.check_entry(c, e['event_id'], p)['errors'])
        p['birth_date'] = '1988-01-01'
        self.assertTrue(Area.check_entry(c, e['event_id'], p)['eligible'])

    def test_overlapping_entry_rejected_but_same_month_nonoverlap_allowed(self):
        c = self.calendar(); a, b = [e for e in c['events'] if e['category'] == 'major'][:2]
        p = dict(player_id='p', age=22, region='Asia')
        b.update(start_date=a['start_date'], end_date=a['end_date'])
        before = copy.deepcopy(c)
        r = Area.check_entry(c, b['event_id'], p, existing_entries=[a['event_id']])
        self.assertTrue(any('DATE_CONFLICT' in x for x in r['errors']))
        self.assertEqual(c, before)
        b.update(start_date='2006-02-20', end_date='2006-02-23')
        self.assertTrue(Area.check_entry(c, b['event_id'], p, existing_entries=[a['event_id']])['eligible'])

    def test_duplicate_entry_and_cancellation_are_rejected(self):
        c = self.calendar(); e = self.major(c); p = dict(player_id='p', age=22)
        self.assertIn('DUPLICATE_ENTRY', Area.check_entry(c, e['event_id'], p, [e['event_id']])['errors'])
        e['status'] = 'CANCELLED'
        self.assertFalse(Area.check_entry(c, e['event_id'], p)['eligible'])

    def test_preflight_is_not_a_registration_mutation(self):
        c = self.calendar(); p = dict(player_id='p', age=22)
        before = copy.deepcopy((c, p))
        Area.check_entry(c, self.major(c)['event_id'], p)
        self.assertEqual((c, p), before)

    def test_malformed_calendar_cannot_crash_entry_preflight(self):
        for invalid in (None, {'events': None}, {'year': 2006, 'mode': 'sandbox', 'events': [None]}):
            self.assertFalse(Area.check_entry(invalid, 'missing', {'age': 18})['eligible'])

    def test_packaged_2006_template_matches_tested_generator(self):
        template = json.loads((ROOT / 'data/calendar_template_2006.json').read_text())
        self.assertEqual(template, Area.calendar_for_year(2006))


if __name__ == '__main__':
    unittest.main()
