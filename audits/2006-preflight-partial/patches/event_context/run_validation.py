"""Rebuild a disposable candidate; leave the given baseline and its saves intact."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, cwd, output):
    value = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True)
    output.write_text(value.stdout + value.stderr)
    if value.returncode:
        raise RuntimeError(f'{args}:\n{value.stdout[-2000:]}\n{value.stderr[-4000:]}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--combined-draw-patch-dir', type=Path)
    parser.add_argument('--full-regression', action='store_true')
    args = parser.parse_args()
    baseline = args.baseline_engine.resolve()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('fresh output required')
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((HERE / 'PATCH_MANIFEST.json').read_text())
    if sha(baseline / manifest['base_file']) != manifest['base_sha256']:
        raise ValueError('BASELINE_HASH_MISMATCH')
    with tempfile.TemporaryDirectory(prefix='spin-era-event-patch-') as directory:
        candidate = Path(directory) / 'engine'
        shutil.copytree(baseline, candidate,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'checks', 'saves'))
        run([str(HERE / 'apply_patch.py'), '--candidate-engine', str(candidate), '--apply'],
            HERE, out / 'APPLY.txt')
        if args.combined_draw_patch_dir:
            draw = args.combined_draw_patch_dir.resolve()
            draw_manifest = json.loads((draw / 'PATCH_MANIFEST.json').read_text())
            target = candidate / draw_manifest['target']
            payload = draw / 'PATCHED_competition_v1_18.py'
            if sha(target) != draw_manifest['original_sha256'] or sha(payload) != draw_manifest['patched_sha256']:
                raise ValueError('DRAW_PATCH_HASH_MISMATCH')
            shutil.copy2(payload, target)
        run([str(HERE / 'test_apply_helper.py')], HERE, out / 'APPLY_HELPER_TESTS.txt')
        run([str(HERE / 'test_event_context.py'), str(candidate)], HERE,
            out / 'EVENT_CONTEXT_TESTS.txt')
        if args.full_regression:
            run(['self_test.py'], candidate, out / 'BASELINE_REGRESSION.txt')
    assert sha(baseline / manifest['base_file']) == manifest['base_sha256']
    print('Validation passed; disposable candidate removed, baseline untouched.')


if __name__ == '__main__':
    main()
