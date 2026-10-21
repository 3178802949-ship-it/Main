"""100 isolated BO7 simulations; cross-year experimental pairings, not history."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Card
import Game


def main():
    joo = json.loads((ROOT / 'data/original/spin_era_v016_schlager2003_joo2003_cards.json').read_text())['joo']
    joo.update(player_id='joo_2003_experimental', name_zh='朱世赫2003独立削球实验卡', year=2003,
        age_approx=23, nation_prototype='韩国', style='modern_chopper', classification='ASSESSMENT',
        source_prototype='EXPERIMENTAL_NOT_REAL_ANNUAL_SNAPSHOT')
    pairs = dict(ma_fan=[Card.get_preset('ma_long', 2016), Card.get_preset('fan_zhendong', 2024)],
                 zhang_joo=[Card.get_preset('zhang_jike', 2012), Card.normalize(joo)])
    tasks = [(name, index) for name in pairs for index in range(50)]
    def run(task):
        name, index = task
        seed = 1166000 + (1000 if name == 'zhang_joo' else 0) + index
        log = Game.play_match(pairs[name], seed, f'benchmark:{name}:{seed}', world_id='benchmark-cross-year-sandbox')
        compact = {k: log[k] for k in ('seed', 'match_id', 'winner', 'games_won', 'points',
            'total_strokes', 'rallies', 'mean_strokes', 'actions', 'log_sha256')}
        return name, index, compact, log if index == 0 else None
    batches = {name: [] for name in pairs}
    samples = ROOT / 'reports/game_examples'
    samples.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, (name, index, compact, sample) in enumerate(pool.map(run, tasks), 1):
            batches[name].append(compact)
            if sample:
                (samples / f'{name}.json').write_text(json.dumps(sample, ensure_ascii=False, indent=2))
            if i % 25 == 0:
                print(f'{i}/100 BO7', flush=True)
    summary = {}
    for name, matches in batches.items():
        rallies = [r for m in matches for r in m['rallies']]
        wins = sum(m['winner'] == 0 for m in matches)
        summary[name] = dict(matches=len(matches), wins_A=wins, wins_B=len(matches) - wins,
            mean_strokes=round(statistics.mean(rallies), 3), median_strokes=statistics.median(rallies),
            P_strokes_ge20=round(sum(r >= 20 for r in rallies) / len(rallies), 4))
    report = dict(version=Game.VERSION, classification='SIMULATED_BENCHMARK_NOT_HISTORICAL_WIN_RATE',
        note='100 compact executed logs plus one full sample per pairing; all logs can be regenerated from cards/seeds.',
        game_sha256=hashlib.sha256((ROOT / 'Game/__init__.py').read_bytes()).hexdigest(),
        tactical_sha256=hashlib.sha256((ROOT / 'runtime/tactical_match_v116.py').read_bytes()).hexdigest(),
        summary=summary, matches=batches)
    (ROOT / 'reports/GAME_BENCHMARK.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
