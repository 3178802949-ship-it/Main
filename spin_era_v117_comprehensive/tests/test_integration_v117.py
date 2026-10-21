"""Public match boundary, real execution evidence and compact checkpoint contracts."""
import copy
import hashlib
import unittest

import Card
import Game
from common import canonical_json
from Training import v117 as Training


class IntegrationV117Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = Training.initialize(Card.make_ma18(), seed=117901)
        cls.cards = [Training.performance_card(cls.state) for _ in range(2)]
        cls.cards[0]['player_id'] = cls.state['id']
        cls.cards[1]['player_id'] = 'integration-v117-peer'
        cls.before = canonical_json(cls.cards)
        cls.full = Game.play_match(cls.cards, 117901, 'v117-real-full',
            ruleset=Game.V117_RULESET, detail_level='full')
        cls.light = Game.play_match(cls.cards, 117901, 'v117-real-summary',
            ruleset=Game.V117_RULESET)

    def test_public_default_is_actual_summary_without_shots(self):
        result = self.light
        self.assertEqual(result['mode'], 'summary')
        self.assertEqual(result['narrative_scope'], 'AGGREGATE_ONLY')
        self.assertTrue(Game.verify_log(result))
        self.assertTrue(all('points' not in g for g in result['games']))
        self.assertEqual(canonical_json(self.cards), self.before)
        self.assertEqual(sum(result['rally_length_distribution'].values()), result['points'])

    def test_full_exposure_assigns_exactly_one_path_per_executed_contact(self):
        counts = [0, 0]
        for game in self.full['games']:
            for point in game['points']:
                for shot in point['shots']:
                    if shot.get('player') in (0, 1) and shot.get('action') != 'unreached':
                        counts[shot['player']] += 1
        self.assertEqual([sum(r['usage'].values()) for r in self.full['exposure_by_player']], counts)
        self.assertEqual([r['contacts'] for r in self.full['fatigue_cost_evidence']['per_player']], counts)
        self.assertTrue(any(p.startswith('serve.') for p in self.full['exposure_by_player'][0]['usage']))
        self.assertEqual(self.full['narrative_scope'], 'EXECUTED_SHOTS_ONLY')
        self.assertFalse(self.full['fatigue_cost_evidence']['estimated'])

    def test_compact_receipt_preserves_scores_learning_load_and_full_hash(self):
        result = Game.compact_log(self.full)
        self.assertTrue(Game.verify_log(result))
        self.assertEqual(result['full_log_sha256'], self.full['log_sha256'])
        self.assertEqual(result['source_mode'], 'full')
        for key in ('games_won', 'winner', 'exposure_by_player', 'fatigue_cost_evidence'):
            self.assertEqual(result[key], self.full[key])
        self.assertTrue(all('points' not in g for g in result['games']))
        self.assertLess(len(canonical_json(result)), len(canonical_json(self.full)) / 20)
        self.assertEqual(Game.compact_log(result), result)

    def test_review_from_full_and_receipt_has_identical_technical_evidence(self):
        compact = Game.compact_log(self.full)
        a = Game.review_event(self.state, self.full, self.state['id'])
        b = Game.review_event(self.state, compact, self.state['id'])
        for key in ('paths', 'usage', 'pressure', 'challenge', 'simulation_detail'):
            self.assertEqual(a[key], b[key])
        self.assertEqual(a['source'], 'MATCH_LOG')
        self.assertLessEqual(len(a['paths']), 3)
        self.assertTrue(all(n >= 8 for n in a['usage'].values()))

    def test_hash_tamper_and_rehashed_forged_learning_path_are_rejected(self):
        bad = Game.compact_log(self.light)
        bad['winner'] = 1 - bad['winner']
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            Game.verify_log(bad)
        bad = Game.compact_log(self.light)
        bad['exposure_by_player'][0]['usage']['invented.super_technique'] = 100
        bad.pop('log_sha256')
        bad['log_sha256'] = hashlib.sha256(canonical_json(bad).encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'unregistered'):
            Game.review_event(self.state, bad, self.state['id'])
        with self.assertRaisesRegex(ValueError, 'participant'):
            Game.review_event(self.state, self.light, 'other-world-player')

    def test_short_formats_are_explicit_light_only(self):
        current_only = [{k: copy.deepcopy(c[k]) for k in ('player_id', 'children', 'P6', 'G9', 'CA')}
                        for c in self.cards]
        self.assertTrue(all('PA' not in c for c in current_only))
        result = Game.play_match(current_only, 117902, 'v117-bo3',
            ruleset=Game.V117_RULESET, max_games=3)
        self.assertEqual(max(result['games_won']), 2)
        with self.assertRaisesRegex(ValueError, 'BO7'):
            Game.play_match(self.cards, 117902, 'v117-full-bo3',
                ruleset=Game.V117_RULESET, max_games=3, detail_level='full')


if __name__ == '__main__':
    unittest.main()
