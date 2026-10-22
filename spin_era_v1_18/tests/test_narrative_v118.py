"""Narration cannot silently turn aggregate data or character cues into facts."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

import Card
import Game
from Area import v117 as Area
from common import ROOT, canonical_json
import narrative_v118 as narrative


def resign(value):
    value.pop('log_sha256', None)
    value['log_sha256'] = hashlib.sha256(canonical_json(value).encode()).hexdigest()
    return value


class Narrative118Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        a = Card.make_ma18()
        b = copy.deepcopy(a)
        b['player_id'] = 'narrative_peer'
        b['name_zh'] = '原创陪练'
        cls.cards = [a, b]
        cls.full = Game.play_match(cls.cards, 118601, 'narrative118-full',
            ruleset=Game.V117_RULESET, detail_level='full')
        cls.summary = Game.play_match(cls.cards, 118602, 'narrative118-summary', ruleset=Game.V117_RULESET)
        cls.compact = Game.compact_log(cls.full)
        cls.receipt = json.loads((ROOT / 'examples/v117_demo_output/DEMO_SUMMARY_V117.json').read_text())['receipts'][0]

    def test_summary_renders_only_scores_and_sourced_trends(self):
        before = canonical_json(self.summary)
        result = narrative.render_match(self.summary, self.cards, seed=1)
        self.assertEqual(result['narrative_scope'], 'AGGREGATE_ONLY')
        self.assertIn('聚合估计', result['text'])
        self.assertNotIn('逐板记录中', result['text'])
        self.assertNotIn('executed_shot', [f['id'] for f in result['facts']])
        self.assertEqual(result['profile_guidance'], [])
        self.assertTrue(narrative.verify_evidence(result, dict(match=self.summary, cards=self.cards)))
        self.assertEqual(before, canonical_json(self.summary))

    def test_full_excerpt_is_an_actual_logged_action_with_score_before(self):
        result = narrative.render_match(self.full, seed=2)
        self.assertEqual(result['narrative_scope'], 'EXECUTED_SHOTS_ONLY')
        self.assertIn('逐板记录中', result['text'])
        self.assertTrue(narrative.verify_evidence(result, dict(match=self.full)))
        excerpt = next(f for f in result['facts'] if f['id'] == 'executed_shot')
        self.assertNotIn(excerpt['value']['action'], ('serve', 'unreached'))
        self.assertTrue(result['evidence'][excerpt['evidence_refs'][0]]['path'].startswith('$.games['))

    def test_compacted_full_log_does_not_authorize_lost_chronology(self):
        result = narrative.render_match(self.compact)
        self.assertEqual(result['narrative_scope'], 'AGGREGATE_ONLY')
        self.assertNotIn('逐板记录中', result['text'])
        self.assertIn('FULL_ARTIFACT_NOT_ATTACHED_RESULT_AND_TRENDS_ONLY', result['warnings'])

    def test_attached_full_artifact_requires_exact_hash_and_identity(self):
        result = narrative.render_match(self.compact, detail_artifact=self.full)
        self.assertEqual(result['narrative_scope'], 'EXECUTED_SHOTS_ONLY')
        self.assertTrue(narrative.verify_evidence(result, dict(match=self.compact, detail=self.full)))
        bad = copy.deepcopy(self.full)
        bad['match_id'] = 'different-match'
        resign(bad)
        with self.assertRaisesRegex(ValueError, 'ARTIFACT'):
            narrative.render_match(self.compact, detail_artifact=bad)

    def test_foreign_cards_and_content_tampering_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'participant order'):
            narrative.render_match(self.summary, list(reversed(self.cards)))
        changed = copy.deepcopy(self.summary)
        changed['winner'] = 1 - changed['winner']
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            narrative.render_match(changed)

    def test_duplicate_display_names_remain_distinct_participants(self):
        cards = copy.deepcopy(self.cards)
        cards[1]['name_zh'] = cards[0]['name_zh']
        result = narrative.render_match(self.summary, cards)
        labels = result['participant_display_labels']
        self.assertEqual(labels, [
            f"{card['name_zh']}[{side}:{card['player_id']}]"
            for side, card in zip(('A', 'B'), cards)
        ])
        # A result template may mention only the winner; that mention must
        # still identify the participating card unambiguously.
        self.assertIn(labels[self.summary['winner']], result['text'])
        self.assertTrue(narrative.verify_evidence(result, dict(match=self.summary, cards=cards)))

    def test_resigned_illegal_score_or_summary_chronology_is_rejected(self):
        bad = copy.deepcopy(self.summary)
        bad['games'][0]['score'] = [11, 10]
        with self.assertRaisesRegex(ValueError, 'illegal'):
            narrative.render_match(resign(bad))
        bad = copy.deepcopy(self.summary)
        bad['games'][0]['points'] = self.full['games'][0]['points']
        with self.assertRaisesRegex(ValueError, 'chronology'):
            narrative.render_match(resign(bad))

    def test_complete_match_stops_at_legal_terminal_game_and_winning_target(self):
        bad = copy.deepcopy(self.summary)
        winner = bad['games'][0]['winner']
        bad['games'][0]['score'][winner] = 14
        bad['games'][0]['score'][1-winner] = 10
        with self.assertRaisesRegex(ValueError, 'illegal'):
            narrative.render_match(resign(bad))
        bad = copy.deepcopy(self.summary)
        target = bad['games_won'][bad['winner']]
        win_game = dict(score=[11, 0], winner=0)
        lose_game = dict(score=[0, 11], winner=1)
        bad.update(winner=0, games_won=[target, 1], games=[copy.deepcopy(win_game) for _ in range(target)] + [lose_game])
        bad['points'] = sum(sum(g['score']) for g in bad['games'])
        with self.assertRaisesRegex(ValueError, 'continued after'):
            narrative.render_match(resign(bad))

    def test_future_or_wrong_era_is_withheld(self):
        future = Area.get_era(2024)
        result = narrative.render_match(self.summary, era=future, as_of_year=2006)
        self.assertIn('ERA_CONTEXT_OUTSIDE_OBSERVATION_DATE_WITHHELD', result['warnings'])
        self.assertNotIn(future['theme_zh'], result['text'])
        undated = narrative.render_match(self.summary, era=Area.get_era(2006))
        self.assertIn('ERA_WITHHELD_WITHOUT_OBSERVATION_YEAR', undated['warnings'])

    def test_current_era_is_a_sourced_design_context_not_historical_proof(self):
        era = Area.get_era(2006)
        result = narrative.render_match(self.summary, era=era, as_of_year=2006)
        self.assertIn('本世界采用的时代主题', result['text'])
        fact = next(f for f in result['facts'] if f['id'] == 'era_theme')
        self.assertEqual(fact['kind'], 'DESIGN_CONTEXT_NOT_HISTORICAL_PROOF')
        self.assertTrue(narrative.verify_evidence(result, dict(match=self.summary, era=era)))

    def test_nested_dated_area_context_has_day_precision_and_future_is_withheld(self):
        era = dict(as_of='2006-02-01', temporal_precision='DAY', era=Area.get_era(2006))
        result = narrative.render_match(self.summary, era=era, as_of_year=2006)
        self.assertIn('本世界采用的时代主题', result['text'])
        self.assertTrue(narrative.verify_evidence(result, dict(match=self.summary, era=era)))
        result = narrative.render_match(self.summary, era=era, as_of_year=2006, as_of_date='2006-01-01')
        self.assertIn('ERA_CONTEXT_OUTSIDE_OBSERVATION_DATE_WITHHELD', result['warnings'])
        with self.assertRaisesRegex(ValueError, 'year/date disagree'):
            narrative.render_match(self.summary, as_of_year=2006, as_of_date='2024-01-01')

    def test_reproducibility_variation_and_bounded_history(self):
        self.assertEqual(narrative.render_match(self.summary, seed=10), narrative.render_match(self.summary, seed=10))
        history, templates, previous = {}, set(), None
        for seed in range(60):
            before = copy.deepcopy(history)
            result = narrative.render_match(self.summary, seed=seed, history=history)
            self.assertEqual(history, before)
            self.assertNotEqual(result['template_id'], previous)
            previous = result['template_id']
            templates.add(previous)
            history = result['history']
            self.assertLessEqual(len(history['recent_templates']), narrative.HISTORY_LIMIT)
        self.assertGreaterEqual(len(templates), 6)

    def test_personality_never_becomes_result_causality_or_private_dialogue(self):
        cards = copy.deepcopy(self.cards)
        for card in cards:
            card['personality_profile'] = dict(secret='因为内向所以必胜', private_quote='不应出现的私下对话')
        result = narrative.render_match(self.summary, cards)
        for forbidden in ('因为内向所以必胜', '不应出现的私下对话', '他心想', '她心想'):
            self.assertNotIn(forbidden, result['text'])
        self.assertEqual(result['fictional_atmosphere']['text'], '')

    def test_profile_guidance_is_narrator_only_and_date_bounded(self):
        from Card import v118 as CurrentCard
        cards = [CurrentCard.prepare(card) for card in self.cards]
        era = dict(as_of='2006-02-01', temporal_precision='DAY', era=Area.get_era(2006))
        result = narrative.render_match(self.summary, cards, era=era, as_of_year=2006)
        self.assertEqual(len(result['profile_guidance']), 2)
        for profile in result['profile_guidance']:
            self.assertEqual(profile['visibility'], 'NARRATOR_ONLY')
            self.assertEqual(profile['guidance']['as_of_date'], '2006-02-01')
            for cue in profile['guidance']['personality_guidance']['simulation_traits']:
                self.assertNotIn(cue, result['text'])
        future = copy.deepcopy(cards)
        future[1]['snapshot_date'] = '2006-12-31'
        with self.assertRaisesRegex(ValueError, 'future card snapshot date'):
            narrative.render_match(self.summary, future, era=era, as_of_year=2006)

    def test_training_uses_actual_receipt_and_awards_nothing(self):
        before = canonical_json(self.receipt)
        result = narrative.render_training(self.receipt)
        self.assertEqual(result['narrative_scope'], 'SETTLED_RECEIPT_ONLY')
        self.assertFalse(result['settlement_performed'])
        self.assertTrue(narrative.verify_evidence(result, dict(training=self.receipt)))
        self.assertEqual(before, canonical_json(self.receipt))
        self.assertIn('4个子项', result['text'])

    def test_training_binding_and_external_receipt_hash_are_verified(self):
        bad = copy.deepcopy(self.receipt)
        bad['receipt']['CA_after'] += 1
        with self.assertRaisesRegex(ValueError, 'BINDING_MISMATCH'):
            narrative.render_training(bad)
        with self.assertRaisesRegex(ValueError, 'RECEIPT_HASH_MISMATCH'):
            narrative.render_training(self.receipt, expected_sha256='0' * 64)

    def test_rest_does_not_fabricate_breakthrough_or_champion_reward(self):
        result = narrative.render_training(dict(mode='rest', CA_before=160, CA_after=160, PA_after=190))
        self.assertIn('休整', result['text'])
        self.assertNotIn('突破', result['text'])
        self.assertNotIn('冠军', result['text'])
        self.assertTrue(narrative.verify_evidence(result, dict(training=dict(mode='rest', CA_before=160, CA_after=160, PA_after=190))))

    def test_evidence_content_edit_is_detected(self):
        result = narrative.render_match(self.summary)
        result['facts'][0]['value'] = ['fabricated', 'identities']
        with self.assertRaisesRegex(ValueError, 'EVIDENCE_MISMATCH'):
            narrative.verify_evidence(result, dict(match=self.summary))
        result = narrative.render_match(self.summary)
        winner = next(f for f in result['facts'] if f['id'] == 'winner')
        winner['value'] = bool(winner['value'])
        with self.assertRaisesRegex(ValueError, 'EVIDENCE_MISMATCH'):
            narrative.verify_evidence(result, dict(match=self.summary))


if __name__ == '__main__':
    unittest.main()
