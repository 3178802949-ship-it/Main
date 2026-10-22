"""Independent cross-module checks for the comprehensive release boundary.

Fixtures below are synthetic; the source cue is not a real interview.
"""
import copy
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Card import v118 as Card
from Game import v118 as Game
from Area import v118 as Area
import narrative_v118 as narrative
from world_v118 import WorldSession


def synthetic_cards():
    result = []
    for i in range(2):
        card = copy.deepcopy(Card.make_ma18())
        card.update(player_id=f'comprehensive_fixture_{i}',
            preset_id=f'comprehensive_fixture_{i}@2006',
            source_prototype='SYNTHETIC', origin='SYNTHETIC',
            year=2006, snapshot_date='2006-01-01', birth_year=1988,
            historical_reference={'champion_history': [], 'classification': 'NONE'})
        result.append(Card.normalize(card))
    return result


def plan(phase=0, *, rest=False):
    if rest:
        return dict(month=0, phase=phase, mode='rest')
    return dict(month=0, phase=phase, technical=[
        dict(group='read', specialize=['self_read', 'choice']),
        dict(group='bh', specialize=['defense', 'placement'])], body='stamina')


class ComprehensiveInvariants(unittest.TestCase):
    def new(self):
        return WorldSession.create(synthetic_cards(), 2006,
            start_date='2006-02-01', seed=118)

    def cue(self, when):
        return dict(source_id='SYNTHETIC_DATE_FIXTURE_NOT_REAL_INTERVIEW',
            source_url='https://example.invalid/synthetic-fixture',
            source_date=when, source_year=int(when[:4]),
            basis='PUBLIC_SELF_DESCRIPTION',
            verification_status='VERIFIED_PUBLIC_PRIMARY_SOURCE',
            text='SYNTHETIC_CUE_ONLY')

    def test_world_public_and_engine_views_exclude_persona_even_when_nested(self):
        world = self.new()
        pid = world.data['main_player_id']
        baseline = Game.match_card(world._match_card(pid))
        metadata = world.data['metadata'][pid]
        metadata['personality_profile']['simulation_traits'] = ['SYNTHETIC_SECRET_WORD']
        metadata['extra'] = dict(private_notes='SYNTHETIC_PRIVATE',
            nested=dict(personality_guidance='SYNTHETIC_PRIVATE', visible='kept'))
        public = world.card(pid)
        self.assertNotIn('personality_profile', public)
        self.assertNotIn('private_notes', public['extra'])
        self.assertEqual(public['extra']['nested'], {'visible': 'kept'})
        self.assertEqual(Game.match_card(world._match_card(pid)), baseline)
        self.assertNotIn('PA', baseline)
        self.assertNotIn('extra', baseline)
        guidance = world.narrative_profile(pid)['personality_guidance']
        self.assertEqual(guidance['simulation_traits'], ['SYNTHETIC_SECRET_WORD'])
        self.assertTrue(guidance['not_match_modifiers'])

    def test_world_profile_and_old_match_use_exact_source_dates(self):
        world = self.new()
        pid = world.data['main_player_id']
        profile = world.data['metadata'][pid]['personality_profile']
        profile['public_cues'] = [self.cue('2006-02-02')]
        self.assertEqual(world.narrative_profile(pid)['personality_guidance']['public_cues'], [])
        world.play_practice(*world.data['players'], 'dated:first', 118601)
        first = world.narrate_match('dated:first')
        self.assertEqual(first['profile_guidance'][0]['guidance']['as_of_date'], '2006-02-01')
        self.assertEqual(first['profile_guidance'][0]['guidance']['personality_guidance']['public_cues'], [])
        world.play_practice(*world.data['players'], 'dated:second', 118602)
        self.assertEqual(world.data['current_date'], '2006-02-02')
        self.assertEqual(len(world.narrative_profile(pid)['personality_guidance']['public_cues']), 1)
        old = world.narrate_match('dated:first')
        self.assertEqual(old['profile_guidance'][0]['guidance']['personality_guidance']['public_cues'], [])

    def test_match_and_training_narration_are_read_only_and_summary_has_no_shots(self):
        world = self.new()
        ids = list(world.data['players'])
        world.play_practice(*ids, 'readonly:match', 118603)
        before, artifacts = world.dump(), copy.deepcopy(world.artifacts)
        rendered = world.narrate_match('readonly:match', history={'recent_templates': [0]})
        self.assertEqual(world.dump(), before)
        self.assertEqual(world.artifacts, artifacts)
        self.assertEqual(rendered['narrative_scope'], 'AGGREGATE_ONLY')
        self.assertNotIn('executed_shot', [fact['id'] for fact in rendered['facts']])
        self.assertIn('聚合估计', rendered['text'])
        self.assertTrue(narrative.verify_evidence(rendered, {
            'match': world.data['matches']['readonly:match'],
            'cards': [world._private_card(p) for p in ids],
            'era': Area.context_for_date('2006-02-01')}))
        world.train_phase(ids[0], plan(), 'readonly:training')
        before, resources = world.dump(), copy.deepcopy(world.data['resources'])
        report = world.narrate_training('readonly:training')
        self.assertEqual(world.dump(), before)
        self.assertEqual(world.data['resources'], resources)
        self.assertIn('text', report)

    def test_duplicate_review_sources_and_reuse_do_not_spend_time_or_rewards(self):
        world = self.new()
        ids = list(world.data['players'])
        world.play_practice(*ids, 'review:one', 118604)
        before = world.dump()
        with self.assertRaisesRegex(ValueError, 'duplicate review source'):
            world.train_phase(ids[0], plan(), 'review:duplicate',
                review_match_ids=['review:one', 'review:one'])
        self.assertEqual(world.dump(), before)
        world.train_phase(ids[0], plan(), 'review:accepted', review_match_ids=['review:one'])
        world.train_phase(ids[1], plan(rest=True), 'review:peer')
        before = world.dump()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            world.train_phase(ids[0], plan(1), 'review:reused', review_match_ids=['review:one'])
        self.assertEqual(world.dump(), before)

    def test_same_year_future_snapshot_and_duplicate_source_person_are_rejected(self):
        cards = synthetic_cards()
        cards[0]['snapshot_date'] = '2006-02-02'
        with self.assertRaisesRegex(ValueError, 'future card'):
            WorldSession.create(cards, 2006, start_date='2006-02-01')
        cards = synthetic_cards()
        for card in cards:
            card.update(source_prototype='REAL_PERSON_FIXTURE', source_person_id='SAME_PERSON_FIXTURE')
        with self.assertRaisesRegex(ValueError, 'one contemporary card'):
            WorldSession.create(cards, 2006, start_date='2006-02-01')


if __name__ == '__main__':
    unittest.main()
