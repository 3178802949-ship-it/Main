"""Predeclared strategy contrasts; outcomes are observations, never fit targets.

The same synthetic abilities/body/equipment face each consecutive seed under
adaptive and forced plans. Forced plans are stress controls, not recommended
universal tactics. Old HGR is a separate-rule reference, not a matched stream
of point events. No historical athlete outcome is an optimization target.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Card
from common import canonical_json
from Game import engine_v117 as engine
from Game import specialist_engine as old
from Game import tactics_v117 as plans
import specialist_rubber_v116 as rubber

BASE_SEED = 11763000


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def card(pid, *, style='attacker', rubbers=None):
    item = Card.make_ma18()
    item.update(player_id=pid, name_zh='同值专项策略实验卡', style=style, hand='right',
                source_prototype='SYNTHETIC_NOT_HISTORICAL',
                rubbers=rubbers or dict(fh='inverted', bh='inverted'))
    item['children'] = {g: dict.fromkeys(sub, 124) for g, sub in item['children'].items()}
    return Card.recompute(item)


def fixtures():
    return {
        'chopper': dict(card=card('v117_bench_chopper', style='modern_chopper',
                                  rubbers=dict(fh='inverted', bh='long_pips')),
                        variants=('adaptive', 'chop_heavy', 'chop_float', 'chop_counter')),
        'short_pips': dict(card=card('v117_bench_short', rubbers=dict(fh='short_pips', bh='raw_pips')),
                          variants=('adaptive', 'pips_early_pressure', 'pips_block_redirect', 'pips_change_rhythm')),
        'long_pips': dict(card=card('v117_bench_long', rubbers=dict(fh='long_pips', bh='long_pips')),
                         variants=('adaptive', 'long_pips_reverse_hold', 'long_pips_float', 'long_pips_flat_finish')),
    }


def _contact_probe(action, path, increment=1.):
    wing = path.split('.')[0]
    if wing not in ('fh', 'bh'):
        raise ValueError('probe needs a stroke path')
    base = card('v117_probe', rubbers=dict(fh='short_pips', bh='short_pips') if '_sp_' in action else None)
    changed = copy.deepcopy(base)
    changed['children'][wing][path.split('.')[1]] += increment
    changed = Card.recompute(changed)
    incoming = dict(spin='back' if action.endswith('sp_under_attack') else 'top',
                    pace=125, quality=125, length='long', landed=wing)
    assert rubber.legal_action(action, rubber.rubber_for(base, wing), incoming, 'good')
    result = []
    for current in (base, changed):
        state = engine.core.warmup(current, engine.core.rng_of('v117-probe'), 25)
        state['g_roll'] = dict.fromkeys(state['g_roll'], 0)
        q, pace, _ = engine._quality(current, state, incoming,
            'good', action, engine.core.rng_of('v117-probe-quality'), 4, False, wing)
        result.append(dict(quality=q, pace=pace, contact_skill=state['v117_contact_skill'],
                           technique_error_adjustment=engine.technical_error_adjustment(state['v117_contact_skill'])))
    return dict(action=action, path=path, increment=increment, incoming=incoming,
                rubber=rubber.rubber_for(base, wing), legal_contact=True,
                before=result[0], after=result[1],
                quality_delta=round(result[1]['quality'] - result[0]['quality'], 6),
                error_probability_delta=round(result[1]['technique_error_adjustment'] - result[0]['technique_error_adjustment'], 8))


def _row(match, seed, player=1):
    shots = [s for game in match['games'] for point in game['points'] for s in point['shots']]
    own = [s for s in shots if s.get('player') == player and s.get('technique_path')]
    families = Counter(s.get('action_family', rubber.action_spec(s['action'])['family']) for s in own)
    n = len(own)
    return dict(seed=seed, winner=match['winner'], games_won=match['games_won'],
        mean_strokes=match['mean_strokes'], contacts=n,
        errors=sum(s.get('return_state') == 'direct_point_lost' for s in own),
        family_counts=dict(families), action_counts=dict(Counter(s['action'] for s in own)),
        plan_counts=dict(Counter(s['specialist_plan'] for s in own if s.get('specialist_plan'))),
        spin_counts=dict(Counter(s['spin'] for s in own)),
        arc_counts=dict(Counter(s.get('arc', s.get('spin_contact', {}).get('arc', 'unknown')) for s in own)),
        mean_quality=round(statistics.mean(s.get('out_quality', s.get('quality')) for s in own), 4) if own else None,
        mean_spin_strength=round(statistics.mean(s['spin_strength'] for s in own), 4) if own else None,
        near_table_contact_share=round(sum(abs(s['movement']['contact']['y']) <= 1.12 for s in own) / n, 5) if n else None,
        workload=match.get('workload', {}).get('per_player', [None, None])[player],
        result_sha256=hashlib.sha256(canonical_json(match).encode()).hexdigest())


def _aggregate(rows):
    def counts(key):
        total = Counter()
        for row in rows:
            total.update(row[key])
        return dict(total)
    n = sum(row['contacts'] for row in rows)
    families = counts('family_counts')
    return dict(matches=len(rows), specialist_wins=sum(row['winner'] == 1 for row in rows),
        attacker_wins=sum(row['winner'] == 0 for row in rows),
        mean_strokes=round(statistics.mean(row['mean_strokes'] for row in rows), 4),
        contacts=n, errors=sum(row['errors'] for row in rows),
        error_per_contact=round(sum(row['errors'] for row in rows) / n, 5) if n else None,
        offensive_contact_share=round(sum(families.get(f, 0) for f in ('attack', 'counter', 'open', 'slow_loop', 'flip')) / n, 5) if n else None,
        mean_quality=round(statistics.mean(row['mean_quality'] for row in rows if row['mean_quality'] is not None), 4),
        mean_spin_strength=round(statistics.mean(row['mean_spin_strength'] for row in rows if row['mean_spin_strength'] is not None), 4),
        mean_near_table_contact_share=round(statistics.mean(row['near_table_contact_share'] for row in rows if row['near_table_contact_share'] is not None), 5),
        families=families, actions=counts('action_counts'), plans=counts('plan_counts'),
        spins=counts('spin_counts'), arcs=counts('arc_counts'))


def run(count=12, output=None):
    if type(count) is not int or count < 1:
        raise ValueError('positive integer count required')
    output = Path(output or ROOT / 'reports/v117/tactics_benchmark')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('output must be empty; retain prior experiment evidence')
    inputs = fixtures()
    opponent = card('v117_bench_attacker')
    sources = [Path(engine.__file__), Path(plans.__file__), Path(old.__file__), Path(rubber.__file__),
               Path(engine.core.__file__), Path(engine.observed.__file__), Path(__file__)]
    source_hash = {p.relative_to(ROOT).as_posix(): sha(p) for p in sources}
    seed_plan = {name: list(range(BASE_SEED + i * 1000, BASE_SEED + i * 1000 + count)) for i, name in enumerate(inputs)}
    plan = dict(version=engine.TAG, seeds=seed_plan, cards=inputs, opponent=opponent,
                source_sha256=source_hash, selection='CONSECUTIVE_PREDECLARED_SEEDS_NO_WINNER_TARGET',
                interpretation='Synthetic same-value controls; force-one-plan variants stress choices rather than optimize wins.')
    (output / 'PREDECLARED_PLAN.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    before = canonical_json((inputs, opponent))
    rows, summary = {}, {}
    for name, data in inputs.items():
        rows[name], summary[name] = {}, {}
        for variant in ('HGR_reference',) + data['variants']:
            player = copy.deepcopy(data['card'])
            if variant != 'HGR_reference':
                player['tactical_plan'] = variant
            runner = old if variant == 'HGR_reference' else engine
            rows[name][variant] = []
            for seed in seed_plan[name]:
                match = runner.play_match([opponent, player], seed, keep_points=True)
                rows[name][variant].append(_row(match, seed))
            summary[name][variant] = _aggregate(rows[name][variant])
            print(name, variant, 'wins', summary[name][variant]['specialist_wins'],
                  'mean_strokes', summary[name][variant]['mean_strokes'], flush=True)
    assert before == canonical_json((inputs, opponent))
    final_hash = {p.relative_to(ROOT).as_posix(): sha(p) for p in sources}
    assert source_hash == final_hash, 'sources changed during the predeclared experiment'
    probes = [_contact_probe(action, path) for action, path in (
        ('fh_fast_loop', 'fh.power'), ('bh_counter_loop', 'bh.continuity'),
        ('fh_chop', 'fh.defense'), ('fh_chop', 'fh.spin'),
        ('fh_sp_under_attack', 'fh.power'), ('fh_sp_under_attack', 'fh.spin'))]
    report = dict(version=engine.TAG, status='EXECUTED_STRATEGY_STRESS_NOT_BALANCE_CERTIFICATION',
        total_matches=sum(len(m) for case in rows.values() for m in case.values()),
        seeds_per_variant=count, summary=summary, matches=rows, contact_sensitivity=probes,
        inputs_preserved=True, sources_preserved=True, source_sha256=source_hash,
        limitations=[
            'Same seed across algorithms does not align point-by-point random events.',
            'Selected-contact mean quality is not a causal estimate; contact_sensitivity holds noise/context fixed.',
            'Forced plans can choose unsuitable preparation and actions; they are stress controls.',
            'Synthetic equal skills do not encode genuine specialist expertise or establish historical win rates.',
            'Spin/arc coefficients are transparent approximations; empirical point-by-point calibration remains open.'])
    (output / 'TACTICS_BENCHMARK.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    lines = ['# V1.1.7 详细比赛：专项策略固定种子实验', '',
        f'实际完成 {report["total_matches"]} 场 BO7；每组每种策略 {count} 个连续预登记种子。', '',
        '三组使用相同124技术子值、相同身体与右手，仅显式改变打法／胶皮／策略。历史球员胜率没有被设为调参目标。', '',
        '|专项|策略|专项胜场|平均板数|主动进攻接触占比|失误/实际接触|近台接触占比|',
        '|---|---|---:|---:|---:|---:|---:|']
    for name, variants in summary.items():
        for variant, row in variants.items():
            lines.append(f'|{name}|{variant}|{row["specialist_wins"]}/{count}|{row["mean_strokes"]}|{row["offensive_contact_share"]}|{row["error_per_contact"]}|{row["mean_near_table_contact_share"]}|')
    lines += ['', '削球的重削／不转／牵制／近台抢反攻改变准备深度、动作分布及实际出球，不叠加G或额外击质倍率。短颗粒侧重抢点、弹击、快挡与节奏；长胶侧重借转、拱刮、减转和条件性低摩擦反攻。', '',
        '定向探针在同来球、同到位、同噪声下增加1点技术，分别检查质量和执行失误概率，详见 JSON 的 contact_sensitivity。', '',
        '这是机制及极端策略检查，不是职业球员胜率校准。每组样本较小，强制策略也不能代表真实选手；新旧规则使用不同随机事件流。胶皮物理、回合长度和整体平衡仍需后续实证校准。', '']
    (output / 'TACTICS_BENCHMARK_ZH.md').write_text('\n'.join(lines))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=12)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    run(args.count, args.output)
