"""Card/ranking contracts; no source archive is written by these checks."""
import copy
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Card
from common import SCHEMA
import career_v116 as career


class CardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / 'data/original/spin_era_players_archive_2000_2026_v12.json'
        cls.original = json.loads(cls.source.read_text())['profiles']

    def test_all_370_profiles_preserve_numeric_traits_and_original_bytes(self):
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.assertEqual(len(self.original), 370)
        for source in self.original:
            with self.subTest(player=source['player_id'], year=source['year']):
                card = Card.normalize(source)
                self.assertEqual(card['children'], source['children'])
                self.assertEqual(card['P6'], source['P6'])
                self.assertEqual(card['CA'], source['CA'])
                self.assertEqual(len(card['learning_factor']), 43)
                self.assertEqual(len(card['development_profile']['talent']), 43)
                self.assertTrue(Card.validate(card))
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), digest)

    def test_normalization_is_read_only_and_json_portable(self):
        source = copy.deepcopy(self.original[0]); before = copy.deepcopy(source)
        card = Card.normalize(source)
        self.assertEqual(source, before)
        self.assertEqual(json.loads(json.dumps(card)), card)
        card['children']['fh']['spin'] -= 1
        self.assertEqual(source, before)

    def test_normalization_is_idempotent_and_keeps_original_provenance(self):
        first = Card.normalize(self.original[0])
        second = Card.normalize(first)
        self.assertEqual(first, second)

    def test_state_recomputation_exports_current_injury_ceiling(self):
        card = Card.make_ma18()
        state = career.start(card, seed=123, development_profile=card['development_profile'])
        career.major_injury(state, 'injury', 0, severity=4)
        exported = Card.recompute({**card, **state})
        self.assertEqual(exported['development_profile']['body_max'], state['P_max'])
        self.assertTrue(Card.validate(exported))

    def test_historical_titles_and_story_gender_remain_explicit_references(self):
        source = self.original[0]; card = Card.normalize(source)
        self.assertEqual(card['source_prototype'], 'real_mens_player')
        self.assertEqual(card['source_story_gender'], source['gender_in_story'])
        self.assertEqual(card['story_gender'], source['gender_in_story'])
        self.assertEqual(card['simulated_career']['titles'], [])
        self.assertEqual(card['historical_reference']['champion_history'], source['champion_history_as_of_snapshot'])
        self.assertEqual(card['development_profile']['classification'], 'ASSESSMENT')

    def test_legacy_lazy_growth_is_reference_only_not_an_active_instruction(self):
        source = copy.deepcopy(self.original[0])
        self.assertEqual(source['growth']['mode'], 'lazy_deterministic')
        card = Card.normalize(source)
        self.assertNotIn('growth', card)
        self.assertEqual(card['legacy_growth_reference'], source['growth'])
        self.assertEqual(card['growth_contract'], dict(authority='Training',
            schedule='TWO_PHASE_CATEGORY_TRAINING', legacy_lazy_growth_active=False))
        self.assertEqual(Card.normalize(card), card)
        self.assertEqual(source, self.original[0])

    def test_pa_does_not_infer_body_talent_or_learning(self):
        source = copy.deepcopy(self.original[0]); source['PA'] = 150
        other = copy.deepcopy(source); other['PA'] = 200
        low, high = Card.normalize(source), Card.normalize(other)
        for key in ('children', 'P6', 'G9', 'CA', 'development_profile', 'learning_factor', 'style_preference'):
            self.assertEqual(low[key], high[key], key)
        self.assertGreater(low['CA'], low['PA'])
        self.assertNotIn('CA_effective', low)

    def test_invalid_mapping_nan_bool_and_stale_aggregates_are_rejected(self):
        base = Card.normalize(self.original[0])
        variants = []
        x = copy.deepcopy(base); del x['children']['read']['choice']; variants.append(x)
        x = copy.deepcopy(base); x['children']['fh']['spin'] = float('nan'); variants.append(x)
        x = copy.deepcopy(base); x['P6']['speed'] = True; variants.append(x)
        x = copy.deepcopy(base); x['G9']['read'] -= 1; variants.append(x)
        x = copy.deepcopy(base); x['CA'] -= 1; variants.append(x)
        x = copy.deepcopy(base); del x['learning_factor']['bh.power']; variants.append(x)
        x = copy.deepcopy(base); x['development_profile']['body_max']['speed'] = 0; variants.append(x)
        x = copy.deepcopy(base); x['id'] = 'different'; variants.append(x)
        for index, variant in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                Card.validate(variant)

    def test_recompute_updates_subskill_aggregation_without_losing_metadata(self):
        card = Card.normalize(self.original[0]); card['children']['read']['choice'] = 100
        card['custom_world_id'] = 'sandbox-1'
        changed = Card.recompute(card)
        self.assertEqual(changed['custom_world_id'], 'sandbox-1')
        self.assertLess(changed['G9']['read'], card['G9']['read'])
        self.assertTrue(Card.validate(changed))
        self.assertEqual(card['G9']['read'], 140)

    def test_only_four_physical_legacy_exceptions_are_explicitly_preserved(self):
        issues = []
        for source in self.original:
            card = Card.normalize(source)
            for issue in card['grandfathered_over_cap']:
                issues.append((card['player_id'], card['year'], issue['path']))
        self.assertEqual(set(issues), {('liu_seungmin', 2000, 'fh.power'),
            ('liu_seungmin', 2012, 'fh.power'), ('truls_moregard', 2021, 'fh.power'),
            ('sora_matsushima', 2024, 'bh.power')})
        source = next(p for p in self.original if p['player_id'] == 'liu_seungmin' and p['year'] == 2000)
        card = Card.normalize(source)
        state = career.start(card, seed=123, development_profile=card['development_profile'])
        original = state['children']['fh']['power']
        career.train(state, 'fh.power', 1, card['age_approx'], career.environment('club'), month=0)
        self.assertEqual(state['children']['fh']['power'], original)
        self.assertLess(career.soft_cap(state, 'fh.power'), original)

    def test_saved_preset_library_has_exact_year_selection_and_no_future_fill(self):
        card = Card.get_preset('ma_long', 2016)
        self.assertEqual(card['year'], 2016)
        with self.assertRaises(ValueError):
            Card.get_preset('ma_long', 2015)
        card['children']['read']['choice'] = 0
        self.assertNotEqual(Card.get_preset('ma_long', 2016)['children']['read']['choice'], 0)

    def test_ma18_is_complete_synthetic_fixture_not_history_or_champion_grant(self):
        card = Card.make_ma18()
        self.assertEqual(card['CA'], 159)
        self.assertEqual(card['PA'], 198)
        self.assertEqual(card['age_approx'], 18)
        self.assertEqual(card['classification'], 'SIMULATED')
        self.assertEqual(card['origin'], 'MODEL_INTERPOLATION_NOT_HISTORICAL')
        self.assertEqual(card['simulated_career']['titles'], [])
        self.assertTrue(Card.validate(card))


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.book = Card.RankingBook()
        self.book.register_player('A')
        self.book.register_player('B', elo=1540)

    def test_adult_and_youth_ratings_are_separate_and_symmetric(self):
        before = self.book.snapshot()['players']
        result = self.book.settle_match('m1', 'A', 'B', 'A', '2006-01-01')
        after = self.book.snapshot()['players']
        self.assertGreater(after['A']['elo'], before['A']['elo'])
        self.assertAlmostEqual(after['A']['elo'] + after['B']['elo'], before['A']['elo'] + before['B']['elo'])
        self.assertEqual(after['A']['youth_elo'], 1500)
        adult = after['A']['elo']
        self.book.settle_match('m2', 'A', 'B', 'B', '2006-01-02', kind='youth_singles')
        latest = self.book.snapshot()['players']
        self.assertEqual(latest['A']['elo'], adult)
        self.assertLess(latest['A']['youth_elo'], 1500)

    def test_duplicate_match_invalid_winner_date_and_nan_are_atomic(self):
        self.book.settle_match('used', 'A', 'B', 'A', '2006-01-01')
        invalid = [dict(match_id='used'), dict(winner_id='unknown'), dict(date='2006-02-30'),
            dict(date='20060102'), dict(a_id='A', b_id='A'), dict(importance=float('nan')),
            dict(kind='team'), dict(date='2005-01-01')]
        for changes in invalid:
            kwargs = dict(match_id='new', a_id='A', b_id='B', winner_id='A', date='2006-01-02')
            kwargs.update(changes); before = self.book.snapshot()
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.book.settle_match(**kwargs)
            self.assertEqual(self.book.snapshot(), before)

    def test_events_settle_once_per_player_not_once_per_match_or_every_player(self):
        self.book.record_event('A', 'EVENT', '2006-01-01', 'pro_tour_open', 'champion')
        self.book.record_event('B', 'EVENT', '2006-01-01', 'pro_tour_open', 'runner_up')
        before = self.book.snapshot()
        with self.assertRaises(ValueError):
            self.book.record_event('A', 'EVENT', '2006-01-01', 'pro_tour_open', 'champion')
        self.assertEqual(self.book.snapshot(), before)
        self.assertEqual(self.book.world_ranking('2006-01-02', ['A', 'B'])['standings'][0]['S_PTS'], 400)

    def test_conflicting_event_identity_and_invalid_finish_are_atomic(self):
        self.book.record_event('A', 'EVENT', '2006-01-01', 'pro_tour_open', 'champion')
        for kwargs in [dict(date='2006-01-02'), dict(level='world_cup'), dict(kind='team'),
                       dict(finish='made_up'), dict(qualifier_wins=-1), dict(qualifier_wins=True)]:
            args = dict(player_id='B', event_id='EVENT', date='2006-01-01', level='pro_tour_open', finish='runner_up')
            args.update(kwargs); before = self.book.snapshot()
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.book.record_event(**args)
            self.assertEqual(self.book.snapshot(), before)

    def test_youth_and_team_events_do_not_enter_adult_points(self):
        self.book.record_event('A', 'YOUTH', '2006-01-01', 'pro_tour_open', 'champion', kind='youth_singles')
        self.book.record_event('A', 'TEAM', '2006-01-02', 'world_championships', 'champion', kind='team')
        rows = self.book.world_ranking('2006-01-03', ['A'])['standings']
        self.assertEqual(rows[0]['S_PTS'], 0)

    def test_best_eight_365_day_window_qualifier_and_future_rules(self):
        for i in range(10):
            self.book.record_event('A', f'event-{i}', f'2006-01-{i+1:02}', 'pro_tour_open', 'champion')
        self.book.record_event('A', 'future', '2007-06-01', 'olympics', 'champion')
        self.assertEqual(self.book.world_ranking('2006-01-11', ['A'])['standings'][0]['S_PTS'], 3200)
        self.assertEqual(self.book.world_ranking('2007-01-11', ['A'])['standings'][0]['S_PTS'], 0)
        self.book.record_event('B', 'qual', '2006-01-01', 'pro_tour_open', 'qualifier_only', qualifier_wins=2)
        self.assertEqual(self.book.world_ranking('2006-01-02', ['B'])['standings'][0]['S_PTS'], 4.4)

    def test_world_rank_requires_explicit_complete_eligible_pool(self):
        partial = self.book.world_ranking('2006-01-01', ['A', 'B'])
        self.assertEqual(partial['scope'], 'SAMPLE_ONLY')
        self.assertIn('sample_rank', partial['standings'][0])
        self.assertNotIn('world_rank', partial['standings'][0])
        complete = self.book.world_ranking('2006-01-01', ['A', 'B'], complete_pool=True)
        self.assertIn('world_rank', complete['standings'][0])
        for args in [dict(eligible_ids=['A', 'A']), dict(eligible_ids=['unknown']), dict(eligible_ids=[]), dict(eligible_ids=['A'], complete_pool=1)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.book.world_ranking('2006-01-01', **args)

    def test_ranking_asof_does_not_use_future_match_elo(self):
        self.book.settle_match('future', 'A', 'B', 'A', '2007-01-01')
        historical = self.book.world_ranking('2006-01-01', ['A', 'B'])['standings']
        self.assertEqual(next(p['elo'] for p in historical if p['player_id'] == 'A'), 1500)
        self.assertEqual(next(p['elo'] for p in historical if p['player_id'] == 'B'), 1540)
        current = self.book.world_ranking('2007-01-01', ['A', 'B'])['standings']
        self.assertGreater(next(p['elo'] for p in current if p['player_id'] == 'A'), 1500)

    def test_restored_points_and_duplicate_ledger_tampering_are_rejected(self):
        self.book.record_event('A', 'event', '2006-01-01', 'pro_tour_open', 'champion')
        damaged = self.book.snapshot()
        damaged['players']['A']['results'][0]['points'] = 9999
        with self.assertRaises(ValueError):
            Card.RankingBook.from_snapshot(damaged)
        damaged = self.book.snapshot()
        damaged['players']['A']['team_points'] = copy.deepcopy(damaged['players']['A']['results'])
        with self.assertRaises(ValueError):
            Card.RankingBook.from_snapshot(damaged)

    def test_snapshot_roundtrip_preserves_dedupe_and_is_deep_copy(self):
        self.book.settle_match('m1', 'A', 'B', 'A', '2006-01-01')
        self.book.record_event('A', 'e1', '2006-01-01', 'pro_tour_open', 'quarterfinal')
        saved = self.book.snapshot()
        restored = Card.RankingBook.from_snapshot(json.loads(json.dumps(saved)))
        self.assertEqual(restored.snapshot(), self.book.snapshot())
        saved['players']['A']['elo'] = 0
        self.assertNotEqual(self.book.snapshot()['players']['A']['elo'], 0)
        with self.assertRaises(ValueError):
            restored.settle_match('m1', 'A', 'B', 'A', '2006-01-02')
        with self.assertRaises(ValueError):
            restored.record_event('A', 'e1', '2006-01-01', 'pro_tour_open', 'quarterfinal')


if __name__ == '__main__':
    unittest.main()
