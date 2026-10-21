"""Frozen V1.1.6 contracts and explicit, opt-in HGR log exposure.

The continuation/log digests were executed against the original frozen release,
not generated from the implementation under test. Synthetic logs below exercise
only the exposure projector and never stand in for the match benchmarks.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import Card
import Game
import Training
from common import canonical_json
import career_v116 as career
from world import WorldSession, VERSION, PATCH_VERSION, PATCH_GAME_RULESET, LEGACY_GAME_RULESET


PROTECTED_FILES = {
    'runtime/game_v112.py': '2f75346f624d59638b5e1a7910c2982ac38fb9a6e2da025d752698c29c6b5581',
    'runtime/game_v113.py': '5cf588b85b625a1dbd29ddab6ce9c29b891243c215e9e8567103b8fa98355d66',
    'runtime/game_v114.py': '124122cd13a576eff5469c5dbe07ab156a118a9e2ba9564401464923012df910',
    'runtime/game_v115.py': '2a75d8bd5fda616908dab28ca915db15fa7dc763176475cc55a0520d69d3836d',
    'runtime/tactical_match_v116.py': '108745b40cbb3cceba561658ce6ac7b25e116fec57b2dbeaccd10d7b660cea0a',
    'runtime/card_training_v112.py': 'ea441a87493701ac078eecc74a42640e7f45e9abb06ac4321636697314f144f9',
    'Card/__init__.py': 'de0614af0039a6b0c4ad4559e90305ea8f0bc8f06e52f7f407d5175d39ee9b6c',
    'Training/__init__.py': '69d249d26781c34d254b07fa9fe6d60f7cdb84ef05a7374175ab397ecf9bf7d5',
    'data/presets_normalized.json': '8c535ac476a5e9e9bd265d34a838fa4f7bf886c95ee4218b4c479e7276e5ee4e',
}


def fresh_world(ruleset=None):
    return WorldSession.create([Card.make_ma18()], 2006, start_date='2006-02-01', game_ruleset=ruleset)


def synthetic_log(action='bh_lp_chop', path='bh.defense', count=8, ruleset=PATCH_GAME_RULESET):
    result = dict(seed=1168802, winner=0,
                  games=[dict(points=[dict(shots=[dict(player=0, action=action,
                      technique_path=path, reach='limited', fault_prob=.25) for _ in range(count)])])])
    if ruleset is not None:
        result['ruleset'] = ruleset
    return result


class PatchCompatibilityTests(unittest.TestCase):
    def test_protected_formulas_and_numeric_archive_are_byte_identical(self):
        for name, expected in PROTECTED_FILES.items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)

    def test_frozen_checkpoints_roundtrip_byte_for_byte(self):
        for name in ('START_WORLD.json', 'DEMO_WORLD.json'):
            with self.subTest(checkpoint=name):
                original = (ROOT / 'examples/demo_output' / name).read_text()
                world = WorldSession.load(original)
                self.assertEqual(world.dump(), original)
                self.assertEqual(world.data['version'], VERSION)
                self.assertNotIn('game_ruleset', world.data)

    def test_frozen_training_continuation_matches_original_executed_hashes(self):
        world = WorldSession.load((ROOT / 'examples/demo_output/DEMO_WORLD.json').read_text())
        plan = dict(month=1, phase=0, mode='train', body='stamina',
                    technical=[dict(group='read'), dict(group='bh')])
        receipt = world.train_phase('ma_long_age18', plan, 'patch-compat-continue')
        self.assertEqual(hashlib.sha256(world.dump().encode()).hexdigest(),
                         'df4784f674bf13bfc3eaccb12573c614009bdc3910be55640898ce188ade7c73')
        self.assertEqual(hashlib.sha256(canonical_json(receipt).encode()).hexdigest(),
                         '96d23bcf72a8733b613cb13fbb888bfdb364e9f23046082387e2a361cecec429')

    def test_default_and_explicit_legacy_create_have_original_shape(self):
        implicit = fresh_world()
        explicit = fresh_world(LEGACY_GAME_RULESET)
        self.assertEqual(implicit.dump(), explicit.dump())
        self.assertNotIn('game_ruleset', implicit.data)
        self.assertEqual(implicit.data['version'], VERSION)
        with self.assertRaisesRegex(ValueError, 'unknown game ruleset'):
            fresh_world('unversioned-new-engine')

    def test_actual_frozen_loader_rejects_new_format(self):
        fixture = ROOT / 'tests/fixtures/world_v116_frozen.py'
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(),
                         '100d2f77a65f1532254f2737dfa9514060927906f0efd668322fe01d5b5bc6d4')
        spec = importlib.util.spec_from_file_location('world_v116_frozen_compat_fixture', fixture)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        patched = fresh_world(PATCH_GAME_RULESET)
        self.assertEqual(patched.data['version'], PATCH_VERSION)
        with self.assertRaisesRegex(ValueError, 'migration'):
            module.WorldSession.load(patched.dump())
        self.assertEqual(WorldSession.load(patched.dump()).dump(), patched.dump())

    def test_ruleset_cannot_be_silently_mixed_or_upgraded(self):
        legacy = fresh_world()
        legacy.data['game_ruleset'] = PATCH_GAME_RULESET
        with self.assertRaisesRegex(ValueError, 'VERSION_MISMATCH'):
            legacy.consistency_check()
        patched = fresh_world(PATCH_GAME_RULESET)
        patched.data.pop('game_ruleset')
        with self.assertRaisesRegex(ValueError, 'VERSION_MISMATCH'):
            patched.consistency_check()
        wrapper = json.loads(fresh_world(PATCH_GAME_RULESET).dump())
        wrapper['payload']['game_ruleset'] = LEGACY_GAME_RULESET
        with self.assertRaisesRegex(ValueError, 'CHECKSUM'):
            WorldSession.load(json.dumps(wrapper))

    def test_legacy_match_full_hash_matches_original_execution(self):
        card = Card.make_ma18()
        peer = copy.deepcopy(card)
        peer['player_id'] = 'compat-peer'
        before = canonical_json([card, peer])
        result = Game.play_match([card, peer], 1168801, 'patch-compat-legacy')
        self.assertEqual(result['log_sha256'],
                         'ed2aaf4029a34bc245512fbdc1f742cb53ab436340521d7bb4d55c8c653a10b7')
        self.assertNotIn('ruleset', result)
        self.assertEqual(canonical_json([card, peer]), before)

    def test_registered_special_action_projects_existing_43_path_without_rewards(self):
        state = Training.initialize(Card.make_ma18(), seed=1168802)
        before = Training.dump_state(state)
        log = synthetic_log()
        event = career.event_from_match(state, log, 0, 'synthetic-exposure-unit-fixture')
        self.assertEqual(event['paths'], ['bh.defense'])
        self.assertEqual(event['usage'], {'bh.defense': 8})
        self.assertEqual(event['pressure'], {'bh.defense': 8})
        self.assertEqual(Training.dump_state(state), before)
        self.assertEqual(event['challenge'], 1)

    def test_exposure_still_requires_eight_and_selects_at_most_three_targets(self):
        state = Training.initialize(Card.make_ma18(), seed=1168803)
        with self.assertRaisesRegex(ValueError, 'adequately logged'):
            career.event_from_match(state, synthetic_log(count=7), 0, 'too-few-fixture')
        import game_v115 as legacy
        shots = []
        for path in ('fh.spin', 'bh.spin', 'table.push', 'bh.defense'):
            action = next(a for a, value in legacy.TECH.items() if value[0] == path)
            shots.extend(dict(player=0, action=action, technique_path=path,
                              reach='good', fault_prob=.1) for _ in range(8))
        log = dict(ruleset=PATCH_GAME_RULESET, seed=0, winner=0, games=[dict(points=[dict(shots=shots)])])
        event = career.event_from_match(state, log, 0, 'four-target-fixture')
        self.assertEqual(len(event['paths']), 3)
        self.assertEqual(set(event['usage'].values()), {8})

    def test_patch_exposure_rejects_forged_path_and_unregistered_action(self):
        state = Training.initialize(Card.make_ma18(), seed=1168804)
        for log in (synthetic_log(path='serve.spin'), synthetic_log(path=None),
                    synthetic_log(action='invented_winning_super_shot')):
            with self.subTest(action=log['games'][0]['points'][0]['shots'][0]):
                with self.assertRaises(ValueError):
                    career.event_from_match(state, log, 0, 'forged-exposure-fixture')

    def test_legacy_projection_retains_original_action_mapping(self):
        state = Training.initialize(Card.make_ma18(), seed=1168805)
        log = synthetic_log(action='chop', path='deliberately-ignored-legacy-metadata', ruleset=None)
        log['games'][0]['points'][0]['shots'] += synthetic_log()['games'][0]['points'][0]['shots']
        event = career.event_from_match(state, log, 0, 'legacy-exposure-fixture')
        self.assertEqual(event['paths'], ['table.chop_control'])
        self.assertEqual(event['usage'], {'table.chop_control': 8})

    def test_new_exposure_registers_once_through_unchanged_training_interface(self):
        state = Training.initialize(Card.make_ma18(), seed=1168806)
        control = copy.deepcopy(state)
        event = career.event_from_match(state, synthetic_log(), 0, 'synthetic-training-fixture')
        event.update(source='SYNTHETIC', evidence_ref='UNIT_FIXTURE_NOT_MATCH_EXECUTION')
        rest0 = dict(month=0, phase=0, mode='rest')
        env = career.environment('national')
        Training.settle_phase(state, rest0, env, 'rest-with-review', events=[event])
        Training.settle_phase(control, rest0, env, 'control-rest')
        for key in ('children', 'P6', 'PA', 'xp', 'permits', 'P_xp'):
            self.assertEqual(state[key], control[key])
        self.assertIn(event['id'], state['event_registry'])
        before = Training.dump_state(state)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_DEVELOPMENT_EVENT'):
            Training.settle_phase(state, dict(month=0, phase=1, mode='rest'), env,
                                  'duplicate-review-rest', events=[event])
        self.assertEqual(Training.dump_state(state), before)

    def test_real_patch_world_match_review_checkpoint_and_continuation(self):
        chopper = Card.make_ma18()
        chopper.update(player_id='hgr_compat_chopper', preset_id='hgr_compat_chopper@2006',
                       source_prototype='SYNTHETIC', origin='SYNTHETIC',
                       name_zh='兼容测试合成削球手', style='modern_chopper',
                       hand='right', grip='shakehand',
                       rubbers=dict(fh='inverted', bh='long_pips'))
        attacker = copy.deepcopy(chopper)
        attacker.update(player_id='hgr_compat_attacker', preset_id='hgr_compat_attacker@2006',
                        name_zh='兼容测试合成进攻手', style='attacker', hand='left',
                        rubbers=dict(fh='inverted', bh='inverted'))
        world = WorldSession.create([Card.normalize(chopper), Card.normalize(attacker)], 2006,
            start_date='2006-02-01', main_player_id=chopper['player_id'],
            world_id='hgr-compat-integration', seed=1168807, game_ruleset=PATCH_GAME_RULESET)
        original_traits = {pid: {key: copy.deepcopy(world.card(pid)[key])
                                 for key in ('children', 'P6', 'G9', 'CA', 'PA')}
                           for pid in world.data['players']}
        match_id = 'hgr-compat-real-practice'
        log = world.play_practice(chopper['player_id'], attacker['player_id'], match_id, 1168808)
        self.assertEqual(log['ruleset'], PATCH_GAME_RULESET)
        self.assertEqual(max(log['games_won']), 4)
        self.assertTrue(Game.verify_log(log))
        self.assertTrue(any(shot.get('action_family') == 'chop' and shot.get('technique_path')
                            for game in log['games'] for point in game['points'] for shot in point['shots']))
        self.assertEqual(world.data['ranking']['matches'], {})
        for pid, values in original_traits.items():
            for key, value in values.items():
                self.assertEqual(world.card(pid)[key], value)
        before_duplicate = world.dump()
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_WORLD_EVENT'):
            world.play_practice(chopper['player_id'], attacker['player_id'], match_id, 1168808)
        self.assertEqual(world.dump(), before_duplicate)
        plan = dict(month=0, phase=0, mode='train', body='stamina',
                    technical=[dict(group='read'), dict(group='bh')])
        world.train_phase(chopper['player_id'], plan, 'hgr-compat-phase0', review_match_ids=[match_id])
        review = world.data['players'][chopper['player_id']]['event_registry'][f'review:{match_id}:0']
        self.assertEqual(review['source'], 'MATCH_LOG')
        self.assertEqual(review['bound_match_sha256'], log['log_sha256'])
        self.assertTrue(all(count >= 8 for count in review['usage'].values()))
        checkpoint = world.dump()
        wrapper = json.loads(checkpoint)
        self.assertEqual(wrapper['format'], PATCH_VERSION)
        self.assertEqual(wrapper['payload']['game_ruleset'], PATCH_GAME_RULESET)
        restored = WorldSession.load(checkpoint)
        self.assertEqual(restored.dump(), checkpoint)
        self.assertEqual(restored.data['matches'][match_id]['ruleset'], PATCH_GAME_RULESET)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_WORLD_EVENT'):
            restored.train_phase(chopper['player_id'], plan, 'hgr-compat-phase0')
        self.assertEqual(restored.dump(), checkpoint)
        next_plan = dict(month=0, phase=1, mode='train', body='agility',
                         technical=[dict(group='read'), dict(group='bh')])
        a = world.train_phase(chopper['player_id'], next_plan, 'hgr-compat-phase1')
        b = restored.train_phase(chopper['player_id'], next_plan, 'hgr-compat-phase1')
        self.assertEqual(a, b)
        self.assertEqual(world.dump(), restored.dump())
        self.assertEqual(world.data['game_ruleset'], PATCH_GAME_RULESET)
        self.assertTrue(world.consistency_check()['valid'])


if __name__ == '__main__':
    unittest.main()
