"""Actual phase/competition/XP/save-load stress through the 2028 horizon."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from simulator import WorldSession,Card,ruleset_fingerprint
from common import SCHEMA
from migration_v1_18 import migrate_checkpoint


def run(output,from_2004=False,phases_limit=None):
    if output.exists():raise ValueError('preserve earlier evidence; use fresh output path')
    tick=time.perf_counter();fingerprint=ruleset_fingerprint();driver_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if from_2004:
        d=ROOT/'data/v1_18/handoff2004';w,_=migrate_checkpoint((d/'WORLD_2005_OPENING_ORIGINAL.json').read_text(),reconciliation=json.loads((d/'RECONCILIATION_INPUT.json').read_text()),new_world_id='spin-era-2005-V1.18-STRESS-ONLY')
    else:
        a=Card.make_ma18();b=copy.deepcopy(a);b.update(player_id='v1_18_original_peer',name_zh='原创普通精英',source_prototype='SYNTHETIC',origin='SYNTHETIC',PA=176,pa_range=[173,179])
        for key in ('career117_profile','career118_profile','personality_profile','style_profile'):b.pop(key,None)
        b['children']={g:{k:v-6 for k,v in sub.items()} for g,sub in b['children'].items()};b=Card.normalize(b)
        w=WorldSession.create([a,b],2006,start_date='2006-02-01',seed=1182028)
    pid=w.data['main_player_id'];groups=list(SCHEMA['core_order']);bodies=list(SCHEMA['body_weights_pct'])
    annual=[];phases=0;matches=0;rested=0;reloads=0;skipped=0;start_matches=len(w.data['matches']);initial=len(w.dump().encode())
    while not w.data['completed'] and (phases_limit is None or phases<phases_limit):
        s=w.data['players'][pid];month,half=s['month'],s['training_release']['phase'];year=int(w.data['current_date'][:4])
        if half==0 and month%3==0:
            eligible=[p for p,q in w.data['players'].items() if q['fatigue']<70 and q['month']>=q.get('rehab_until',0)]
            if len(eligible)>=2 and pid in eligible:
                other=next(p for p in eligible if p!=pid)
                w.play_practice(pid,other,f'stress:{month}',1180000+month,best_of=(3,5,7)[(month//3)%3]);matches+=1
            else:skipped+=1
        state=w.data['players'][pid];rest=state['fatigue']>=45 or state['month']<state.get('rehab_until',0)
        plan=dict(month=month,phase=half,mode='rest' if rest else 'train')
        if not rest:plan.update(technical=[dict(group=groups[(month*2+half+i*4)%len(groups)]) for i in range(2)],body=bodies[month%len(bodies)])
        w.train_phase(pid,plan,f'stress-train:{month}:{half}');phases+=1;rested+=rest
        assert len({(x['month'],x['training_release']['phase']) for x in w.data['players'].values()})==1
        if int(w.data['current_date'][:4])!=year or w.data['completed']:
            saved=w.dump();w=WorldSession.load(saved);assert w.dump()==saved;reloads+=1
            annual.append(dict(year=year,date=w.data['current_date'],players={p:dict(age=w.card(p)['age'],CA=w.card(p)['CA'],PA=x['PA'],P6=x['P6'],injuries=x['injuries']) for p,x in w.data['players'].items()},checkpoint_bytes=len(saved.encode())))
        if phases%48==0:print('settled',phases,'phases,',w.data['current_date'],flush=True)
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==driver_hash
    assert ruleset_fingerprint()==fingerprint,'source changed while stress ran'
    result=dict(version='V1.18-1',status='ACTUAL_WORLD_STRESS_PASSED',from_2004=from_2004,primary_phases=phases,
        background_player_count=len(w.data['players'])-1,background_phase_advances=phases*(len(w.data['players'])-1),
        practice_matches=matches,skipped_due_health=skipped,primary_rests=rested,yearly_exact_reload_continue=reloads,
        initial_matches=start_matches,final_matches=len(w.data['matches']),initial_checkpoint_bytes=initial,final_checkpoint_bytes=len(w.dump().encode()),
        final_consistency=w.consistency_check(deep=True),annual_samples=annual,source_fingerprint=fingerprint,driver_sha256=driver_hash,elapsed_seconds=time.perf_counter()-tick,
        caveat='Conditional model integration exercise, not population or real athlete validation.')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2));print('World stress complete',result['primary_phases'],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--from-2004',action='store_true');p.add_argument('--phases',type=int);a=p.parse_args();run(a.output,a.from_2004,a.phases)
