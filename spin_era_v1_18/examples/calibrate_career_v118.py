"""Predeclared growth alternatives and held-out career validation.

These are synthetic development-condition comparisons, not played historical
titles. Every opportunity carries SYNTHETIC provenance; no archive is written.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import argparse
import copy
import hashlib
import json
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Card
from Training import v118 as training
from common import SCHEMA
import career_v118 as career
import career_v116 as old
import career_v114 as fixtures

LABELS = ('ma2004', 'fan2012', 'zhang2004', 'ma18', 'elite181', 'elite165')


def fixture(label):
    if label == 'ma2004':
        return Card.get_preset('ma_long', 2004)
    if label == 'fan2012':
        return Card.get_preset('fan_zhendong', 2012)
    if label == 'zhang2004':
        return Card.get_preset('zhang_jike', 2004)
    if label == 'ma18':
        return Card.make_ma18()
    card = fixtures.ordinary_card(SCHEMA)
    if label == 'elite165':
        card.update(player_id='synthetic_elite_165', PA=165, pa_range=[162, 168])
    return Card.normalize(card)


def _events(state, month, phase):
    if phase or month < 12:
        return []
    paths = sorted(state['xp'], key=lambda p: (-state['learning_factor'][p], p))[:3]
    if month % 12 in (1, 7):
        return [dict(id=f'synthetic-champion:{month}', month=month, kind='champion',
            source='SYNTHETIC', evidence_ref=f'CONDITION_CONTROL_NOT_REAL_TITLE:{month}',
            paths=paths, usage=dict.fromkeys(paths, 12), challenge=.90, review_quality=.9)]
    if month % 3 == 0:
        return [dict(id=f'synthetic-review:{month}', month=month, kind='match_review',
            source='SYNTHETIC', evidence_ref=f'EXPOSURE_CONDITION_NOT_EXECUTED_MATCH:{month}',
            paths=paths, usage=dict.fromkeys(paths, 16), challenge=.85, review_quality=.9)]
    return []


def run_one(task):
    label, strategy, seed, curve, environment = task[:5]
    condition = task[5] if len(task) > 5 else 'ideal'
    card = fixture(label)
    state = training.initialize(card, seed=seed, curve=curve, config=strategy)
    initial = career.performance_card(state)
    model = state['career_v118']
    initial_caps = dict(model['latent_technical_caps'])
    initial_pa = state['PA']
    target = model['latent_target']
    state['yearly'].append(dict(age=state['start_age'], CA=initial['CA'], learned_CA=initial['learned_CA'],
        PA=state['PA'], pa_range=list(state['pa_range']), G9=initial['G9'], P6=dict(state['P6']),
        children=copy.deepcopy(state['children']), effective_children=initial['children'], fatigue=state['fatigue'], injuries=0, remaining_body_envelope=initial['remaining_body_envelope'],
        latent_target=target, potential_damage_total=0))
    groups = list(SCHEMA['core_order'])
    rests = 0
    budget = 0.
    for month in range(round((40 - state['start_age']) * 12)):
        for phase in range(2):
            if condition == 'overload_injury':
                state['fatigue'] = min(100, state['fatigue'] + 8)
                if phase == 0 and month == round((24 - state['start_age']) * 12):
                    career.injury(state, 'SYNTHETIC_STRESS_INJURY', month, severity=3)
            if phase == 0 and condition in ('minor_injury', 'major_injury') and month == round((24 - state['start_age']) * 12):
                career.injury(state, 'SYNTHETIC_SEVERITY_CONTRAST', month,
                    affected=tuple(state['P6']), severity=2 if condition == 'minor_injury' else 5)
            if state['fatigue'] > 62 or state['month'] < state.get('rehab_until', 0) and phase == 1:
                plan = dict(month=month, phase=phase, mode='rest', recovery_fraction=.9)
                rests += 1
            else:
                selected = [groups[(month * 2 + phase) % 9], groups[(month * 2 + phase + 4) % 9]]
                plan = dict(month=month, phase=phase, mode='train', training_fraction=.90, recovery_fraction=.90,
                    technical=[dict(group=g) for g in selected], body=list(state['P6'])[(month + phase) % 6])
                if condition == 'low_investment':
                    plan.update(training_fraction=.40, recovery_fraction=.75)
                elif condition == 'mixed_investment':
                    plan.update(training_fraction=.80, recovery_fraction=.80)
            events = _events(state, month, phase)
            if condition in ('low_investment', 'overload_injury'):
                events = [e for e in events if e['kind'] != 'champion']
            actual_environment = 'national' if condition == 'mixed_investment' and month % 12 < 6 else 'club' if condition == 'mixed_investment' else environment
            # Internal in-place runner is used only for disposable calibration
            # states. Public settle_phase keeps its transaction boundary.
            receipt = training._settle(state, plan, old.environment(actual_environment), f'cal:{month}:{phase}', events, False)
            budget += receipt['fatigue']['cost']
    annual = state['yearly']
    best = max(annual, key=lambda x: x['CA'])
    peak = best['CA']
    peak_age = min(x['age'] for x in annual if x['CA'] == peak)
    plateau_end = max(x['age'] for x in annual if x['CA'] == peak)
    at38 = min(annual, key=lambda x: abs(x['age'] - 38))
    final = career.performance_card(state)
    initial_flat = {f'{g}.{k}': v for g, sub in card['children'].items() for k, v in sub.items()}
    best_flat = {f'{g}.{k}': v for g, sub in best['children'].items() for k, v in sub.items()}
    return dict(label=label, strategy=strategy, seed=seed, curve=curve, environment=environment, condition=condition,
        start_age=state['start_age'], initial_CA=initial['CA'], source_PA=card['PA'], initial_PA=initial_pa,
        latent_target=target, estimated_envelope=model['reachable_envelope'], peak_CA=peak,
        peak_age=peak_age, peak_plateau_end=plateau_end, peak_plateau_span=plateau_end - peak_age,
        peak_PA=best['PA'], gap_to_source_PA=card['PA'] - peak,
        gap_to_latent=target - peak, gap_to_peak_PA=best['PA'] - peak,
        within_ten_latent=abs(target - peak) <= 10, CA38=at38['CA'], CA40=final['CA'],
        end_PA=state['PA'], end_latent_target=model['latent_target'],
        end_remaining_body_envelope=final['remaining_body_envelope'],
        potential_damage_total=model['potential_damage_total'],
        PA_decrease_years=[dict(age=b['age'], before=a['PA'], after=b['PA']) for a,b in zip(annual, annual[1:]) if b['PA']<a['PA']],
        injury_receipts=[r for r in state['event_registry'].values() if r['kind'] in ('major_injury','temporary_injury')],
        rests=rests, fatigue_end=state['fatigue'], injuries=state['injuries'],
        body_limitations_40=len(final['body_limitations']), opportunity_windows=state['audit']['LEARNING_WINDOWS'],
        XP_balance_40=round(sum(state['xp'].values()), 4), permit_balance_40=sum(state['permits'].values()),
        body_XP_balance_40=round(sum(state['P_xp'].values()), 4),
        development_budget_cost=budget, phase_receipts_retained=len(state['training_release']['phase_log']),
        appraisal_max_annual_change=max(abs(b['PA'] - a['PA']) for a, b in zip(annual, annual[1:])),
        appraisal_range_max_width=max(x['pa_range'][1] - x['pa_range'][0] for x in annual),
        gained_by_path={p: round(best_flat[p] - initial_flat[p], 4) for p in initial_flat},
        initial_caps=initial_caps, annual=annual)


def summary(rows):
    result = {}
    for strategy in sorted({r['strategy'] for r in rows}):
        result[strategy] = {}
        for label in sorted({r['label'] for r in rows}):
            selected = [r for r in rows if r['strategy'] == strategy and r['label'] == label]
            if not selected:
                continue
            result[strategy][label] = dict(n=len(selected), mean_peak_CA=round(statistics.mean(r['peak_CA'] for r in selected), 3),
                mean_peak_age=round(statistics.mean(r['peak_age'] for r in selected), 3),
                mean_peak_plateau_end=round(statistics.mean(r['peak_plateau_end'] for r in selected), 3),
                mean_peak_plateau_span=round(statistics.mean(r['peak_plateau_span'] for r in selected), 3),
                mean_CA38=round(statistics.mean(r['CA38'] for r in selected), 3),
                mean_gap_to_latent=round(statistics.mean(r['gap_to_latent'] for r in selected), 3),
                within_ten_rate=round(statistics.mean(r['within_ten_latent'] for r in selected), 3),
                peak_range=[min(r['peak_CA'] for r in selected), max(r['peak_CA'] for r in selected)],
                peak_age_range=[min(r['peak_age'] for r in selected), max(r['peak_age'] for r in selected)])
    return result


def aggregate(rows):
    return dict(n=len(rows), all_fixture_mean_peak_age=round(statistics.mean(r['peak_age'] for r in rows), 4),
        peak_after31=sum(r['peak_age'] > 31 for r in rows),
        within_ten_rate=round(statistics.mean(r['within_ten_latent'] for r in rows), 4),
        mean_peak_CA=round(statistics.mean(r['peak_CA'] for r in rows), 4),
        mean_peak_to38_loss=round(statistics.mean(r['peak_CA'] - r['CA38'] for r in rows), 4),
        max_annual_PA_revision=max(r['appraisal_max_annual_change'] for r in rows),
        max_PA_range_width=max(r['appraisal_range_max_width'] for r in rows))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seeds', type=int, default=4)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--holdout', action='store_true')
    parser.add_argument('--strategy', choices=list(career.CONFIGS))
    parser.add_argument('--injury-contrast', action='store_true')
    parser.add_argument('--matrix', action='store_true', help='five priors, club/national, ma18+ordinary: stress conditions')
    parser.add_argument('--stress', action='store_true', help='mixed investment, low investment, overload+fixed test injury')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('preserve existing evidence; choose a fresh output file')
    seeds = list(range(11818101 if args.holdout else 11818001, (11818101 if args.holdout else 11818001) + args.seeds))
    strategies = [args.strategy] if args.strategy else list(career.CONFIGS)
    tasks = [(label, strategy, seed, 'foundation_builder' if label in ('ma2004', 'ma18') else 'balanced_progress', 'national')
             for strategy in strategies for label in LABELS for seed in seeds]
    if args.matrix:
        tasks = [(label, strategy, seed, curve, environment)
                 for strategy in strategies for label in ('ma18', 'elite181') for seed in seeds
                 for curve in career.CURVES for environment in ('club', 'national')]
    if args.stress:
        if args.matrix:
            raise ValueError('choose matrix or stress')
        tasks = [(label, strategy, seed, 'balanced_progress', 'club', condition)
                 for strategy in strategies for label in ('ma18', 'elite181') for seed in seeds
                 for condition in ('mixed_investment', 'low_investment', 'overload_injury')]
    if args.injury_contrast:
        if args.matrix or args.stress:
            raise ValueError('injury contrast must be a separate predeclared experiment')
        tasks = [(label, strategy, seed, 'balanced_progress', 'national', condition)
                 for strategy in strategies for label in ('ma18', 'elite181') for seed in seeds
                 for condition in ('minor_injury', 'major_injury')]
    condition_note = ('Synthetic stress: 0.80 availability with 6 national/6 club months each year; '
        '0.40 training in club; or club plus +8 fatigue/phase and one fixed severity3 injury at age24. '
        'Low/overload have no champion opportunities; all evidence SYNTHETIC, not actual wins.') if args.stress else (
        '0.90 training/recovery availability, no injuries; five growth priors x club/national, ma18+ordinary; '
        'all opportunities SYNTHETIC.') if args.matrix else (
        '0.90 training/recovery availability, rotate all groups, no injuries, national environment; '
        'all opportunities SYNTHETIC and not actual titles.')
    if args.injury_contrast:
        condition_note = 'National training; one synthetic severity2 transient or severity5 all-body persistent injury at age24, not medical prognosis. All opportunities SYNTHETIC.'
    plan = dict(version=career.VERSION, seed_selection='CONSECUTIVE_PREDECLARED_HOLDOUT' if args.holdout else 'CONSECUTIVE_PREDECLARED_DEVELOPMENT',
        seeds=seeds, scenarios=len(tasks), labels=LABELS, strategies=strategies, matrix=args.matrix, stress=args.stress, injury_contrast=args.injury_contrast,
        condition=condition_note,
        source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            ROOT / 'runtime/career_v118.py', ROOT / 'Training/v118.py', Path(__file__))},
        note='Abstract age-conditioned careers, not a world calendar past the 2028 cutoff; all opportunities SYNTHETIC, not wins.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix('.plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for index, row in enumerate(pool.map(run_one, tasks), 1):
            rows.append(row)
            if index % 6 == 0:
                print(f'{index}/{len(tasks)} careers', flush=True)
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest for name,digest in plan['source_sha256'].items()), 'source changed while running'
    report = dict(**plan, status='EXECUTED_NOT_HISTORICAL_CALIBRATION', summary=summary(rows),
                  aggregate_by_strategy={strategy: aggregate([r for r in rows if r['strategy'] == strategy]) for strategy in strategies}, results=rows)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
