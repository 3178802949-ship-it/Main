"""Fixed-seed speed/size/trend comparison; light and full are not equivalent."""
from pathlib import Path
import argparse
from collections import Counter
import hashlib
import importlib
import json
import statistics
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import canonical_json
from Game import light_v117 as light
from examples.benchmark_specialist_patch import fixtures

BASE_SEED = 11792000


def _summary(rows):
    n = len(rows)
    return dict(matches=n, wins_A=sum(r['winner'] == 0 for r in rows),
                wins_B=sum(r['winner'] == 1 for r in rows),
                mean_strokes=round(statistics.mean(r['mean_strokes'] for r in rows), 5),
                scorelines=dict(Counter(':'.join(map(str, r['games_won'])) for r in rows)),
                mean_seconds=round(statistics.mean(r['seconds'] for r in rows), 6),
                median_seconds=round(statistics.median(r['seconds'] for r in rows), 6),
                mean_bytes=round(statistics.mean(r['bytes'] for r in rows), 2))


def _one(fn, cards, seed, full):
    started = time.perf_counter()
    match = fn(cards, seed, fatigue=(25, 25), max_games=7, keep_points=full)
    seconds = time.perf_counter() - started
    body = canonical_json(match).encode()
    return dict(seed=seed, winner=match['winner'], games_won=match['games_won'],
                points=match['points'], mean_strokes=match['mean_strokes'],
                seconds=seconds, bytes=len(body), result_sha256=hashlib.sha256(body).hexdigest()), match


def run(count=16, output=None, detailed_module='Game.engine_v117', base_seed=BASE_SEED):
    if type(count) is not int or count < 1 or type(base_seed) is not int:
        raise ValueError('positive integer seed count required')
    output = Path(output or ROOT / 'reports/v117/light_benchmark')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('output must be empty; preserve earlier benchmark evidence')
    detailed = importlib.import_module(detailed_module)
    sources = [Path(light.__file__), Path(detailed.__file__), Path(light.plans.__file__),
               Path(light.observed_tactics.__file__), Path(light.geo.__file__),
               Path(light.rubbers.__file__), Path(light.core.__file__), Path(__file__)]
    fingerprint = lambda: {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    source_start = fingerprint()
    inputs = fixtures()
    case_cards = inputs['cards']
    before = canonical_json(case_cards)
    plan = dict(version=light.TAG, detailed_module=detailed_module,
                seeds={name: list(range(base_seed + i * 1000, base_seed + i * 1000 + count))
                       for i, name in enumerate(case_cards)},
                fixtures=inputs, source_sha256_start=source_start,
                selection='CONSECUTIVE_PREDECLARED_SEEDS_NO_WINNER_TARGET',
                comparison='DIRECT_IN_PROCESS_COMPUTATION; no subprocess/transport costs in either measurement',
                interpretation='Same seed does not mean identical random event streams or an accuracy target.')
    (output / 'PREDECLARED_PLAN.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    compact, summary = {}, {}
    for name, cards in case_cards.items():
        compact[name] = dict(light=[], detailed=[])
        for seed in plan['seeds'][name]:
            for variant, engine, full in (('light', light, False), ('detailed', detailed, True)):
                row, match = _one(engine.play_match, cards, seed, full)
                compact[name][variant].append(row)
                if seed == plan['seeds'][name][0]:
                    (output / f'{name}_{variant}_sample.json').write_text(json.dumps(match, ensure_ascii=False, indent=2))
        old, new = compact[name]['detailed'], compact[name]['light']
        ds, ls = _summary(old), _summary(new)
        summary[name] = dict(detailed=ds, light=ls,
            absolute_win_fraction_difference=round(abs(ls['wins_A'] - ds['wins_A']) / count, 5),
            paired_winner_agreement=round(sum(x['winner'] == y['winner'] for x, y in zip(old, new)) / count, 5),
            runtime_ratio_full_over_light=round(ds['mean_seconds'] / ls['mean_seconds'], 3),
            byte_ratio_full_over_light=round(ds['mean_bytes'] / ls['mean_bytes'], 3))
        print(name, json.dumps(summary[name], ensure_ascii=False), flush=True)
    assert canonical_json(case_cards) == before
    # Peak allocations of one representative computation in the same process.
    memory = {}
    first_cards = next(iter(case_cards.values()))
    for variant, engine, full in (('light', light, False), ('detailed', detailed, True)):
        tracemalloc.start()
        engine.play_match(first_cards, base_seed, fatigue=(25, 25), max_games=7, keep_points=full)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory[variant] = peak
    source_end = fingerprint()
    if source_start != source_end:
        raise RuntimeError('source changed during benchmark; evidence is not a frozen-run report')
    report = dict(version=light.TAG, status='EXECUTED_NOT_EQUIVALENCE_CERTIFICATION',
        total_matches=count * len(case_cards) * 2, seeds_per_pair=count, summary=summary,
        matches=compact, memory_one_representative_match_peak_bytes=memory,
        source_sha256=source_end, source_sha256_start=source_start, source_sha256_end=source_end,
        sources_unchanged=True,
        inputs_preserved=True, conclusions=[
            'Light simulates exact scoring with an approximate point/contact-pair model.',
            'Rally length, technical exposures and movement are sampled aggregate estimates, not observed shot traces.',
            'Winner agreement is not an accuracy score because algorithms consume different random streams.',
            'A large systematic win-fraction shift is a calibration risk even when size/speed savings are substantial.',
            'No historical win rate is a target; Xu2013 context retains the explicit 2012 prior baseline.'])
    (output / 'LIGHT_BENCHMARK.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    lines = ['# V1.1.7 轻量／详细引擎对照', '',
             f'固定4组×{count}种子×2模式，共{report["total_matches"]}场BO7。两模式同卡同种子，算法不同，不要求相同赛果。', '',
             '| 对抗 | 详细A:B | 轻量A:B | 详细/轻量耗时比 | 详细/轻量字节比 |',
             '| --- | ---: | ---: | ---: | ---: |']
    for name, item in summary.items():
        ds, ls = item['detailed'], item['light']
        lines.append(f'| {inputs["labels"][name]} | {ds["wins_A"]}:{ds["wins_B"]} | {ls["wins_A"]}:{ls["wins_B"]} | '
                     f'{item["runtime_ratio_full_over_light"]:.1f}× | {item["byte_ratio_full_over_light"]:.1f}× |')
    lines.extend(['', '轻量没有逐板轨迹。技术曝光和移动负荷是明确标记的聚合抽样估计，仅支持趋势叙述。',
                  '测量均直接在同一进程调用，不含公开Game边界的子进程和传输开销；内存仅为一场代表计算，不是多年世界压测。',
                  '详细与轻量胜率差异需要作为校准风险报告，不能以性能提升替代行为一致性。'])
    (output / 'LIGHT_BENCHMARK_ZH.md').write_text('\n'.join(lines) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=int, default=16)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/v117/light_benchmark')
    parser.add_argument('--detailed-module', default='Game.engine_v117')
    parser.add_argument('--base-seed', type=int, default=BASE_SEED)
    args = parser.parse_args()
    run(args.seeds, args.output, args.detailed_module, args.base_seed)


if __name__ == '__main__':
    main()
