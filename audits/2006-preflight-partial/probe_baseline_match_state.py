"""Read-only synthetic probes of the previously available V1.18 release.
Not a 2004-2006 history recovery and never a 2007 formal fixture.
"""
from pathlib import Path
import copy, hashlib, json, random, sys
ROOT=Path('/workspace/spin-era-v1_18-github/spin_era_v1_18')
sys.path.insert(0,str(ROOT))
from common import canonical_json
from simulator import Card, Game
from Game import engine_v1_18 as engine

def digest(x):return hashlib.sha256(canonical_json(x).encode()).hexdigest()
def card(pid):
 c=copy.deepcopy(json.loads((ROOT/'data/presets_normalized.json').read_text())['starters']['ma18']);c['player_id']=pid;return c
class CountRng(random.Random):
 def __init__(self,seed):super().__init__(seed);self.ints=[]
 def randint(self,a,b):
  v=super().randint(a,b);self.ints.append([a,b,v]);return v
out=dict(status='SYNTHETIC_BASELINE_PROBES',source='PREVIOUS_RELEASE_V1.18_NOT_NEW_UPLOAD',formal_history_matches_run=0,probes=[])
base=[card('synthetic-alpha'),card('synthetic-beta')]
for seed in range(50):
 r=CountRng(6000+seed);s=engine.core.warmup(base[0],r,25)
 assert [v[:2] for v in r.ints]==[[-4,4]]*6+[[-7,7]]*9
out['probes'].append(dict(name='50_warmups_single_native_daily_roll',passed=True,seeds=50,p_roll_range=[-4,4],g_raw_roll_range=[-7,7],per_actor_p_draws=6,per_actor_g_draws=9,notes='Stable can contract the applied G roll; 25 fatigue avoids decrement branch.'))
for mode in ('full','summary'):
 seed=21180607
 a=Game.play_match(base,seed,'synthetic-state-audit',world_id='UNLINKED_SYNTHETIC_AUDIT',best_of=3,detail_level=mode)
 b=Game.play_match(base,seed,'synthetic-state-audit',world_id='UNLINKED_SYNTHETIC_AUDIT',best_of=3,detail_level=mode)
 assert a['log_sha256']==b['log_sha256'];assert Game.replay(Game.compact_log(a))['valid']
 changed=copy.deepcopy(base)
 for i,c in enumerate(changed):c.update(PA=1 if i==0 else 200,personality_profile={'unvalidated_audit_marker':i},hot_hand_level=5,arousal_level=2)
 c=Game.play_match(changed,seed,'synthetic-state-audit',world_id='UNLINKED_SYNTHETIC_AUDIT',best_of=3,detail_level=mode)
 assert a['log_sha256']==c['log_sha256']
 renamed=copy.deepcopy(base);renamed[0]['player_id']='renamed-other';renamed[1]['player_id']='renamed-main'
 d=Game.play_match(renamed,seed,'synthetic-state-audit',world_id='UNLINKED_SYNTHETIC_AUDIT',best_of=3,detail_level=mode)
 assert a['games']==d['games']
 out['probes'].append(dict(name=mode+'_replay_and_identity_metadata',passed=True,best_of=3,seed=seed,games=a['games_won'],game_payload_hash=digest(a['games']),same_seed_full_hash_reproducible=True,compact_replay=True,PA_personality_and_unsupported_hot_arousal_do_not_enter_match=True,renaming_id_preserves_games=True,physical_fatigue_audit_rows=len(a['physical_fatigue_audit'])))
# Pure fixed-contact probes; same arrival grade and RNG draw on every call.
b=base[0];s=engine.core.warmup(b,random.Random(7),25)
ball=dict(spin='top',pace=125,quality=120,landed='fh')
q=[]
for key in ('strength','burst','speed'):
 row=[]
 for v in (60,150):
  st=copy.deepcopy(s);st['p_eff'][key]=v
  quality,pace,spin=engine._quality(b,st,ball,'good','fh_attack',random.Random(11),4,False,'fh');row.append(dict(value=v,quality=quality,pace=pace))
 assert row[0]['quality']==row[1]['quality']
 q.append(dict(body=key,results=row))
out['probes'].append(dict(name='P6_no_global_contact_quality_bonus',passed=True,controlled_fixed_arrival=True,results=q,notes='Burst affects offensive pace once; speed affects reach elsewhere; strength influences support-cap eligibility before match but has no direct Game quality/pace term.'))
out['actual_synthetic_matches_run']=10 # replay invokes one additional engine run in each mode
out['not_tested']=['Population balance or actor-order invariance distribution','New uploaded 2006 outer state overlays','Historical final seed 200612170717','Game-level injury metadata without Training settlement']
files=['Game/v1_18.py','Game/worker_v1_18.py','Game/engine_v1_18.py','Game/light_v1_18.py','Game/fatigue_v1_18.py','runtime/game_v112.py','runtime/game_v113.py','Game/formats_v1_18.py','runtime/career_v118.py']
out['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}
Path('/workspace/audits/full_history_2006/BASELINE_MATCH_STATE_PROBES.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in out.items() if k not in ('probes','source_sha256')},ensure_ascii=False,indent=2))
