"""V1.18 integration of match/observation rewards into the existing XP pool.

The numerical age/training core is retained. Every new source is idempotent;
normal XP never expires and permanent changes use the same cap/cost/permit pipe.
"""
import copy
import hashlib
import math
from common import canonical_json, SCHEMA
from Training import v118 as base
import career_v118 as career
import career_v116 as old

VERSION = 'V1.18-TRAINING-1'
PATHS = frozenset(career.PATHS)

def ensure(state):
    state.setdefault('integration_v1_18',dict(version=VERSION,sources={},xp_awarded=0.,
        match_phase_awards={},development_awards=[],vouchers={}))
    a=state['integration_v1_18']
    a.setdefault('initial_xp_total',sum(state['xp'].values()))
    a.setdefault('initial_training_awards',state['audit'].get('XP_FOCUS',0)+state['audit'].get('XP_GENERAL',0))
    a.setdefault('initial_spent',state['audit'].get('XP_SPENT',0))
    state['integration_v1_18'].setdefault('development_requests',{})
    return state['integration_v1_18']

def initialize(*args,**kwargs):
    s=base.initialize(*args,**kwargs);ensure(s);return s

def reference_focus_xp(state,path):
    """Nominal one-path half-month club XP; excludes windows/direct gains."""
    if path not in PATHS: raise ValueError('unknown subskill')
    env=old.environment('club')
    age=state['start_age']+(state['month']+state['training_release']['phase']/2)/12
    quality=.65*env['coaching']+.35*env['partners']
    return 7.5*old.pa_xp_mult(state['PA'])*state['learning_factor'][path]*quality*career.learning_age_factor(state,age)*state['activity_rate']*career.CONFIGS[state['career_v118']['strategy']]['xp_scale']

def award_xp(state,source_id,grants,*,source_kind,evidence_hash,exchange=False,permits=None):
    if not isinstance(source_id,str) or not source_id or not isinstance(evidence_hash,str) or len(evidence_hash)!=64:
        raise ValueError('unique source and content hash required')
    if not isinstance(grants,dict) or not set(grants)<=PATHS or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in grants.values()):
        raise ValueError('finite nonnegative registered subskill XP required')
    permits=permits or {}
    if not set(permits)<=PATHS or any(type(v)is not int or v<0 for v in permits.values()):raise ValueError('invalid permits')
    digest=hashlib.sha256(canonical_json(dict(grants=grants,permits=permits,source_kind=source_kind,evidence_hash=evidence_hash)).encode()).hexdigest()
    existing=ensure(state)['sources'].get(source_id)
    if existing:
        if existing['input_hash']!=digest:raise ValueError('XP_SOURCE_CONFLICT')
        return dict(existing,status='already_applied')
    proposed=copy.deepcopy(state);a=ensure(proposed);before=base.performance_card(proposed)
    before_xp={p:proposed['xp'][p] for p in grants}
    for p,v in grants.items():proposed['xp'][p]+=v
    for p,v in permits.items():proposed['permits'][p]+=v;proposed['audit']['PERMITS_AWARDED']+=v
    if exchange:
        for p in grants:base._exchange(proposed,p)
    after=base.performance_card(proposed)
    result=dict(status='applied',version=VERSION,source_id=source_id,source_kind=source_kind,
        evidence_hash=evidence_hash,input_hash=digest,grants=copy.deepcopy(grants),permits=copy.deepcopy(permits),
        xp_before=before_xp,xp_after={p:proposed['xp'][p] for p in grants},
        CA_before=before['CA'],CA_after=after['CA'],subskill_deltas={f'{g}.{k}':after['learned_children'][g][k]-before['learned_children'][g][k]
            for g,sub in after['learned_children'].items() for k in sub if after['learned_children'][g][k]!=before['learned_children'][g][k]},
        month=state['month'],phase=state['training_release']['phase'],expiry=None)
    a['sources'][source_id]=copy.deepcopy(result);a['xp_awarded']+=sum(grants.values())
    proposed['audit']['XP_EXTERNAL_AWARDED']=proposed['audit'].get('XP_EXTERNAL_AWARDED',0.)+sum(grants.values())
    state.clear();state.update(proposed);return result

def match_reward(state,log,player_id,opponent_CA,*,exchange=True):
    """Bounded on each path, each match and each half-month, for either actor."""
    existing=ensure(state)['sources'].get('match:'+log['match_id'])
    if existing:
        if existing['evidence_hash']!=log['log_sha256']:raise ValueError('XP_SOURCE_CONFLICT')
        return dict(existing,status='already_applied')
    i=log['participant_ids'].index(player_id);row=log['exposure_by_player'][i]
    own=base.performance_card(state)['CA'];challenge=max(.55,min(1.35,1+(opponent_CA-own)/40))
    quality_rows=log.get('quality_by_player',[{},{}])[i]
    approximate=log.get('source_mode',log.get('mode'))!='full'
    grants={};diagnostics=[];permits={};draws=[]
    fatigue_factor=career.fatigue_factor(state['fatigue'])
    for path,n in sorted(row['usage'].items()):
        if path not in PATHS or n<=0:continue
        q=quality_rows.get(path,{})
        quality=max(0.,min(1.,q.get('quality_factor',.48)))
        errors=q.get('error_rate',None)
        quality*=.55 if approximate else 1.
        success=.10*min(1.,q.get('decisive_successes',0)/3)
        raw=(.20*math.sqrt(n)*quality*challenge+success)*fatigue_factor
        cap=.20*reference_focus_xp(state,path)
        grants[path]=round(min(cap,raw),8)
        if errors is not None and errors>=.18 and n>=4:
            diagnostics.append(dict(path=path,error_rate=errors,contacts=n,confidence='OBSERVED_FULL_CONTACTS',reward=False))
        eligible=(not approximate and n>=8 and challenge>=.9 and quality>=.75 and q.get('decisive_successes',0)>=1)
        if eligible:
            d=career.rng_for(state['seed'],'match-breakthrough',log['match_id'],path).randint(1,100)
            granted=d<=2
            draws.append(dict(path=path,D100=d,threshold=2,granted=granted))
            if granted:permits[path]=1
    account=ensure(state);phase_key=f"{state['month']}:{state['training_release']['phase']}"
    used=account['match_phase_awards'].get(phase_key,0.)
    limit=min(12.,.25*sum(sorted((reference_focus_xp(state,p) for p in PATHS),reverse=True)[:4]))
    total=min(8.,max(0.,limit-used));scale=min(1.,total/max(sum(grants.values()),1e-12))
    grants={p:round(v*scale,8) for p,v in grants.items() if v*scale>1e-12}
    if not grants:permits={}
    reward=award_xp(state,'match:'+log['match_id'],grants,source_kind='MATCH_APPROXIMATE' if approximate else 'MATCH_OBSERVED',evidence_hash=log['log_sha256'],exchange=exchange,permits=permits)
    if reward['status']!='already_applied':ensure(state)['match_phase_awards'][phase_key]=used+sum(grants.values())
    reward.update(approximate=approximate,per_path_reference_cap_ratio=.20,per_match_total_cap=8.,phase_cap=limit,
        challenge=challenge,diagnostics=diagnostics,breakthrough_draws=draws,
        breakthrough_semantics='ONE_PERMIT_ONLY_AT_MOST_2_PERCENT_ELIGIBLE_PATH; NO_DIRECT_G_PA')
    ensure(state)['sources']['match:'+log['match_id']]=copy.deepcopy(reward)
    return reward

def development_reward(state,kind,paths,source_id,evidence_hash,*,quality=1.,exchange=False):
    config={'observation':(8,.10,.60,1.2),'participation':(4,.20,.80,1.5),'champion':(2,.30,1.20,3.),'breakthrough':(6,.20,.80,1.5),'legacy_streak':(1,.30,.60,1.5)}
    if kind not in config or not 0<=quality<=1 or not paths or len(paths)>3 or len(set(paths))!=len(paths) or not set(paths)<=PATHS:
        raise ValueError('valid bounded development reward required')
    account=ensure(state);existing=account['sources'].get(source_id)
    request_hash=hashlib.sha256(canonical_json([kind,paths,quality,evidence_hash]).encode()).hexdigest()
    if existing:
        if existing.get('evidence_hash')!=evidence_hash or account['development_requests'].get(source_id)!=request_hash:raise ValueError('XP_SOURCE_CONFLICT')
        return dict(existing,status='already_applied')
    recent=[x for x in account['development_awards'] if x['month']>=state['month']-11]
    limit,lo,hi,total_cap=config[kind]
    if sum(x['kind']==kind for x in recent)>=limit:raise ValueError('DEVELOPMENT_ROLLING_BUDGET_EXHAUSTED')
    if any(x['evidence_hash']==evidence_hash and x['kind']==kind for x in account['development_awards']):raise ValueError('DUPLICATE_DEVELOPMENT_EVIDENCE')
    amount=lo+(hi-lo)*quality;budget=max(0.,12-sum(x['total'] for x in recent))
    total=min(amount*len(paths),total_cap,budget)
    if total<=0:raise ValueError('DEVELOPMENT_YEAR_XP_BUDGET_EXHAUSTED')
    grants={p:total/len(paths) for p in paths}
    result=award_xp(state,source_id,grants,source_kind=kind,evidence_hash=evidence_hash,exchange=exchange)
    ensure(state)['development_requests'][source_id]=request_hash
    ensure(state)['development_awards'].append(dict(kind=kind,month=state['month'],source_id=source_id,evidence_hash=evidence_hash,total=total))
    result.update(per_path_range=[lo,hi],event_cap=total_cap,rolling12_count_cap=limit,all_development_rolling12_XP_cap=12.)
    return result

def settle_phase(state,*args,**kwargs):
    ensure(state);return base.settle_phase(state,*args,**kwargs)
def settle_month(state,*args,**kwargs):
    ensure(state);return base.settle_month(state,*args,**kwargs)
def load_state(blob):
    s=base.load_state(blob);a=ensure(s)
    if a.get('version')!=VERSION or not math.isfinite(a['xp_awarded']) or a['xp_awarded']<0:raise ValueError('invalid V1.18 XP integration ledger')
    awarded=sum(sum(x.get('grants',{}).values()) for x in a['sources'].values())
    expected=a['initial_xp_total']+(s['audit'].get('XP_FOCUS',0)+s['audit'].get('XP_GENERAL',0)-a['initial_training_awards'])+a['xp_awarded']-(s['audit'].get('XP_SPENT',0)-a['initial_spent'])
    if abs(awarded-a['xp_awarded'])>1e-5 or abs(expected-sum(s['xp'].values()))>1e-5:raise ValueError('FORMAL_XP_CONSERVATION_MISMATCH')
    return s

dump_state=base.dump_state
performance_card=base.performance_card
prepare_card=base.prepare_card
