"""Independent SYNTHETIC training-core paths; never advance a user World.

The exact frozen numerical core is called in-place, with no monkeypatches or
shortened clock. The public wrapper is separately checked on a complete path.
This is not an injury/population/full-career competition simulation.
"""
from pathlib import Path
import argparse
import concurrent.futures
import copy
import hashlib
import json
import math
import os
import statistics
import sys
import time

ROOT = Path(os.environ.get('SPIN_ERA_ENGINE_ROOT', '/workspace/spin-era-v1_18-github/spin_era_v1_18'))
sys.path.insert(0, str(ROOT))
from Card import v1_18 as Card
from Training import v1_18 as Training
from Training import v118 as Core
from common import SCHEMA, canonical_json
import career_v116 as Environment

HERE = Path(__file__).resolve().parent
AGES = (20, 23, 26, 28, 30)
ARMS = (
    dict(id='PA191_CLUB_USER', PA=191, environment='club', role='user'),
    dict(id='PA191_NATIONAL_USER', PA=191, environment='national', role='user'),
    dict(id='PA191_NATIONAL_NPC', PA=191, environment='national', role='NPC'),
    dict(id='PA175_NATIONAL_NPC', PA=175, environment='national', role='NPC'),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    paths = [Path(__file__)]
    for folder in ('Card', 'Training', 'runtime', 'common'):
        paths += sorted((ROOT / folder).rglob('*.py'))
    paths += [ROOT/'data/original/spin_era_v013_frozen_attribute_schema.json',
              ROOT/'data/presets_normalized.json']
    return {str(p): sha(p) for p in paths}


def template():
    baseline = Card.make_ma18()
    # Borrow only numeric template values. Names, real prototype provenance,
    # personality and all actual career history are absent from experiment card.
    card = dict(player_id='SYNTHETIC_NUMERIC_TEMPLATE', name_zh='合成成长模板',
                children=copy.deepcopy(baseline['children']), P6=copy.deepcopy(baseline['P6']),
                PA=191, age_approx=18, model_start_age=18,
                classification='SIMULATED', origin='SYNTHETIC',
                source_prototype='SYNTHETIC_NUMERIC_TEMPLATE', role='synthetic')
    for key in ('development_profile', 'learning_factor', 'style_preference'):
        card[key] = copy.deepcopy(baseline[key])
    return Card.normalize(card)


def declaration():
    card = template()
    cases = [dict(arm=arm['id'], seed=200600000 + index*10000+i)
             for index, arm in enumerate(ARMS) for i in range(250)]
    return dict(status='PREDECLARED', scope='SYNTHETIC_TRAINING_CORE_ONLY',
                inputs=card, inputs_sha256=hashlib.sha256(canonical_json(card).encode()).hexdigest(),
                arms=ARMS, cases=cases, samples_per_arm=250, total_independent_paths=1000,
                start_age=18, end_age=30, half_month_phases=288, sample_ages=AGES,
                prior='balanced_progress', strategy='bounded_opportunities',
                schedule='two rotating categories and one rotating P6 category, no specialization',
                formal_events=0, synthetic_review_windows=0, match_rewards=0,
                injury_exposure='NOT_MODELLED_NO_WORLD_NO_MATCHES', exit_rate='NOT_MODELLED',
                caveat='Conditional one-template random paths, not real athletes or population inference.',
                source_sha256=source_hashes())


def plan_for(state, index):
    groups = tuple(SCHEMA['core_order']); bodies = tuple(SCHEMA['body_weights_pct'])
    return dict(month=state['month'], phase=state['training_release']['phase'],
                technical=[dict(group=groups[index % len(groups)]),
                           dict(group=groups[(index+4) % len(groups)])],
                body=bodies[index % len(bodies)])


def run_one(case):
    arm = next(a for a in ARMS if a['id'] == case['arm'])
    card = template(); card.update(PA=arm['PA'], role=arm['role'], player_id='SYNTHETIC_'+arm['id'])
    state = Training.initialize(card, seed=case['seed'], start_age=18)
    env = Environment.environment(arm['environment'])
    samples = {}; peak_CA = -1; peak_age = None; max_fatigue = 0; high_load_phases = 0
    for index in range(288):
        plan = plan_for(state, index)
        receipt=Core._settle(state, plan, env, 'synthetic-training:'+str(index), (), False)
        age = 18 + (state['month'] + state['training_release']['phase']/2)/12
        if receipt['CA_after'] > peak_CA: peak_CA, peak_age = receipt['CA_after'], age
        max_fatigue = max(max_fatigue, state['fatigue']); high_load_phases += state['fatigue'] >= 70
        if state['training_release']['phase'] == 0 and age in AGES:
            current = Training.performance_card(state)
            samples[str(int(age))] = dict(CA=current['CA'], learned_CA=current['learned_CA'],
                PA=state['PA'], P6=copy.deepcopy(state['P6']),
                bank_XP=sum(state['xp'].values()), permits=sum(state['permits'].values()),
                support_limited=len(current['body_limitations']))
    Training.load_state(Training.dump_state(state))
    return dict(case, samples=samples, peak_CA=peak_CA, first_peak_age=peak_age,
                final_PA=state['PA'], max_fatigue=max_fatigue, high_load_phases=high_load_phases,
                training_XP_awarded=state['audit']['XP_FOCUS']+state['audit']['XP_GENERAL'],
                training_XP_spent=state['audit']['XP_SPENT'],
                unspent_XP=sum(state['xp'].values()), unspent_permits=sum(state['permits'].values()),
                banked_paths_at_cap=sum(state['xp'][p]>0 and state['children'][p.split('.')[0]][p.split('.')[1]]+1>__import__('career_v118').soft_cap(state,p)+1e-8 for p in state['xp']))


def wilson(k, n):
    z=1.959963984540054; p=k/n; den=1+z*z/n
    mid=(p+z*z/(2*n))/den; half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [mid-half, mid+half]


def quantile(values, q):
    s=sorted(values); f=(len(s)-1)*q; i=math.floor(f)
    return s[i] if i==len(s)-1 else s[i]*(1-f+i)+s[i+1]*(f-i)


def summarize(rows):
    result={}
    for arm in ARMS:
        rr=[r for r in rows if r['arm']==arm['id']]; by_age={}
        for age in AGES:
            values=[r['samples'][str(age)]['CA'] for r in rr]
            by_age[str(age)]=dict(n=len(values),mean=statistics.mean(values),
                quantiles={str(q):quantile(values,q) for q in (.05,.25,.5,.75,.95)},
                attainment={str(t):dict(count=sum(v>=t for v in values),rate=sum(v>=t for v in values)/len(values),
                    Wilson95=wilson(sum(v>=t for v in values),len(values))) for t in (180,185,190)})
        peaks=[r['peak_CA'] for r in rr]
        result[arm['id']]=dict(configuration=arm, samples=len(rr), ages=by_age,
            first_peak_age_median=statistics.median(r['first_peak_age'] for r in rr),
            peak_CA_mean=statistics.mean(peaks),
            peak_attainment={str(t):dict(count=sum(v>=t for v in peaks),rate=sum(v>=t for v in peaks)/len(peaks),Wilson95=wilson(sum(v>=t for v in peaks),len(peaks))) for t in (180,185,190)},
            unspent_XP_mean=statistics.mean(r['unspent_XP'] for r in rr),
            banked_paths_at_cap_mean=statistics.mean(r['banked_paths_at_cap'] for r in rr),
            max_observed_training_fatigue=max(r['max_fatigue'] for r in rr),
            high_load_phases=sum(r['high_load_phases'] for r in rr),
            injury_incidence='NOT_MODELLED', exit_incidence='NOT_MODELLED')
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args();plan_path=HERE/'PREDECLARED_GROWTH_PLAN.json'
    plan=declaration()
    if plan_path.exists() or (HERE/'CAREER_PATHS.jsonl').exists():raise ValueError('preserve previous experiment')
    plan_path.write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    # Verify that in-place execution changes no numerical behavior, including
    # audit counters and XP mass, relative to the transactional public wrapper.
    check_a=Training.initialize(template(),seed=299999999,start_age=18);check_b=copy.deepcopy(check_a)
    for index in range(288):
        p=plan_for(check_a,index);event_id='public-equivalence:'+str(index);env=Environment.environment('national')
        a=Training.settle_phase(check_a,p,env,event_id,record=False)
        b=Core._settle(check_b,p,env,event_id,(),False)
        assert a==b and check_a==check_b,'in-place optimization differs from public wrapper'
    tick=time.perf_counter(); rows=[]
    with (HERE/'CAREER_PATHS.jsonl').open('w') as f, concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(run_one,plan['cases'],chunksize=4):
            rows.append(row);f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
            if len(rows)%100==0:print(len(rows),'paths complete',round(time.perf_counter()-tick,1),'seconds',flush=True)
    assert len(rows)==1000 and len({r['seed'] for r in rows})==1000
    assert plan['source_sha256']==source_hashes(),'source changed during experiment'
    report=dict(status='COMPLETED',scope=plan['scope'],total_independent_paths=len(rows),
                source_sha256=plan['source_sha256'],plan_sha256=sha(plan_path),raw_results_sha256=sha(HERE/'CAREER_PATHS.jsonl'),
                half_month_phases=288000,public_wrapper_equivalence_phases=288,elapsed_seconds=time.perf_counter()-tick,arms=summarize(rows),
                limitation=plan['caveat'],injury_exposure=plan['injury_exposure'],exit_rate=plan['exit_rate'])
    (HERE/'GROWTH_CALIBRATION_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('1000 independent training-core paths complete',flush=True)


if __name__=='__main__':main()
