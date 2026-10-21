import copy
import json
from pathlib import Path
import unittest

from common import ROOT
import Game
import career_v116 as career


class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads((ROOT / 'data/presets_normalized.json').read_text())
        cls.a = data['starters']['ma18']
        cls.b = copy.deepcopy(cls.a)
        cls.b['player_id'] = 'synthetic-peer'
        cls.log = Game.play_match([cls.a, cls.b], 1164001, 'game-self-test')

    def test_bound_full_bo7_is_verified_and_does_not_mutate_inputs(self):
        self.assertEqual(max(self.log['games_won']), 4)
        self.assertTrue(self.log['isolated_process'])
        self.assertEqual(self.log['participant_ids'], [self.a['player_id'], 'synthetic-peer'])
        self.assertTrue(Game.verify_log(self.log))
        self.assertTrue(all('shots' in p for g in self.log['games'] for p in g['points']))
        self.assertEqual(self.a['CA'], 159)

    def test_stale_aggregate_and_duplicate_participant_rejected(self):
        invalid = copy.deepcopy(self.a)
        invalid['G9']['bh'] += 1
        with self.assertRaises(ValueError):
            Game.play_match([invalid, self.b], 1, 'invalid')
        with self.assertRaises(ValueError):
            Game.play_match([self.a, self.a], 1, 'invalid')

    def test_review_binds_actual_player_index_and_cannot_edit_match(self):
        state = career.start(self.a, 1164002, development_profile=self.a['development_profile'])
        event = Game.review_event(state, self.log, self.a['player_id'])
        self.assertEqual(event['participant_id'], state['id'])
        self.assertEqual(event['bound_match_sha256'], self.log['log_sha256'])
        with self.assertRaises(ValueError):
            Game.review_event(state, self.log, 'synthetic-peer')
        corrupted = copy.deepcopy(self.log)
        corrupted['games_won'][0] += 1
        with self.assertRaises(ValueError):
            Game.verify_log(corrupted)


if __name__ == '__main__':
    unittest.main()
