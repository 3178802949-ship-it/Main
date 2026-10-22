import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('event_context_safe_apply', HERE / 'apply_patch.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class SafeApplyTests(unittest.TestCase):
    def test_dry_run_default_apply_and_repeat(self):
        original = (HERE / 'ORIGINAL_world_extensions_v1_18.py').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'world_extensions_v1_18.py'
            target.write_bytes(original)
            self.assertEqual(helper.apply_to(directory)['status'], 'dry_run_valid')
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(helper.apply_to(directory, commit=True)['status'],
                             'applied_to_candidate')
            self.assertEqual(helper.apply_to(directory, commit=True)['status'],
                             'already_applied')
            backup = target.with_name(target.name + '.before_event_context_patch')
            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(target.read_bytes(), (HERE / target.name).read_bytes())

    def test_wrong_base_rejected_without_write(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'world_extensions_v1_18.py'
            target.write_text('different engine source')
            with self.assertRaisesRegex(ValueError, 'BASELINE_HASH_MISMATCH'):
                helper.apply_to(directory, commit=True)
            self.assertEqual(target.read_text(), 'different engine source')
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_known_original_directory_forbidden(self):
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_BASELINE_READ_ONLY'):
            helper.apply_to(helper.BASELINE, commit=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
