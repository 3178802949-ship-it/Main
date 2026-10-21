"""New-rule stress experiment; not historical CA or population calibration."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Card
import Training
from common import ROOT, SCHEMA
import career_v114 as fixtures
import career_v116 as career
from card_training_v112 import compute_card


def fixture(label):
    if label == 'Ma':
        return Card.make_ma18()
    if label == 'Elite':
        base = fixtures.ordinary_card(SCHEMA)
    else:
        profiles = json.loads((ROOT / 'data/original/spin_era_players_archive_2000_2026_v12.json').read_text())['profiles']
        base = fixtures.age18_card(profiles, SCHEMA, 'fan_zhendong', (2012, 2016), 2015, [194, 199])
    state = career.start(base, 1165000)
    profile = dict(body_max=state['P_max'], talent=state['talent'], neuromotor=state['neuromotor'],
        mental=state['mental'], focus=state['focus'], body_maturation_rate=state['body_maturation_rate'])
    base.update(age_approx=18, classification='SIMULATED')
    return Card.normalize(base, development_profile=profile)


def run_one(task):
    label, strategy, seed = task
    state = Training.initialize(fixture(label), seed=seed, curve='foundation_builder' if label == 'Ma' else 'balanced_progress')
    initial = compute_card(state, SCHEMA)['CA_calculated']
    state['yearly'].append(dict(age=18, CA=initial, PA=state['PA']))
    exceptional = coach_permits = specialized = rests = 0
    fatigue_peak = state['fatigue']
    groups = list(SCHEMA['core_order'])
    for month in range(240):
        for phase in range(2):
            if strategy == 'managed_specialization' and state['fatigue'] > 55:
                plan = dict(month=month, phase=phase, mode='rest')
                rests += 1
            else:
                chosen = [groups[(month * 2 + phase) % 9], groups[(month * 2 + phase + 4) % 9]]
                selections = []
                for group in chosen:
                    selection = dict(group=group)
                    if strategy != 'general_categories':
                        selection['specialize'] = sorted(SCHEMA['subskill_weights_pct'][group],
                            key=lambda k: (state['children'][group][k], k))[:2]
                        specialized += 1
                    selections.append(selection)
                plan = dict(month=month, phase=phase, technical=selections,
                    body=list(state['P6'])[(month + phase) % 6], mode='train')
            receipt = Training.settle_phase(state, plan, career.environment('national'),
                f'stress:{seed}:{month}:{phase}', record=False)
            exceptional += sum(x['exceptional'] for x in receipt['general'])
            coach_permits += sum(x.get('coach_permit', 0) for x in receipt['general'])
            fatigue_peak = max(fatigue_peak, receipt['fatigue']['peak'])
            assert 0 <= state['fatigue'] <= 100
            assert receipt['budget']['focused_technical'] in (0, 4)
            assert all(0 <= v <= 150 for sub in state['children'].values() for v in sub.values())
            assert all(x >= -1e-8 for x in state['xp'].values())
    q = state['yearly']
    return dict(label=label, strategy=strategy, seed=seed, initial_CA=initial,
        peak_CA=max(x['CA'] for x in q), CA38=q[-1]['CA'], end_PA=state['PA'],
        fatigue_end=state['fatigue'], fatigue_peak=fatigue_peak, rest_phases=rests,
        specialization_groups=specialized, general_excellence=exceptional,
        coached_permits=coach_permits, annual=q)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, default=8)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    tasks = [(label, strategy, seed) for label in ('Ma', 'Fan', 'Elite')
        for strategy in ('general_categories', 'constant_specialization', 'managed_specialization')
        for seed in range(1165001, 1165001 + args.seeds)]
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, row in enumerate(pool.map(run_one, tasks), 1):
            rows.append(row)
            if i % 9 == 0:
                print(f'{i}/{len(tasks)} careers', flush=True)
    summary = {}
    for label in ('Ma', 'Fan', 'Elite'):
        summary[label] = {}
        for strategy in ('general_categories', 'constant_specialization', 'managed_specialization'):
            selected = [r for r in rows if r['label'] == label and r['strategy'] == strategy]
            summary[label][strategy] = dict(n=len(selected),
                mean_peak_CA=round(statistics.mean(r['peak_CA'] for r in selected), 2),
                peak_range=[min(r['peak_CA'] for r in selected), max(r['peak_CA'] for r in selected)],
                mean_CA38=round(statistics.mean(r['CA38'] for r in selected), 2),
                mean_end_fatigue=round(statistics.mean(r['fatigue_end'] for r in selected), 2),
                mean_rest_phases=round(statistics.mean(r['rest_phases'] for r in selected), 2),
                mean_general_excellence=round(statistics.mean(r['general_excellence'] for r in selected), 2))
    report = dict(version=Training.VERSION, status='STRESS_ONLY_NOT_HISTORICAL_CALIBRATION',
        careers=len(rows), age_range=[18, 38], phases_per_career=480,
        training_sha256=hashlib.sha256((ROOT / 'Training/__init__.py').read_bytes()).hexdigest(),
        summary=summary, results=rows)
    (ROOT / 'reports/TRAINING_STRESS.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
