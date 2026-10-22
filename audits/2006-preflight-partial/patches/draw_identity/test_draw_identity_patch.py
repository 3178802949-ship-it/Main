from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest

BUNDLE = Path(__file__).resolve().parent
BASE = Path('/workspace/spin-era-v1_18-github/spin_era_v1_18')
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BUNDLE))
from apply_draw_identity_patch import apply


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


ORIGINAL = module(BUNDLE/'ORIGINAL_competition_v1_18.py', 'audit_original_competition')
PATCHED = module(BUNDLE/'PATCHED_competition_v1_18.py', 'audit_patched_competition')


class DrawIdentityTests(unittest.TestCase):
    def entries(self):
        return [dict(player_id='a', qualification_tier='q'),
                dict(player_id='b', qualification_tier='q'),
                dict(player_id='seed', qualification_tier='q', confirmed_seed=True)]

    def test_original_duplicate_is_reproduced(self):
        entries = self.entries()[:2]
        result = ORIGINAL.historical_replacement(entries, 'a', seed=0, qualification_tier='q')
        self.assertEqual([e['player_id'] for e in result['draw']], ['a', 'a'])

    def test_patch_rejects_existing_player_without_input_mutation(self):
        entries = self.entries()
        original = copy.deepcopy(entries)
        with self.assertRaisesRegex(ValueError, 'ALREADY_ENTERED'):
            PATCHED.historical_replacement(entries, 'a', seed=0, qualification_tier='q')
        self.assertEqual(entries, original)

    def test_valid_replacements_match_original_for_50_seeds(self):
        entries = self.entries()
        original = copy.deepcopy(entries)
        for seed in range(50):
            with self.subTest(seed=seed):
                a = ORIGINAL.historical_replacement(entries, 'new', seed=seed, qualification_tier='q')
                b = PATCHED.historical_replacement(entries, 'new', seed=seed, qualification_tier='q')
                self.assertEqual(a, b)
                self.assertEqual(len({e['player_id'] for e in b['draw']}), len(entries))
                self.assertEqual(b['draw'][2], entries[2])
        self.assertEqual(entries, original)

    def test_malformed_incoming_identity_rejected(self):
        for identity in ('', ' ', None, 0, [], {}):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                PATCHED.historical_replacement(self.entries(), identity, seed=0, qualification_tier='q')

    def test_malformed_entry_identity_rejected(self):
        for entries in ([{}], [None], [dict(player_id='')], [dict(player_id=[])],
                        [dict(player_id='a'), dict(player_id='a')]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                PATCHED.historical_replacement(entries, 'new', seed=0, qualification_tier='q')

    def test_dry_run_apply_and_idempotence(self):
        with tempfile.TemporaryDirectory() as temp:
            engine = Path(temp)
            target = engine/'Game/competition_v1_18.py'
            target.parent.mkdir()
            original = (BUNDLE/'ORIGINAL_competition_v1_18.py').read_bytes()
            patched = (BUNDLE/'PATCHED_competition_v1_18.py').read_bytes()
            target.write_bytes(original)
            self.assertEqual(apply(engine)['status'], 'DRY_RUN_READY')
            self.assertEqual(target.read_bytes(), original)
            self.assertTrue(apply(engine, write=True)['written'])
            self.assertEqual(target.read_bytes(), patched)
            self.assertEqual(apply(engine, write=True)['status'], 'ALREADY_APPLIED')
            self.assertEqual(target.read_bytes(), patched)

    def test_wrong_base_rejected_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            engine = Path(temp)
            target = engine/'Game/competition_v1_18.py'
            target.parent.mkdir()
            damaged = (BUNDLE/'ORIGINAL_competition_v1_18.py').read_bytes()+b'\n# other version\n'
            target.write_bytes(damaged)
            with self.assertRaisesRegex(ValueError, 'BASELINE_SHA256_MISMATCH'):
                apply(engine, write=True)
            self.assertEqual(target.read_bytes(), damaged)

    def test_immutable_baseline_refused(self):
        before = hashlib.sha256((BASE/'Game/competition_v1_18.py').read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'IMMUTABLE_BASELINE_REFUSED'):
            apply(BASE, write=True)
        self.assertEqual(before, hashlib.sha256((BASE/'Game/competition_v1_18.py').read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main(verbosity=2)
