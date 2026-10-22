"""Long-term career stress model (EXPERIMENTAL), no real athlete history modifications.
Two monthly training phases; phase=two technical focus subskills and one P6; each 2 D100.
43-skill XP, a separate permanent P6 vector, multidimensional physical limits,
individual maturation/aging onset and exceptional champion growth windows.
"""
from __future__ import annotations
import math,random,copy,hashlib
from collections import Counter
from card_training_v112 import physical_weights,compute_card,P


def bounded(x,low,high):return max(low,min(high,x))
def sigmoid(x):return 1/(1+math.exp(-bounded(x,-30,30)))
def fixed_aptitude(player,path):
    x=hashlib.sha256(f'V113|{player}|{path}'.encode()).digest()
    return (int.from_bytes(x[:4],'big')/2**32-0.5)*2

def soft_cap(state,path):
    g,k=path.split('.');p=state['P6'];w=physical_weights(path)
    pbase=sum(p[x]*q for x,q in w.items());physical=k in ('power','start','arrival','recover','continuity','defense','spin','flick')
    alpha=.72 if k in ('power','start','arrival') else .58 if physical else .43
    if g in ('stable','read'):alpha=.16
    specialization=state['talents'].get(path,0)
    innate=state['mental_potential'] if g in ('read','stable') else 0
    cap=126 + alpha*(pbase-110) + .36*specialization + innate
    cap+=state['cap_bonus'].get(path,0)
    if k=='power':cap=min(cap,126+.90*max(0,p['strength']-112)+.15*max(0,p['burst']-112))
    if k in ('start','arrival'):cap=min(cap,127+.92*max(0,p['speed']-112)+.15*max(0,p['burst']-112))
    return bounded(int(round(cap)),96,150)

def xp_cost(v):
    # Smooth acceleration, continuously differentiable at 116 and 134.
    return round(7+.13*(v-90)+.035*max(0,v-116)**2+.055*max(0,v-134)**2,2)
def permissions(v):
    return 0 if v<128 else 1 if v<138 else 2 if v<145 else 3

def init_career(schema,player_id,*,talent='elite',seed=1):
    r=random.Random(seed);kids={g:{k:r.randint(111,117) for k in sub} for g,sub in schema['subskill_weights_pct'].items()}
    p={k:r.randint(108,112) for k in P}; paths=[f'{g}.{k}' for g in kids for k in kids[g]]
    # Inherit external PA only as reference / optional end-game cap, never in XP chance.
    potentials={'developing':(134,142),'elite':(139,148),'generational':(146,150)}
    low,high=potentials[talent]
    return {'player_id':player_id,'children':kids,'P6':p,'PA':200 if talent=='generational' else 188 if talent=='elite' else 172,
        'body_potential':{k:r.uniform(low,high) for k in P},
        'talents':{path:round(r.gauss(4 if talent=='elite' else 8 if talent=='generational' else 1,4),2) for path in paths},
        'mental_potential':r.uniform(0,3 if talent!='generational' else 6),
        'xp':dict.fromkeys(paths,0.),'permits':dict.fromkeys(paths,0),'p_xp':dict.fromkeys(P,0.),
        'cap_bonus':{},'maturation_midpoint':r.uniform(19.5,23.5),
        'decline_onset':r.uniform(27.8,31.1) if talent!='generational' else r.uniform(29.5,33.7),
        'cognitive_onset':r.uniform(35,39), 'injury_burden':0,'fatigue':18.0,'training_peak_until':-1,
        'active_multiplier':1.0, 'audit_summary':Counter(), 'yearly':[]}

def _xp_exchange(state,path):
    g,k=path.split('.');num=0
    while state['children'][g][k]<soft_cap(state,path):
        cur=state['children'][g][k];cost=xp_cost(cur);req=permissions(cur)
        if state['xp'][path]<cost or state['permits'][path]<req:break
        state['xp'][path]-=cost;state['permits'][path]-=req
        state['children'][g][k]+=1;num+=1
    return num

def train_tech(state,path,r,random_gen,multiplier=1):
    g,k=path.split('.');v=state['children'][g][k]
    if r<=10:
        if v<118:direct=random_gen.randint(2,4);xp=0;permission=0
        elif v<128:direct=random_gen.randint(1,2);xp=0;permission=0
        else:direct=0;permission=2 if r<=4 else 1;xp=1
    elif r<=20:
        direct=1 if v<116 else 0;permission=1 if v>=128 else 0;xp=0 if direct else 4
    elif r<=50:direct=0;permission=0;xp=2.5
    else:direct=0;permission=0;xp=1
    state['permits'][path]+=permission
    state['xp'][path]+=xp*multiplier
    state['children'][g][k]=min(soft_cap(state,path),v+direct)
    inc=state['children'][g][k]-v+_xp_exchange(state,path)
    state['audit_summary']['skill_growth']+=inc
    state['audit_summary']['permits_awarded']+=permission
    return inc

def train_body(state,k,roll,multiplier=1):
    xp=4 if roll<=5 else 2 if roll<=20 else 1 if roll<=60 else 0
    state['p_xp'][k]+=xp*multiplier
    v=state['P6'][k]
    cost=round(7+.27*max(0,v-105)+.055*max(0,v-125)**2,2)
    if state['p_xp'][k]>=cost and v<min(150,state['body_potential'][k]):
        state['P6'][k]+=1;state['p_xp'][k]-=cost;state['audit_summary']['body_training_growth']+=1

def _passive(state,age,mode):
    # General routine work outside the two monthly focused sessions: minor XP only.
    routine={'conservative':.40,'balanced':.80,'intensive':1.20,'generational':1.55}[mode]
    age_factor=bounded(1.12-.055*max(0,age-29),.24,1.1)
    for path in state['xp']:
        state['xp'][path]+=routine*age_factor
        _xp_exchange(state,path)

def _mature_and_age(state,age,r):
    onset=state['decline_onset'];mid=state['maturation_midpoint']
    # Smooth youth growth opportunity, not hard age-bracket jump.
    dev_gate=1-sigmoid((age-mid)/2.8)
    for p in P:
        cur=state['P6'][p];potential=state['body_potential'][p]
        if age<29 and cur<potential:
            chance=bounded((potential-cur)*(.0078 if state['PA']==200 else .0059)*dev_gate,0,.31)
            if r.random()<chance:
                state['P6'][p]+=1;state['audit_summary']['body_maturation_growth']+=1
        # Smooth physiological decline; each P decays differently.
        if age>onset:
            vulnerabilities={'speed':1.4,'burst':1.45,'strength':.8,'stamina':.68,'agility':1.22,'flexibility':.76}
            prob=.020*(age-onset+.5)**1.20*vulnerabilities[p]
            if r.random()<min(.5,prob):state['P6'][p]=max(60,state['P6'][p]-1);state['audit_summary']['body_age_loss']+=1
    for group in state['children']:
        for k in state['children'][group]:
            path=f'{group}.{k}';old=state['children'][group][k];ca_onset=state['cognitive_onset'] if group in ('read','stable') else onset+.8
            if age>ca_onset:
                d=.0135*(age-ca_onset+.5)**1.23 * (0.58 if group in ('read','stable') else 1)
                if r.random()<min(.30,d):state['children'][group][k]=max(65,old-1);state['audit_summary']['skill_age_loss']+=1
            # Falling physical potential can erode highly specialized output, but not instantly.
            cap=soft_cap(state,path)
            if state['children'][group][k]>cap and age>onset and r.random()<.12:
                state['children'][group][k]-=1;state['audit_summary']['cap_erosion']+=1

def simulate_career(schema,seed=1,mode='balanced',talent='elite',start=16,stop=40,record_yearly=True):
    r=random.Random(seed);state=init_career(schema,f'synthetic_{seed}_{talent}',talent=talent,seed=seed)
    paths=list(state['xp'])
    priority=['bh.continuity','bh.defense','receive.spin_read','receive.control','fh.power','fh.continuity','feet.start','feet.recover','serve.placement','read.choice','stable.pressure']
    weights=[3.2 if x in priority else 1.0 for x in paths]
    for mi in range((stop-start)*12):
        age=start+mi/12
        _mature_and_age(state,age,r)
        # Temporary champion-driven growth: NOT guaranteed, even for generational talent.
        if mi%12==0 and 20<=age<=34 and r.random()<({'developing':.035,'elite':.12,'generational':.27}[talent]):
            state['training_peak_until']=mi+3;target=r.choice(paths);state['cap_bonus'][target]=min(2,state['cap_bonus'].get(target,0)+1)
            state['audit_summary']['champion_windows']+=1
        mult=1.5 if mi<state['training_peak_until'] else 1.
        # injury temporarily skips a phase and can have a permanent burden.
        injury_chance=.0025+.0009*max(0,age-30)+.00012*max(0,state['fatigue']-45)
        if r.random()<injury_chance:
            state['injury_burden']+=1;state['audit_summary']['injuries']+=1;phases=1
        else:phases=2
        for phase in range(phases):
            chosen=[r.choices(paths,weights=weights,k=1)[0]]
            others=[x for x in paths if x!=chosen[0]]
            chosen.append(r.choices(others,weights=[weights[paths.index(x)] for x in others],k=1)[0])
            k=r.choice(P)
            for path in chosen:
                for _ in range(2):train_tech(state,path,r.randint(1,100),r,multiplier=mult)
            for _ in range(2):train_body(state,k,r.randint(1,100),multiplier=mult)
            state['fatigue']=bounded(state['fatigue']+r.uniform(3,6)*mult,0,100)
        state['fatigue']=bounded(state['fatigue']-r.uniform(7,12),0,100)
        _passive(state,age,mode)
        if (mi+1)%12==0 and record_yearly:
            calc=compute_card(state,schema)
            state['yearly'].append({'age':start+(mi+1)//12,'CA':calc['CA_calculated'],'Gmean':round(sum(calc['G9'].values())/9,2),
                'Pmean':round(sum(state['P6'].values())/6,2),'P6':state['P6'].copy(),
                'G9':calc['G9'].copy(),'injuries':state['audit_summary']['injuries'],'fatigue':round(state['fatigue'],1)})
    return state
