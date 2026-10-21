"""Spin Era v1.1 TEST Card + Training unified, transactional and audit-friendly.
All output states in NEW experimental branches; historical snapshot files read-only.
"""
from __future__ import annotations
import copy,hashlib,random,math
P=('speed','burst','strength','stamina','agility','flexibility')
REQUIREMENTS=((120,10,0),(130,15,0),(140,25,1),(150,30,2))
# Each subskill has 1-2 meaningful physical bottlenecks; cognitive skills only
# weakly associated with P6. A declared aptitude belongs to the player/skill.
PHYSICAL={
 'serve.spin':('strength','flexibility'),'serve.disguise':('agility','flexibility'),'serve.placement':('agility','flexibility'),
 'serve.variation':('agility','flexibility'),'serve.third_link':('speed','agility'),
 'receive.spin_read':('flexibility','agility'),'receive.length_read':('speed','agility'),
 'receive.control':('agility','flexibility'),'receive.initiative':('burst','speed'),
 'fh.spin':('burst','flexibility'),'fh.power':('strength','burst'),'fh.continuity':('stamina','agility'),
 'fh.defense':('agility','speed'),'fh.placement':('agility','flexibility'),
 'bh.spin':('burst','flexibility'),'bh.power':('strength','burst'),'bh.continuity':('stamina','agility'),
 'bh.defense':('agility','speed'),'bh.placement':('agility','flexibility'),
 'feet.start':('speed','burst'),'feet.arrival':('speed','agility'),'feet.recover':('stamina','agility'),
 'feet.coordination':('agility','flexibility'),'feet.balance':('agility','strength'),
 'table.short':('agility','flexibility'),'table.push':('agility','flexibility'),
 'table.chop_control':('flexibility','agility'),'table.flick':('burst','flexibility'),
 'table.placement':('agility','flexibility'),
 'stable.variance':('stamina','flexibility'),'stable.sustain':('stamina','agility'),
 'stable.recovery':('stamina','flexibility'),'stable.pressure':('stamina','flexibility'),
 'spirit.improvisation':('agility','flexibility'),'spirit.unorthodox_defense':('agility','flexibility'),
 'spirit.spin_deception':('agility','flexibility'),'spirit.lob_arcs':('flexibility','stamina'),
 'spirit.unexpected_transition':('agility','speed'),
 'read.self_read':('stamina','agility'),'read.opponent_read':('stamina','agility'),
 'read.choice':('stamina','agility'),'read.counter':('stamina','agility'),'read.exploit':('stamina','agility')}
COGNITIVE={'read','stable'}

def aptitude_for(pid,path):
    digest=hashlib.sha256(f'SPIN-ERA-TALENT|{pid}|{path}'.encode()).digest()
    return 2+digest[0]%7 # +2 to +8, fixed per player and subskill

def soft_cap(profile,path,*,championship_cap_bonus=0):
    group,key=path.split('.')
    pa,pb=PHYSICAL[path];p=profile['P6']
    preferred=.72*p[pa]+.28*p[pb]
    alpha=.16 if group in COGNITIVE else .68 if key in ('power','start','arrival','recover','balance') else .46
    cognitive_base=133 if group in COGNITIVE else 128
    cognitive_aptitude=(int.from_bytes(hashlib.sha256(f'COGNITIVE|{profile.get("player_id","player")}|{path}'.encode()).digest()[:2],'big')%9) if group in COGNITIVE else 0
    natural=round(cognitive_base+alpha*(preferred-120)+aptitude_for(profile.get('player_id','player'),path)+cognitive_aptitude+min(2,championship_cap_bonus))
    # Absolute physical requirement on power: Strength=120 can NEVER yield FH power >=140.
    if key=='power': natural=min(natural,139+max(0,p['strength']-120)*.86)
    return int(min(150,max(85,natural)))

def growth_requirement(v):
    if v<120:return {'xp_required':10,'permits_required':0}
    if v<130:return {'xp_required':15,'permits_required':0}
    if v<140:return {'xp_required':25,'permits_required':1}
    return {'xp_required':30,'permits_required':2}

def init_state(profile):
    out={'player_id':profile.get('player_id','anon'),'children':copy.deepcopy(profile['children']),
         'P6':copy.deepcopy(profile['P6']),'PA':profile.get('PA',190),'CA_initial':profile.get('CA'),
         'xp':{f'{g}.{k}':0.0 for g,c in profile['children'].items() for k in c},
         'permits':{f'{g}.{k}':0 for g,c in profile['children'].items() for k in c},
         'championship_cap_bonus':{},'events':{},'audit':[]}
    return out

def train(state,path,roll,seed,training_date,*,event_multiplier=1.0,kind='focused'):
    if not 1<=roll<=100:raise ValueError('D100 out of range')
    g,k=path.split('.');cur=state['children'][g][k];sid=f'{state["player_id"]}|{training_date}|{path}|{seed}'
    if sid in state['events']:raise ValueError('TRAINING_DUPLICATE_EVENT_ID')
    # Transactional; commit only after successful computation
    proposed=copy.deepcopy(state)
    x=proposed['xp'][path];perm=proposed['permits'][path]
    profile={'P6':proposed['P6'],'player_id':proposed['player_id']}
    cap=soft_cap(profile,path,championship_cap_bonus=proposed['championship_cap_bonus'].get(path,0))
    direct=0;xp_gain=0;permit_gain=0;bonus_roll=None
    r=random.Random(int.from_bytes(hashlib.sha256(f'{seed}|{sid}|DIRECT'.encode()).digest()[:8],'big'))
    if roll<=10:
        if cur<120:
            bonus_roll=r.randint(2,4);direct=bonus_roll
        else:
            permit_gain=2 if roll<=5 else 1
            xp_gain=2 # Advanced expertise, still requires permits and XP to buy G>=130
    elif roll<=20:
        if cur<120 or 120<=cur<130:direct=1
        else:permit_gain=1
    elif roll<=50:xp_gain=2
    else:xp_gain=1.5
    # Championship peak multiplies earned routine XP, not instantaneous direct G or permits.
    xp_gain*=event_multiplier
    proposed['permits'][path]+=permit_gain; proposed['xp'][path]+=xp_gain
    before=cur
    direct_applied=min(max(0,cap-cur),direct)
    cur+=direct_applied
    if direct>direct_applied:proposed['audit'].append({'event':sid,'direct_blocked_by_P_cap':direct-direct_applied})
    exchanges=[]
    while cur<cap and cur<150:
        req=growth_requirement(cur)
        if proposed['xp'][path]+1e-9<req['xp_required'] or proposed['permits'][path]<req['permits_required']:break
        proposed['xp'][path]=round(proposed['xp'][path]-req['xp_required'],6)
        proposed['permits'][path]-=req['permits_required'];cur+=1
        exchanges.append({'target':cur,'xp_spent':req['xp_required'],'permits_spent':req['permits_required']})
    proposed['children'][g][k]=cur
    entry={'id':sid,'date':training_date,'path':path,'D100':roll,'secondary_direct_roll':bonus_roll,
          'starting_value':before,'cap_from_P6':cap,'event_multiplier':event_multiplier,
          'xp_awarded':xp_gain,'direct_awarded':direct_applied,'permit_awarded':permit_gain,
          'exchanges':exchanges,'end_value':cur,'xp_balance':proposed['xp'][path],
          'permit_balance':proposed['permits'][path],'kind':kind}
    proposed['events'][sid]=entry;proposed['audit'].append(entry)
    state.clear();state.update(proposed)
    return entry

def champion_event(state,event_id,date,seed,major=True):
    if event_id in state['events']:raise ValueError('CHAMPION_EVENT_ALREADY_USED')
    r=random.Random(int.from_bytes(hashlib.sha256(f'{seed}|{event_id}|CHAMP'.encode()).digest()[:8],'big'))
    window=3 if major else 1
    # Big win opens a temporary growth window, not automatic double experience in every worldline.
    xp_multiplier=1.5 if major else 1.25
    eligible=[f'{g}.{k}' for g,c in state['children'].items() for k in c]
    chosen=r.choice(eligible)
    cap_roll=r.randint(1,100);cap_bonus=1 if cap_roll<=70 else 2 if cap_roll<=85 else 0
    pa_roll=r.randint(1,100);pa_change=int(pa_roll<=8 and state['PA']<200)
    state['PA']+=pa_change
    state['championship_cap_bonus'][chosen]=min(2,state['championship_cap_bonus'].get(chosen,0)+cap_bonus)
    e={'event':event_id,'date':date,'xp_multiplier':xp_multiplier,'months':window,'target':chosen,'soft_cap_bonus':cap_bonus,
       'PA_roll':pa_roll,'PA_delta':pa_change,'source':'SIMULATED_CHAMPION_EVENT_NOT_AUTOMATIC'}
    state['events'][event_id]=e;state['audit'].append(e)
    return e


def compute_card(state,schema):
    """CA is OUTPUT ONLY; never feeds back into training odds/softcaps/shot quality."""
    from decimal import Decimal, ROUND_HALF_UP
    def round_up(x):return int(Decimal(str(x)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    def weighted(a,w):return round_up(sum(Decimal(str(a[k]))*Decimal(str(v)) for k,v in w.items())/100)
    g={k:weighted(state['children'][k],schema['subskill_weights_pct'][k]) for k in schema['core_order']}
    ga=weighted(g,schema['core_weights_pct']);pa=weighted(state['P6'],schema['body_weights_pct'])
    ca=round_up(4*(65*ga+35*pa)/300)
    return {'G9':g,'G_aggregate':ga,'P_aggregate':pa,'CA_calculated':ca,'PA':state['PA'],
            'CA_effective':min(ca,state['PA']),'classification':'P6+43_CHILDREN_DERIVED_NO_CA_FEEDBACK'}

def active_training_multiplier(state,year_month):
    """One peak per event; first calendar month includes the championship month.
    Consecutive, overlapping peaks take max multiplier, never multiply each other.
    """
    y,m=map(int,year_month.split('-'))
    ix=y*12+m
    candidates=[1.0]
    for e in state['events'].values():
        if not isinstance(e,dict) or 'xp_multiplier' not in e:continue
        ey,em=map(int,e['date'][:7].split('-'))
        if ey*12+em<=ix<ey*12+em+e['months']:candidates.append(e['xp_multiplier'])
    return max(candidates)

# V1.1.2 revised multi-to-multi P6 influence; does NOT rewrite frozen historic snapshots.
# Every G subskill depends on three P attributes with normalized weights.
P_MULTI = {
 'power':('strength','burst','agility'),
 'spin':('flexibility','burst','strength'),
 'placement':('agility','flexibility','speed'),
 'continuity':('stamina','agility','speed'),
 'defense':('agility','speed','flexibility'),
 'spin_read':('flexibility','speed','agility'),
 'length_read':('speed','agility','flexibility'),
 'initiative':('burst','speed','agility'),
 'control':('agility','flexibility','speed'),
 'third_link':('speed','agility','burst'),
 'start':('speed','burst','agility'),
 'arrival':('speed','agility','stamina'),
 'recover':('stamina','agility','speed'),
 'coordination':('agility','flexibility','speed'),
 'balance':('agility','strength','flexibility'),
 'short':('agility','flexibility','speed'),
 'push':('agility','flexibility','strength'),
 'chop_control':('flexibility','agility','stamina'),
 'flick':('burst','flexibility','agility'),
}

def physical_weights(path):
    g,k=path.split('.')
    if k in P_MULTI:attrs=P_MULTI[k]
    else:
        a,b=PHYSICAL[path];third=('speed' if a!='speed' and b!='speed' else 'agility' if 'agility' not in (a,b) else 'stamina')
        attrs=(a,b,third)
    # Fixed three-weight scheme. Physical ceiling formed by *combination* of P fields.
    weights=(.55,.30,.15) if k in ('power','start','arrival','recover') else (.50,.30,.20)
    return dict(zip(attrs,weights))

def soft_cap(profile,path,*,championship_cap_bonus=0):
    group,key=path.split('.');p=profile['P6']
    phys=sum((p[k]-120)*w for k,w in physical_weights(path).items())
    aptitude=aptitude_for(profile.get('player_id','player'),path)-3
    if group in COGNITIVE:
        # Tactical reading and psychological resilience not primarily determined by P.
        cap=131+.14*phys+aptitude
    else:
        alpha=.83 if key in ('power','start','arrival','recover') else .62 if key in ('spin','continuity','defense') else .52
        cap=131+alpha*phys+aptitude
    cap+=min(2,championship_cap_bonus)
    if key=='power':
        # At permanent strength 120 a force/power skill cannot reach 140,
        # regardless of elite agility or external fame.
        cap=min(cap,138+max(0,p['strength']-120)*.78)
    if key in ('start','arrival'):
        cap=min(cap,138+max(0,p['speed']-120)*.72)
    return int(max(85,min(150,round(cap))))

# Training engine's train() invokes soft_cap at execution time and thereby uses this patch.
