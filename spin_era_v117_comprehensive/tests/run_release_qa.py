"""Execute the integrated tests, fresh-demo replay and portable-state checks."""
from pathlib import Path
import argparse
import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from world import WorldSession
import Card
import Training


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'checks/release_qa',
                        help='Write new verification receipts separately from frozen release evidence')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test_*.py')
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (args.output / 'unittest_stdout.txt').write_text(stream.getvalue())
    print(stream.getvalue())
    if not result.wasSuccessful() or not result.testsRun:
        raise SystemExit(1)
    with tempfile.TemporaryDirectory(prefix='spin-era-release-qa-') as temp:
        subprocess.run([sys.executable, 'examples/start.py', '--demo', '--output', temp], cwd=ROOT,
                       capture_output=True, text=True, check=True)
        baseline = (ROOT / 'examples/demo_output/DEMO_WORLD.json').read_text()
        actual = (Path(temp) / 'DEMO_WORLD.json').read_text()
        if actual != baseline:
            raise AssertionError('fresh demo must exactly reproduce the shipped checkpoint')
    world = WorldSession.load(baseline)
    other = WorldSession.load(baseline)
    plan = dict(month=1, phase=0, mode='train', body='stamina',
                technical=[dict(group='read'), dict(group='bh')])
    a = world.train_phase('ma_long_age18', plan, 'qa-continuation')
    b = other.train_phase('ma_long_age18', plan, 'qa-continuation')
    assert a == b and world.dump() == other.dump()
    source = ROOT / 'data/original/spin_era_players_archive_2000_2026_v12.json'
    archive = json.loads(source.read_text())['profiles']
    presets = json.loads((ROOT / 'data/presets_normalized.json').read_text())['profiles']
    assert len(archive) == len(presets) == 370
    for raw, normalized in zip(archive, presets):
        assert raw['children'] == normalized['children'] and raw['P6'] == normalized['P6']
        assert raw['CA'] == normalized['CA']
    stress = json.loads((ROOT / 'reports/TRAINING_STRESS.json').read_text())
    assert stress['training_sha256'] == hashlib.sha256((ROOT / 'Training/__init__.py').read_bytes()).hexdigest()
    assert stress['careers'] == 72 and len(stress['results']) == 72
    game = json.loads((ROOT / 'reports/GAME_BENCHMARK.json').read_text())
    assert game['game_sha256'] == hashlib.sha256((ROOT / 'Game/__init__.py').read_bytes()).hexdigest()
    assert game['tactical_sha256'] == hashlib.sha256((ROOT / 'runtime/tactical_match_v116.py').read_bytes()).hexdigest()
    assert sum(row['matches'] for row in game['summary'].values()) == 100
    for name, matches in game['matches'].items():
        assert len(matches) == 50 and len({m['seed'] for m in matches}) == 50
        assert all(max(m['games_won']) == 4 for m in matches)
    report = dict(version='V1.1.6-MODULAR-INTEGRATION-CANDIDATE', status='FUNCTIONAL_CHECKS_PASSED',
        tests=dict(passed=result.testsRun, failed=len(result.failures) + len(result.errors), skipped=len(result.skipped)),
        fresh_demo_reproduced=True, checkpoint_continuation_exact=True, original_presets=370,
        preserved_43_subskills_and_P6=True, preserved_original_CA=True,
        game_BO7_matches=100, new_rule_training_careers=72, phases_per_career=480,
        complete_historical_calendar=False, population_rarity_calibrated=False,
        historical_197_198_potential_calibration='NOT_PASSED',
        full_NPC_automatic_careers=False, underlying_game_shared_process_safety=False,
        public_Game_process_isolation_verified=True, complete_real_world_ranking_pool=False,
        package_source_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for directory in ('Game', 'Card', 'Training', 'Area', 'common')
            for p in (ROOT / directory).glob('*.py')})
    (args.output / 'RELEASE_QA.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
