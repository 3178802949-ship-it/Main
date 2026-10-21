"""Two original careers from 2006 through the finite 2028 Olympic horizon.

Quarterly actual summary games; explicit quality-environment budget; real
Training phases, aging, injury restrictions and yearly verified checkpoints.
"""
import copy
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import Card
from common import SCHEMA
from world_v117 import WorldSession
from stress_world_v117 import source_sha256


def original_cards():
    result = []
    for i, potential in enumerate((198, 176)):
        value = copy.deepcopy(Card.make_ma18())
        value.update(player_id=f'original_horizon_{i}', preset_id=f'original_horizon_{i}@2006',
                     name_zh=('原创高潜测试员', '原创普通精英')[i], source_prototype='SYNTHETIC',
                     origin='SYNTHETIC', PA=potential,
                     pa_range=[max(0, potential-3), min(200, potential+3)],
                     career_resources=dict(investment_units=12, national_eligible=True),
                     historical_reference={'champion_history': [], 'classification': 'NONE'})
        if i:
            value['children'] = {group: {key: max(0, level-7) for key, level in subs.items()}
                                 for group, subs in value['children'].items()}
            value['P6'] = {key: level-5 for key, level in value['P6'].items()}
        result.append(Card.normalize(value))
    return result


def run():
    tick = time.perf_counter()
    world = WorldSession.create(original_cards(), 2006, start_date='2006-02-01',
                                seed=1172028, world_id='v117-whole-horizon')
    sources = source_sha256()
    initial = {pid: dict(CA=world.card(pid)['CA'], PA=state['PA'], P6=copy.deepcopy(state['P6']))
               for pid, state in world.data['players'].items()}
    baseline = len(world.dump().encode())
    annual, investment, phase_modes = [], {}, {'train': 0, 'rest': 0}
    matches = skipped = phases = yearly_verifications = 0
    groups = list(SCHEMA['core_order'])
    bodies = list(SCHEMA['body_weights_pct'])
    while not world.data['completed']:
        current_date = world.data['current_date']
        year = int(current_date[:4])
        state = world.data['players'][world.data['main_player_id']]
        month, half = state['month'], state['training_release']['phase']
        reviews = []
        if half == 0 and month % 3 == 0:
            ready = all(s['month'] >= s.get('rehab_until', 0) and s['fatigue'] < 80
                        for s in world.data['players'].values())
            if ready:
                mid = f'quarter:{month}'
                world.play_practice(*list(world.data['players']), mid, 1173000+month)
                reviews = [mid]
                matches += 1
            else:
                skipped += 1
        for pid, state in world.data['players'].items():
            rest = state['fatigue'] >= 45 or state['month'] < state.get('rehab_until', 0)
            mode = 'rest' if rest else 'train'
            plan = dict(month=month, phase=half, mode=mode)
            environment = 'club'
            if not rest:
                selected = [groups[(month*2+half+i*4) % len(groups)] for i in range(2)]
                plan.update(technical=[dict(group=group, specialize=list(state['children'][group])[:2])
                                       for group in selected], body=bodies[month % len(bodies)])
                used = investment.setdefault(str(year), {}).get(pid, 0)
                if half == 0 and used < 12:
                    environment = 'national'
            receipt = world.train_phase(pid, plan, f'horizon:{month}:{half}:{pid}',
                environment_name=environment, review_match_ids=reviews if not rest else ())
            spent = receipt['world_settlement']['investment_cost']
            investment.setdefault(str(year), {})[pid] = investment.setdefault(str(year), {}).get(pid, 0)+spent
            phase_modes[mode] += 1
            phases += 1
        if world.data['completed'] or int(world.data['current_date'][:4]) != year:
            checkpoint = world.dump()
            restored = WorldSession.load(checkpoint)
            assert restored.dump() == checkpoint
            assert not restored.artifacts
            yearly_verifications += 1
            record = dict(settled_calendar_year=year, date=world.data['current_date'],
                checkpoint_bytes=len(checkpoint.encode()), matches=matches,
                players={pid: dict(age=world.card(pid)['age_approx'], CA=world.card(pid)['CA'],
                    learned_CA=world.card(pid)['learned_CA'], PA=state['PA'], pa_range=state['pa_range'],
                    P6=copy.deepcopy(state['P6']), fatigue=state['fatigue'], injuries=state['injuries'],
                    body_limited_subskills=len(world.card(pid)['body_limitations']),
                    investment_units=world.data['resources'][pid]['investment_units'],
                    national_training_units_spent=investment[str(year)][pid])
                    for pid, state in world.data['players'].items()})
            annual.append(record)
            # Continue from the loaded checkpoint, rather than merely inspect it.
            world = restored
    final = world.consistency_check(deep=True)
    assert final['completed'] and final['current_date'] == '2028-07-30'
    assert final['matches'] == matches and matches >= 60
    assert phases == 1080  # Feb 2006 through July 2028, 270 months * 2 phases * 2 actors.
    assert all(spent <= 12 for players in investment.values() for spent in players.values())
    assert not world.artifacts
    assert all(not state['training_release']['phase_log'] for state in world.data['players'].values())
    assert source_sha256() == sources, 'source changed during the experiment; rerun after freeze'
    peaks = {pid: max((dict(year=row['settled_calendar_year'], **row['players'][pid]) for row in annual),
                      key=lambda record: record['CA']) for pid in world.data['players']}
    report = dict(version='V1.1.7-CANDIDATE-1', experiment='ACTUAL_TWO_ORIGINAL_CAREERS_2006_2028',
        source_sha256=sources, start_date='2006-02-01', end_date=final['current_date'],
        ruleset_fingerprint_sha256=world.data['ruleset_fingerprint']['sha256'],
        initial_players=initial, phases=phases, phase_modes=phase_modes, summary_matches=matches,
        skipped_quarterly_fixtures_due_to_health=skipped, full_logs_retained=0,
        yearly_dump_load_continue_verifications=yearly_verifications,
        baseline_checkpoint_bytes=baseline, final_checkpoint_bytes=len(world.dump().encode()),
        annual_samples=annual, annual_sample_peaks=peaks, final_consistency=final,
        elapsed_seconds=round(time.perf_counter()-tick, 6), limitations=[
            'Two synthetic careers validate finite-horizon integration, not population-level calibration.',
            'Quarterly practice provides real exposure; it gives no titles, formal Elo/S-PTS or champion opportunities.',
            'National-quality access is explicitly granted by this test scenario; spending is capped at 12 units/player/year.',
            'Annual samples are for trends; the individual growth calibration report supplies precise peak distributions.'])
    output = ROOT / 'reports' / 'v117' / 'world_horizon_v117.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('annual_samples', 'source_sha256')},
                     ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    run()
