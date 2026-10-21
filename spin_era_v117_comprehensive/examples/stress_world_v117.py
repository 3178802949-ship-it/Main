"""Measured two-year, four-player V1.1.7 World integration exercise.

Run from the package root: python examples/stress_world_v117.py
This tests the real summary Game and real Training, including finite recovery.
"""
import copy
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import Card
from world_v117 import WorldSession, ruleset_fingerprint


def source_sha256():
    files = ruleset_fingerprint()['files']
    for path in ('examples/stress_world_v117.py', 'examples/stress_horizon_v117.py'):
        files[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    return files


def sample_cards():
    cards = []
    for i in range(4):
        card = copy.deepcopy(Card.make_ma18())
        card.update(player_id=f'stress117_{i}', preset_id=f'stress117_{i}@2006',
                    source_prototype='SYNTHETIC', origin='SYNTHETIC',
                    historical_reference={'champion_history': [], 'classification': 'NONE'})
        cards.append(card)
    return cards


def run():
    started = time.perf_counter()
    sources = source_sha256()
    world = WorldSession.create(sample_cards(), 2006, start_date='2006-02-01',
                                seed=117779, world_id='v117-world-stress')
    baseline = len(world.dump().encode())
    match_seconds, phase_seconds, match_record_bytes, phase_record_bytes = [], [], [], []
    sizes, phases, rests, skipped, max_fatigue = [], 0, 0, 0, 0.
    for phase_index in range(48):
        # 48 ordinary fixtures + sixteen extra fixtures; no competition is
        # forced through rehabilitation or fatigue gates to meet a sample size.
        fixtures = 2 if phase_index % 3 == 0 else 1
        for fixture in range(fixtures):
            eligible = [pid for pid, state in world.data['players'].items()
                        if state['month'] >= state.get('rehab_until', 0) and state['fatigue'] < 80]
            eligible.sort(key=lambda pid: (world.data['activity'][pid]['match_count'],
                                           len(world.card(pid)['simulated_career']['matches']), pid))
            if len(eligible) < 2:
                skipped += 1
                continue
            mid = f'stress:p{phase_index}:m{fixture}'
            tick = time.perf_counter()
            world.play_practice(*eligible[:2], mid, 117000 + phase_index * 3 + fixture)
            match_seconds.append(time.perf_counter() - tick)
            match_record_bytes.append(len(json.dumps(world.data['matches'][mid], ensure_ascii=False).encode()))
        for pid, state in world.data['players'].items():
            rest = state['fatigue'] >= 45 or state['month'] < state.get('rehab_until', 0)
            plan = dict(month=state['month'], phase=state['training_release']['phase'])
            if rest:
                plan['mode'] = 'rest'
                rests += 1
            else:
                plan.update(technical=[dict(group='read', specialize=['self_read', 'choice']),
                                       dict(group='bh', specialize=['defense', 'placement'])], body='stamina')
            event_id = f'stress:settle:{phase_index}:{pid}'
            tick = time.perf_counter()
            world.train_phase(pid, plan, event_id)
            phase_seconds.append(time.perf_counter() - tick)
            phase_record_bytes.append(len(json.dumps(world.data['events'][event_id], ensure_ascii=False).encode()))
            phases += 1
            max_fatigue = max(max_fatigue, world.data['players'][pid]['fatigue'])
        if phase_index % 12 == 11:
            tick = time.perf_counter()
            checkpoint = world.dump()
            recovered = WorldSession.load(checkpoint)
            assert recovered.dump() == checkpoint
            sizes.append(dict(phases_per_player=phase_index + 1, matches=len(world.data['matches']),
                              checkpoint_bytes=len(checkpoint.encode()),
                              dump_load_verify_seconds=round(time.perf_counter() - tick, 6)))
    final_check = world.consistency_check(deep=True)
    assert 40 <= len(match_seconds) <= 100
    assert phases == 192
    assert not world.artifacts
    assert max(phase_record_bytes) < 2500
    assert max(match_record_bytes) < 20000
    assert all(not state['training_release']['phase_log'] for state in world.data['players'].values())
    assert all(len(state.get('training_log', [])) <= 24 for state in world.data['players'].values())
    final = world.dump()
    assert source_sha256() == sources, 'source changed during the experiment; rerun after freeze'
    report = dict(version='V1.1.7-CANDIDATE-1', experiment='ACTUAL_WORLD_FOUR_PLAYERS_TWO_YEARS',
        source_sha256=sources,
        ruleset_fingerprint_sha256=world.data['ruleset_fingerprint']['sha256'],
        players=4, years=2, settled_phases=phases, training_phases=phases-rests, rest_phases=rests,
        summary_matches=len(match_seconds), skipped_fixtures_due_to_health=skipped,
        injury_events=sum(state['injuries'] for state in world.data['players'].values()),
        max_post_settlement_fatigue=max_fatigue, baseline_checkpoint_bytes=baseline,
        final_checkpoint_bytes=len(final.encode()), compact_match_bytes=dict(min=min(match_record_bytes),
        median=statistics.median(match_record_bytes), max=max(match_record_bytes)),
        phase_receipt_bytes=dict(min=min(phase_record_bytes), median=statistics.median(phase_record_bytes), max=max(phase_record_bytes)),
        median_match_seconds=statistics.median(match_seconds), median_phase_seconds=statistics.median(phase_seconds),
        full_logs_retained=0, size_samples=sizes, final_consistency=final_check,
        final_players={pid: dict(CA=world.card(pid)['CA'], learned_CA=world.card(pid)['learned_CA'],
                                PA=state['PA'], fatigue=state['fatigue'], injuries=state['injuries'],
                                phase_log_length=len(state['training_release']['phase_log']))
                       for pid, state in world.data['players'].items()},
        elapsed_seconds=round(time.perf_counter()-started, 6),
        limitations=['Four synthetic players and two years test integration/storage, not population calibration.',
                    'Checkpoint grows linearly with compact results and identities, not constant-size forever.',
                    'Formal tournament health is a post-event coarse settlement; no mid-bracket walkover adapter.'])
    destination = ROOT / 'reports' / 'v117' / 'world_stress_v117.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    run()
