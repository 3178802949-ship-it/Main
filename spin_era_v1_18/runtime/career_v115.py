"""Spin Era 1.1.5 43 independent aptitudes + dynamic scouting PA + five overlapping age curves.
Candidate only. Calibrate population distributions; never modify existing archived careers.
Month: two phases * (two G43 techniques + one P6) * two D100; limited passive
budget and synthetic match exposure clearly segregated. No CA feedback to growth.
"""
import random,copy,math,statistics
from collections import Counter
import career_v114 as old
from card_training_v112 import P,compute_card
clamp=old.clamp
CURVES={
 'early_accelerator':dict(label='前期高速成长',peak=(27.6,1.7),decline=(28.7,1.8),rate=1.05,bodyloss=1.10,technical=.90,focus_early=1.30),
 'foundation_builder':dict(label='厚积稳进',peak=(30.3,1.6),decline=(30.6,1.6),rate=.93,bodyloss=.88,technical=1.06,focus_early=.90),
 'balanced_progress':dict(label='均衡成长',peak=(29.0,1.75),decline=(29.1,1.9),rate=1.,bodyloss=1.,technical=1.,focus_early=1.),
 'late_breakthrough':dict(label='中后期突破',peak=(31.0,1.7),decline=(30.8,1.7),rate=.86,bodyloss=.95,technical=1.12,focus_early=.82),
 'skill_specialist':dict(label='专项技术型',peak=(29.2,1.8),decline=(29.4,2.0),rate=.96,bodyloss=1.05,technical=1.12,focus_early=1.05)
}
# Five types are mild priors with broad overlapping gaussian parameter draws,
# never immutable age buckets. Phenotype and PA are separate random variables.

def pa_xp_mult(pa):
    # 5 PA points -> 1.5-2.0% learning change (gentle).
    return round(clamp(1+.0035*(pa-150),.91,1.18),4)

def start(card,seed=1,curve='balanced_progress',ranked=0):
    if curve not in CURVES:raise ValueError(curve)
    r=random.Random(seed);s=old.initialize(card,seed=seed,strength=.0)
    data=CURVES[curve];s['curve']=curve
    s['peak_age']=clamp(r.gauss(*data['peak']),25.0,33.2)
    s['decline_age']=clamp(r.gauss(*data['decline']),26.3,32.2)
    s['body_loss_rate']=data['bodyloss'];s['tech_loss_rate']=data['technical']
    s['activity_rate']=data['rate'];s['early_focus']=data['focus_early']
    s['scouting_PA_centre']=card['PA'];s['pa_range']=list(card.get('pa_range',(max(120,card['PA']-4),min(200,card['PA']+4))))
    s['learning_factor']={};s['style_preference']={};s['aptitude_group']={}
    group_shifts={g:r.gauss(0,.035) for g in card['children']}
    for path in s['xp']:
        group=path.split('.')[0];tag=1.08 if path in s['focus'] else 1.
        independent=clamp(r.gauss(1.,.075)+group_shifts[group],.77,1.24)
        s['learning_factor'][path]=round(independent*tag,4)
        s['style_preference'][path]=round(clamp(r.lognormvariate(-.035,.24),.40,2.45),3)
        # independent sensory and decision talents; high-BH low-P legal
        s['talent'][path]+=r.gauss(0,3.8)
        if curve=='skill_specialist' and r.random()<.10:s['talent'][path]+=r.uniform(6,12)
    s['PA_evidence']=Counter();s['scouting_events']=[];s['event_dedupe']=set()
    s['peak_ca']=-1;s['peak_ca_age']=18;s['post_peak_ref']={}
    return s

def progress(s,path,d100,r,age):
    g,k=path.split('.');v=s['children'][g][k];oldval=v
    apt=s['learning_factor'][path]
    # Independent skill aptitude shifts success window by at most +-2 pips.
    bias=round(clamp((apt-1)*11,-2,2))
    eff=int(clamp(d100-bias,1,100));xp=0;direct=0;permit=0
    if eff<=10:
        if v<120:direct=r.randint(2,4)
        elif v<128:direct=r.randint(1,2)
        else:permit=2 if eff<=3 else 1;xp=1
    elif eff<=20:
        if v<118:direct=1
        elif v>=128:permit=1;xp=1
        else:xp=2
    elif eff<=50:xp=2.5
    else:xp=1.5
    # CA is output only, PA never directly changes G, only per-subskill XP speed.
    awarded=xp*pa_xp_mult(s['PA'])*apt*s['activity_rate']
    s['xp'][path]+=awarded;s['permits'][path]+=permit
    s['children'][g][k]=min(old.soft_cap(s,path),v+direct)
    old.exchange(s,path)
    s['audit']['TRAINING_ROLLS']+=1;s['audit']['XP_FOCUS']+=awarded
    s['audit']['DIRECT_SKILL_LEVELS']+=s['children'][g][k]-oldval
    if eff<=10:s['PA_evidence']['exceptional_rolls']+=1
    return {'path':path,'roll':d100,'adjusted':eff,'aptitude':apt,'xp_awarded':round(awarded,3),
       'direct':direct,'permit':permit,'old':v,'new':s['children'][g][k],'cap':old.soft_cap(s,path)}

def body_training(s,k,d,r,age):
    xp=(4 if d<=5 else 2 if d<=20 else 1 if d<=60 else 0)
    gain=xp*pa_xp_mult(s['PA'])*s['activity_rate'];s['P_xp'][k]+=gain
    val=s['P6'][k];cost=8+.30*max(0,val-108)+.06*max(0,val-129)**2
    if s['P_xp'][k]>=cost and val<s['P_max'][k]:
        s['P6'][k]+=1;s['P_xp'][k]-=cost;s['audit']['P_FOCUS_GROWTH']+=1
    s['audit']['P_ROLLS']+=1

def common_training(s,age,r):
    # Bounded general training: 12/43 paths per month with NO replacement,
    # athlete-specific priority. Distinct from four focused technical drills.
    paths=list(s['xp']);pool=paths.copy();choices=[]
    for i in range(12):
        weights=priorities(s,age,pool);z=r.choices(pool,weights=weights)[0];choices.append(z);pool.remove(z)
    for path in choices:
        g,k=path.split('.');xp=.82*pa_xp_mult(s['PA'])*s['learning_factor'][path]
        s['xp'][path]+=xp;s['audit']['MAINTENANCE_XP']+=xp;old.exchange(s,path)

def priorities(s,age,paths):
    fs=set(s['focus']);w=[]
    for path in paths:
        group,k=path.split('.');val=s['children'][group][k]
        priority=s['style_preference'][path]*(2.15 if path in fs else 1.)
        if age<23:priority*=s['early_focus']
        if val>=old.soft_cap(s,path):priority*=.26
        if age>30 and group in ('read','stable','table'):priority*=1.12
        w.append(max(.04,priority))
    return w

def aging(s,age,r):
    # First allow normal P maturation, then impose stronger and increasing
    # physical attrition after personal age threshold.
    old.natural_and_age(s,age,r)
    later=max(0,age-s['decline_age'])
    if later<=0:return
    for p in P:
        mult={'speed':1.10,'burst':1.18,'strength':.65,'stamina':.82,'agility':1.08,'flexibility':.88}[p]
        prob=min(.36,.0048*later**1.35*s['body_loss_rate']*mult)
        if r.random()<prob:s['P6'][p]=max(70,s['P6'][p]-1);s['audit']['V115_EXTRA_AGE_P_LOSS']+=1
    for group,sub in s['children'].items():
        for k in sub:
            # Cognition declines more slowly; technique maintenance delays but
            # cannot erase decline; peak may show minor rebounds.
            cognitive=group in ('read','stable');delay=3 if cognitive else 1
            elapsed=max(0,age-(s['decline_age']+delay))
            if elapsed and r.random()<min(.28,.0032*elapsed**1.35*s['tech_loss_rate']*(.46 if cognitive else 1)):
                sub[k]=max(62,sub[k]-1);s['audit']['V115_EXTRA_AGE_G_LOSS']+=1
    # Rare second smaller crest from temporary renewed technical preparation,
    # never artificial free +CA. It manifests via stochastic training normally.

def pa_revision(s,age,r,yearly_excellence,major_title=False):
    # PA is a noisy estimate of latent potential, not physical P, and not a
    # guaranteed ceiling reached by training. No automatic PA increase from CA.
    if major_title:
        ticket=f'GOLD_{int(age*100)}'
        if ticket not in s['event_dedupe']:
            s['event_dedupe'].add(ticket)
            d=r.randint(1,100)
            if d<=12 and s['PA']<s['pa_range'][1]:s['PA']+=1;s['scouting_events'].append({'age':round(age,2),'reason':'major_title','delta':1,'roll':d})
    # Sustained repeated exceptional breakthroughs are evidence once/year.
    if yearly_excellence>=9 and r.random()<.20 and s['PA']<s['pa_range'][1]:
        s['PA']+=1;s['scouting_events'].append({'age':round(age,2),'reason':'sustained_tech_progress','delta':1})
    elif age>=28 and yearly_excellence<=1 and r.random()<.12 and s['PA']>s['pa_range'][0]:
        s['PA']-=1;s['scouting_events'].append({'age':round(age,2),'reason':'scouting_reassessment','delta':-1})

def simulate(schema,card,seed,curve='balanced_progress',stop=40,synthetic_matches_per_month=2):
    r=random.Random(seed);s=start(card,seed,curve);paths=list(s['xp']);excellence=0
    for month in range(12*(stop-18)):
        age=18+month/12
        aging(s,age,r)
        for phase in range(2):
            weights=priorities(s,age,paths)
            a=r.choices(paths,weights=weights,k=1)[0]
            weights[paths.index(a)]=0;b=r.choices(paths,weights=weights,k=1)[0]
            for path in (a,b):
                for _ in range(2):
                    d=r.randint(1,100);progress(s,path,d,r,age);excellence+=int(d<=10)
            pk=r.choices(list(P),weights=[1.2,1.2,1,1.05,1.1,.9])[0]
            for _ in range(2):body_training(s,pk,r.randint(1,100),r,age)
        common_training(s,age,r)
        # Competition experience is separated and DOES NOT fake played wins.
        for path in r.choices(paths,weights=priorities(s,age,paths),k=synthetic_matches_per_month):
            s['xp'][path]+=.4*pa_xp_mult(s['PA']);old.exchange(s,path)
            s['audit']['SYNTHETIC_EXPOSURES']+=1
        if (month+1)%12==0:
            pa_revision(s,age,r,excellence);excellence=0
            result=compute_card(s,schema);ca=result['CA_calculated'];current=18+(month+1)//12
            if ca>s['peak_ca']:s['peak_ca']=ca;s['peak_ca_age']=current
            s['yearly'].append({'age':current,'CA':ca,'PA':s['PA'],'G9':result['G9'],
               'P6':s['P6'].copy(),'curve':s['curve'],'peak_age_prior':round(s['peak_age'],2),'decline_age':round(s['decline_age'],2)})
    return s
