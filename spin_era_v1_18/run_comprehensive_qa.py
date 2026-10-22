"""Run public behavior tests and a fresh reproducible cross-module career demo.

Long model experiments are separate evidence, not silently rerun or selected
here. Output is excluded from the immutable package manifest.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from simulator import WorldSession as Dispatcher, RULESET, ruleset_fingerprint


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error('output must be empty; earlier QA evidence is preserved')
    out.mkdir(parents=True, exist_ok=True)
    tested = subprocess.run([sys.executable, 'self_test.py'], cwd=ROOT, text=True, capture_output=True)
    (out / 'TESTS.txt').write_text(tested.stdout + tested.stderr, encoding='utf-8')
    if tested.returncode:
        print((tested.stdout + tested.stderr)[-9000:])
        raise SystemExit(tested.returncode)
    match = re.search(r'Ran (\d+) tests?', tested.stdout + tested.stderr)
    if not match:
        raise ValueError('test count missing')
    for name in ('fresh_a', 'fresh_b'):
        run = subprocess.run([sys.executable, 'examples/start_comprehensive.py', '--output', str(out / name),
            '--demo', '--full-match'], cwd=ROOT, text=True, capture_output=True)
        (out / f'{name}.txt').write_text(run.stdout + run.stderr, encoding='utf-8')
        if run.returncode:
            print(run.stdout + run.stderr)
            raise SystemExit(run.returncode)
    demo_a, demo_b = out / 'fresh_a', out / 'fresh_b'
    exact = all(digest(demo_a / name) == digest(demo_b / name) for name in (
        'START_WORLD_COMPREHENSIVE.json', 'COMPLETE_CARD_COMPREHENSIVE.json', 'DEMO_WORLD_COMPREHENSIVE.json', 'DEMO_CARD_COMPREHENSIVE.json', 'NARRATIVE_EXAMPLES.json'))
    if not exact:
        raise ValueError('fresh seeded demos differ')
    shipped = ROOT / 'examples/comprehensive_demo_output'
    shipped_exact = all(digest(shipped / name) == digest(demo_a / name)
        for name in ('START_WORLD_COMPREHENSIVE.json', 'COMPLETE_CARD_COMPREHENSIVE.json',
                     'DEMO_WORLD_COMPREHENSIVE.json', 'DEMO_CARD_COMPREHENSIVE.json', 'NARRATIVE_EXAMPLES.json'))
    if not shipped_exact:
        raise ValueError('shipped starting checkpoint/card differs from fresh execution')
    saved = (demo_a / 'DEMO_WORLD_COMPREHENSIVE.json').read_text()
    loaded = Dispatcher.load(saved)
    if loaded.dump() != saved:
        raise ValueError('dispatcher checkpoint roundtrip differs')
    # Full artifacts are deliberately outside the mutable career checkpoint.
    if loaded.artifacts or any('points' in g for log in loaded.data['matches'].values() for g in log['games']):
        raise ValueError('checkpoint contains detailed shot histories')
    report = dict(version=RULESET, status='FUNCTIONAL_QA_PASSED',
        tests=int(match[1]), fresh_seeded_demo_exact=True, checkpoint_roundtrip_exact=True,
        shipped_start_and_card_exact=shipped_exact, shipped_demo_and_narrative_exact=shipped_exact,
        ruleset_fingerprint=ruleset_fingerprint(),
        no_full_logs_in_checkpoint=True, demo_checkpoint_bytes=len(saved.encode()),
        source_sha256={p.relative_to(ROOT).as_posix(): digest(p)
            for p in sorted(ROOT.rglob('*.py')) if not {'checks', 'saves', '__pycache__'}.intersection(p.relative_to(ROOT).parts)},
        note='Behavior checks do not certify historical accuracy, population rarity or full/light equivalence.')
    (out / 'COMPREHENSIVE_QA.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'source_sha256'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
