"""Predeclared 42 x N match matrix; actual engine calls, not synthetic scores."""
from pathlib import Path
import argparse
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
import json
import math
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from common import canonical_json
from Card import v118 as Card
from Game.v1_18 import match_card
from Game.worker_v1_18 import run
from Game.integration_v1_18 import finalize
from Game.formats_v1_18 import validate_result


def source_hashes():
    selected=[p for p in (ROOT/'Game').glob('*.py') if p.name!='competition_v1_18.py']
    selected+=list((ROOT/'runtime').glob('game_v*.py'))+[ROOT/'runtime/tactical_match_v116.py',ROOT/'runtime/specialist_rubber_v116.py',ROOT/'common/__init__.py',ROOT/'Training/v1_18.py',ROOT/'Training/v118.py',ROOT/'runtime/career_v118.py',ROOT/'runtime/career_v116.py',Path(__file__)]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in selected}

def base_cards(gap=0,style='neutral'):
    a=Card.make_ma18();a['style_profile']['axes']=dict.fromkeys(a['style_profile']['axes'],.5)
    b=copy.deepcopy(a);b['player_id']='stress_v1_18_B';a['player_id']='stress_v1_18_A'
    if gap:
        target=a['CA']+gap
        original=copy.deepcopy(b)
        for n in range(-250,251):
            offset=n/10;b=copy.deepcopy(original)
            b['children']={g:{k:max(50,min(145,v+offset)) for k,v in sub.items()} for g,sub in b['children'].items()}
            b['P6']={k:max(50,min(145,v+offset)) for k,v in b['P6'].items()};b=Card.recompute(b)
            if b['CA']==target:break
        else:raise ValueError('target CA not found')
    if style=='wings':a['style_profile']['axes'].update(forehand_use=.85,backhand_use=.15);b['style_profile']['axes'].update(forehand_use=.15,backhand_use=.85)
    if style=='left_right':a['hand']='left';b['hand']='right'
    if style=='chopper':b.update(style='modern_chopper',rubbers=dict(fh='inverted',bh='long_pips'))
    return [match_card(a),match_card(b)]

def plans(n):
    result=[]
    def add(label,fmt=5,patch=False,first=0,gap=0,style='neutral',mode='summary'):
        result.append(dict(id=label,best_of=fmt,patch=patch,first_server=first,gap=gap,style=style,mode=mode,
            fatigue=[10,70] if style=='fatigue' else [25,25],samples=n,seed_start=118200000+len(result)//2*2000))
    for fmt in (3,5,7):
        for first in (0,1):
            for patch in (False,True):add(f'equal_BO{fmt}_serve{first}_patch{int(patch)}',fmt,patch,first)
    for gap in (-20,-15,-10,-5,5,10,15,20):
        for patch in (False,True):add(f'gap{gap:+d}_patch{int(patch)}',gap=gap,patch=patch)
    for style in ('wings','left_right','chopper','fatigue'):
        for patch in (False,True):add(f'{style}_patch{int(patch)}',style=style,patch=patch)
    for fmt in (3,5,7):
        for first in (0,1):add(f'full_BO{fmt}_serve{first}',fmt=fmt,first=first,mode='full')
    return result

def task(item):
    plan,start,count=item;cards=plan.get('cards') or base_cards(plan['gap'],plan['style'])
    out=dict(samples=0,A_wins=0,games=0,shutouts=0,one_point_games=0,points=0,A_points=0,total_strokes=0,
        comeback_games=0,max_delta=0.,XP_max_path_ratio=0.,early_terminated_games_checked=0)
    from Training import v1_18 as Training
    states=[]
    for card in cards:
        source=dict(Card.make_ma18(),**card);source.pop('style_profile',None)
        states.append(Training.initialize(Card.normalize(source),seed=118))
    for k in range(start,start+count):
        request=dict(cards=cards,seed=plan['seed_start']+k,max_games=plan['best_of'],detail_level=plan['mode'],
            fatigue=plan['fatigue'],physical_fatigue=True,anti_shutout=plan['patch'],first_server=plan['first_server'])
        r=run(request);r=finalize(r,request);validate_result(r)
        out['samples']+=1;out['A_wins']+=r['winner']==0;out['games']+=len(r['games']);out['points']+=r['points'];out['total_strokes']+=r['total_strokes']
        out['A_points']+=sum(g['score'][0] for g in r['games']);out['shutouts']+=sum(min(g['score'])==0 for g in r['games']);out['one_point_games']+=sum(min(g['score'])==1 for g in r['games'])
        trends=r.get('score_trends',[])
        if not trends:
            for g in r['games']:
                peak=[0,0]
                for p in g.get('points',[]):
                    for a in (0,1):peak[a]=max(peak[a],p['score_before'][a]-p['score_before'][1-a])
                trends.append(dict(comeback_from_four=peak[1-g['winner']]>=4))
        out['comeback_games']+=sum(t['comeback_from_four'] for t in trends)
        out['max_delta']=max(out['max_delta'],r['psychology_summary']['max_absolute_delta']);out['early_terminated_games_checked']+=len(r['games'])
        # Independent deterministic reward check on a fresh per-match state;
        # the world stress separately checks cumulative phase caps.
        r.update(participant_ids=[c['player_id'] for c in cards],match_id=plan['id']+':'+str(k))
        r['log_sha256']=hashlib.sha256(canonical_json(r).encode()).hexdigest()
        for actor in (0,1):
            state=copy.deepcopy(states[actor]);state['id']=cards[actor]['player_id']
            reward=Training.match_reward(state,r,state['id'],cards[1-actor]['CA'],exchange=False)
            for p,v in reward['grants'].items():out['XP_max_path_ratio']=max(out['XP_max_path_ratio'],v/max(Training.reference_focus_xp(state,p),1e-12))
    return plan['id'],out

def wilson(w,n):
    z=1.95996398454;p=w/n;d=1+z*z/n;center=(p+z*z/(2*n))/d;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [center-half,center+half]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--samples',type=int,default=1000);parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    if args.output.exists():raise ValueError('fresh evidence directory required')
    args.output.mkdir(parents=True);ps=plans(args.samples);sources=source_hashes()
    for p in ps:p['cards']=base_cards(p['gap'],p['style'])
    plan=dict(version='V1.18-1',status='PREDECLARED_BEFORE_RUN',configurations=ps,source_sha256=sources,
        note='42 selected configurations, not the full factorial; all design effects, no historical calibration.')
    (args.output/'PREDECLARED_PLAN.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    jobs=[(p,start,min(50,args.samples-start)) for p in ps for start in range(0,args.samples,50)];acc={};tick=time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for index,(pid,row) in enumerate(pool.map(task,jobs),1):
            if pid not in acc:acc[pid]=row
            else:
                for key,value in row.items():acc[pid][key]=max(acc[pid][key],value) if key in ('max_delta','XP_max_path_ratio') else acc[pid][key]+value
            if index%20==0:print(f'{index}/{len(jobs)} batches; {round(time.perf_counter()-tick,1)} seconds',flush=True)
    if source_hashes()!=sources:raise ValueError('Game source changed during run')
    for pid,row in acc.items():
        row.update(A_win_rate=row['A_wins']/row['samples'],A_win_Wilson95=wilson(row['A_wins'],row['samples']),
            shutout_game_rate=row['shutouts']/row['games'],shutout_Wilson95=wilson(row['shutouts'],row['games']),
            mean_points=row['points']/row['samples'],mean_games=row['games']/row['samples'],mean_strokes=row['total_strokes']/row['points'],
            comeback_game_rate=row['comeback_games']/row['games'])
        assert row['max_delta']<=.085+1e-10 and row['XP_max_path_ratio']<=.20+1e-7
    report=dict(version='V1.18-1',status='EXECUTED_SELECTED_MATRIX_NOT_HISTORICAL_VALIDATION',total_matches=sum(x['samples'] for x in acc.values()),
        configurations=len(ps),samples_per_configuration=args.samples,source_sha256=sources,results=acc,elapsed_seconds=time.perf_counter()-tick)
    (args.output/'MONTE_CARLO_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('Completed',report['total_matches'],'matches',flush=True)
if __name__=='__main__':main()
