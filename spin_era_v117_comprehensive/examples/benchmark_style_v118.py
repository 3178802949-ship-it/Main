"""Predeclared style-overlay comparison; not a historical win-rate fit."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Card
from Game import v118 as Game
from Game import preferences_v118 as preference
from common import canonical_json

SOURCES = ('Game/v118.py', 'Game/worker_v118.py', 'Game/preferences_v118.py', 'Game/integration_v118.py',
    'Game/engine_v117.py', 'Game/light_v117.py', 'Game/tactics_v117.py', 'Game/specialist_engine.py',
    'runtime/specialist_rubber_v116.py', 'runtime/game_v112.py', 'runtime/game_v115.py',
    'runtime/tactical_match_v116.py', 'examples/benchmark_style_v118.py')


def fingerprint():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def fixtures():
    result = {}
    for case, style, material in (
            ('two_wings_right_left', 'attacker', 'inverted'),
            ('weak_fh_strong_bh', 'attacker', 'inverted'),
            ('chopper_long_pips', 'modern_chopper', 'long_pips'),
            ('raw_pips_rhythm', 'attacker', 'raw_pips')):
        pair = []
        for i in (0, 1):
            c = Card.make_ma18()
            c.update(player_id=f'{case}_{i}', source_prototype='SYNTHETIC', hand='right' if i == 0 else 'left',
                style=style if i == 0 else 'attacker', rubbers=dict(fh='inverted', bh=material if i == 0 else 'inverted'))
            c['children'] = {group: dict.fromkeys(subs, 125) for group, subs in c['children'].items()}
            c['P6'] = dict.fromkeys(c['P6'], 125)
            if case == 'weak_fh_strong_bh' and i == 0:
                c['children']['fh'] = dict.fromkeys(c['children']['fh'], 112)
                c['children']['bh'] = dict.fromkeys(c['children']['bh'], 140)
            pair.append(Card.recompute(c))
        result[case] = pair
    return result


def declaration(case, variant):
    axes = dict.fromkeys(preference.AXES, .5)
    if variant == 'preferred_means':
        if case == 'chopper_long_pips':
            axes.update(backspin_control=.9, counterattack=.7, risk=.25, initiative=.3)
        elif case == 'raw_pips_rhythm':
            axes.update(initiative=.8, backhand_use=.9, forehand_use=.2, risk=.65)
        else:
            axes.update(initiative=.8, forehand_use=.9, backhand_use=.2, risk=.65)
    return dict(version=preference.STYLE_VERSION, axes=axes)


def summary(rows):
    result = {}
    for case in sorted({r['case'] for r in rows}):
        result[case] = {}
        for mode in ('summary', 'full'):
            result[case][mode] = {}
            for variant in ('neutral', 'preferred_means'):
                picked = [r for r in rows if r['case'] == case and r['mode'] == mode and r['variant'] == variant]
                result[case][mode][variant] = dict(n=len(picked), wins_A=sum(r['winner'] == 0 for r in picked),
                    mean_strokes=round(statistics.mean(r['mean_strokes'] for r in picked), 5),
                    mean_fh_skill_exposure_share=round(statistics.mean(r['fh_skill_exposure_share'] for r in picked), 5),
                    mean_seconds=round(statistics.mean(r['seconds'] for r in picked), 6),
                    weighted_pool_calls=sum(r['audit']['weighted_calls'] for r in picked),
                    min_multiplier=min(r['audit']['min_multiplier'] for r in picked),
                    max_multiplier=max(r['audit']['max_multiplier'] for r in picked))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seeds', type=int, default=8)
    args = parser.parse_args()
    if args.seeds < 1 or args.output.exists() and any(args.output.iterdir()):
        parser.error('choose positive seed count and an empty new output directory')
    args.output.mkdir(parents=True, exist_ok=True)
    inputs = fixtures()
    before = canonical_json(inputs)
    fingerprints = fingerprint()
    plan = dict(version=Game.RULESET, cases=inputs,
        seeds={case: list(range(11841001 + i * 1000, 11841001 + i * 1000 + args.seeds)) for i, case in enumerate(inputs)},
        variants=['neutral', 'preferred_means'], modes=['summary', 'full'],
        selection='CONSECUTIVE_PREDECLARED_SEEDS_NO_WINNER_TARGET', source_sha256=fingerprints,
        intent='Choice sensitivity, lawful contacts, immutable attributes; no historical winner targets or specialist calibration claim.')
    (args.output / 'PREDECLARED_PLAN.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    rows = []
    for case, cards in inputs.items():
        for seed in plan['seeds'][case]:
            for mode in plan['modes']:
                for variant in plan['variants']:
                    pair = copy.deepcopy(cards)
                    pair[0]['style_profile'] = declaration(case, variant)
                    pair[1]['style_profile'] = declaration(case, 'neutral')
                    tick = time.perf_counter()
                    match = Game.play_match(pair, seed, f'{case}:{seed}:{mode}:{variant}', detail_level=mode)
                    seconds = time.perf_counter() - tick
                    exposure = match['exposure_by_player'][0]['usage']
                    fh = sum(n for p, n in exposure.items() if p.startswith('fh.'))
                    bh = sum(n for p, n in exposure.items() if p.startswith('bh.'))
                    rows.append(dict(case=case, mode=mode, variant=variant, seed=seed,
                        winner=match['winner'], games_won=match['games_won'], points=match['points'],
                        mean_strokes=match['mean_strokes'], fh_skill_exposure_share=fh / max(1, fh + bh),
                        seconds=seconds, audit=match['style_preference_audit'][0], log_sha256=match['log_sha256']))
        print(f'{case}: {args.seeds * 4} matches', flush=True)
    assert canonical_json(inputs) == before
    assert fingerprint() == fingerprints, 'source changed during the experiment'
    report = dict(version=Game.RULESET, status='EXECUTED_PREFERENCE_SENSITIVITY_NOT_BALANCE_CERTIFICATION',
        matches=len(rows), seeds_per_case=args.seeds, source_sha256=fingerprints,
        inputs_unchanged=True, source_unchanged=True, summary=summary(rows), results=rows,
        limitations=['Small synthetic samples cannot determine historical playing-style prevalence or win rates.',
            'Full and summary remain different algorithms; specialist summary calibration remains unpassed.',
            'Exposure share is selected skill exposure, not a count of observed forehand strokes in summary mode.',
            'A preferred but weaker wing is not awarded skill; no monotone winner benefit is claimed.'])
    (args.output / 'GAME_STYLE_BENCHMARK.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
