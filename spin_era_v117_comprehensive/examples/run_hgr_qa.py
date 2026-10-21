"""Actual tests, immutable-baseline checks and old/new checkpoint replay."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Game


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'checks/hgr_qa')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    tests = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test_*.py')
    stream = io.StringIO()
    result = unittest.TextTestRunner(verbosity=2, stream=stream).run(tests)
    (args.output / 'HGR_unittest_stdout.txt').write_text(stream.getvalue())
    print(stream.getvalue())
    if not result.wasSuccessful() or not result.testsRun or result.skipped:
        raise SystemExit('HGR QA requires actual successful tests, with no skips')
    frozen = json.loads((ROOT / 'reports/HGR_BASELINE_MANIFEST.json').read_text())
    protected = {name: digest for name, digest in frozen['files'].items()
        if name.startswith('data/') or name in ('Card/__init__.py', 'Training/__init__.py', 'Area/__init__.py')
        or name.startswith('runtime/') and name != 'runtime/career_v116.py'
        or name.startswith('examples/demo_output/') or name.startswith('reports/')}
    for name, digest in protected.items():
        if sha(ROOT / name) != digest:
            raise AssertionError(f'protected baseline differs: {name}')
    demos = [('examples/start.py', 'DEMO_WORLD.json', ROOT / 'examples/demo_output'),
             ('examples/start_hgr.py', 'DEMO_WORLD_HGR.json', ROOT / 'examples/hgr_demo_output')]
    for script, filename, baseline in demos:
        with tempfile.TemporaryDirectory(prefix='hgr-checkpoint-qa-') as temp:
            subprocess.run([sys.executable, script, '--demo', '--output', temp], cwd=ROOT,
                           capture_output=True, text=True, check=True)
            if (Path(temp) / filename).read_bytes() != (baseline / filename).read_bytes():
                raise AssertionError(f'fresh checkpoint differs: {filename}')
    regression = json.loads((ROOT / 'reports/hgr_patch/REGRESSION.json').read_text())
    assert regression['total_matches'] == 256 and regression['seeds_per_pair'] == 32
    assert regression['same_seed_and_card_pairing_verified']
    for name, digest in regression['source_sha256'].items():
        if sha(ROOT / name) != digest:
            raise AssertionError(f'regression code changed after benchmark: {name}')
    for name, variants in regression['summary'].items():
        assert variants['old']['matches'] == variants['new']['matches'] == 32
        assert sum(variants['new']['chop_direct_winners_by_player'].values()) == 0
    report = dict(version=Game.PATCH_RULESET, status='FUNCTIONAL_AND_MATCHED_REGRESSION_PASSED',
        tests=dict(passed=result.testsRun, failed=0, skipped=0),
        protected_baseline_files=len(protected), baseline_source_and_archive_bytes_preserved=True,
        legacy_fresh_demo_exact=True, patch_fresh_demo_exact=True,
        legacy_match_hash_and_training_continuation='ASSERTED_BY_COMPATIBILITY_TESTS',
        matched_seed_BO7_matches=256, independent_fixed_seeds_per_pair=32,
        regression_source_fingerprints_verified=True, direct_chop_winner_draws=0,
        historical_win_rates_calibrated=False, complete_2013_xu_snapshot_available=False,
        unknown_metadata_inferred=False, population_balance_certified=False,
        source_sha256={str(p.relative_to(ROOT)): sha(p) for p in sorted(
            list((ROOT / 'Game').glob('*.py')) + list((ROOT / 'runtime').glob('*.py'))
            + [ROOT / 'world.py', Path(__file__)])})
    (args.output / 'HGR_QA.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
