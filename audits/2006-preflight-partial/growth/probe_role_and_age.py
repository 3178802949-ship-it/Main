"""Small, synthetic execution probes alongside the independent career matrix."""
from pathlib import Path
import copy
import hashlib
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import calibrate_training_core as M
import career_v118 as Career


def main():
    rows=[]
    for seed in range(200688000,200688050):
        a=M.template();b=copy.deepcopy(a);a['role']='user';b['role']='NPC'
        sa=M.Training.initialize(a,seed=seed);sb=M.Training.initialize(b,seed=seed)
        assert sa==sb,'role affects initial state'
        for index in range(24):
            p=M.plan_for(sa,index);env=M.Environment.environment('national');eid='synthetic-role:'+str(index)
            ra=M.Core._settle(sa,p,env,eid,(),False);rb=M.Core._settle(sb,p,env,eid,(),False)
            assert ra==rb and sa==sb,'role affects training'
        rows.append(dict(seed=seed,phases=24,exact_role_swap=True))
    s=M.Training.initialize(M.template(),seed=200688000)
    ages={str(a):Career.learning_age_factor(s,a) for a in (21.999999,22,24.999999,25)}
    before=copy.deepcopy(s);after=copy.deepcopy(s)
    Career.age_and_body(before,26.999999,M.Environment.environment('national'),108)
    Career.age_and_body(after,27,M.Environment.environment('national'),108)
    report=dict(status='PASSED',scope='SYNTHETIC_TRAINING_CORE_ONLY',role_swap_seeds=50,
                phases_each_role_per_seed=24,all_states_and_receipts_exact=True,
                role_swap_probes=rows,learning_age_boundary_factors=ages,
                maturation_P_near_27={k:before['P6'][k]-after['P6'][k] for k in before['P6']},
                source_sha256=M.source_hashes(),probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation='Does not compare World NPC plans, budgets, schedules or health exposure.')
    out=Path(__file__).resolve().parent/'ROLE_AND_AGE_PROBES.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2));print('50 exact role-swap seed probes passed')


if __name__=='__main__':main()
