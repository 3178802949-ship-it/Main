"""Constructed evidence probes: reward bounds, rarity and permanent XP bank.
These are explicitly not engine matches or a population breakthrough estimate.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from Card import v118 as Card
from Training import v1_18 as T
import career_v116 as env
from stress_v1_18 import wilson


def main():
    state=T.initialize(Card.make_ma18(),seed=118315);path='fh.spin';wins=0;trials=2000
    for i in range(trials):
        s=copy.deepcopy(state);log=dict(participant_ids=[s['id'],'synthetic-peer'],match_id='SYNTHETIC:'+str(i),mode='full',
            exposure_by_player=[dict(usage={path:12},pressure={path:4}),dict(usage={},pressure={})],
            quality_by_player=[{path:dict(quality_factor=1.,decisive_successes=2,error_rate=0.)},{}],log_sha256=hashlib.sha256(str(i).encode()).hexdigest())
        r=T.match_reward(s,log,s['id'],T.performance_card(s)['CA'],exchange=False)
        wins+=sum(x['granted'] for x in r['breakthrough_draws'])
        assert r['CA_before']==r['CA_after'] and sum(r['permits'].values())<=1
        T.load_state(T.dump_state(s))
    bank=copy.deepcopy(state);r=T.award_xp(bank,'bank-test',{path:3.75},source_kind='SYNTHETIC_BANK_TEST',evidence_hash='f'*64)
    before=sum(bank['xp'].values())
    for month in range(24):
        for phase in (0,1):T.settle_phase(bank,dict(month=month,phase=phase,mode='rest'),env.environment('club'),f'rest:{month}:{phase}',record=False)
    assert abs(sum(bank['xp'].values())-before)<1e-10;T.load_state(T.dump_state(bank))
    result=dict(version='V1.18-1',status='CONSTRUCTED_REWARD_PROBES_PASSED',source_scope='SYNTHETIC_NOT_ENGINE_MATCHES',
        eligible_D100_path_trials=trials,permits_granted=wins,observed_rate=wins/trials,Wilson95=wilson(wins,trials),
        per_eligible_path_threshold=.02,not_a_per_match_or_population_rate=True,rest_months=24,XP_bank_before=before,XP_bank_after=sum(bank['xp'].values()),
        original_skills_not_directly_awarded=True,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),ROOT/'Training/v1_18.py',ROOT/'Training/v118.py')})
    out=ROOT/'reports/v1_18/REWARD_PROBES.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
