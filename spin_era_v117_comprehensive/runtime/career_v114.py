"""Spin Era V1.1.4 experimental persistent G43 / P6 career study.
18y start derived from immutable era snapshots; separate PA, learnability,
neuromotor aptitude, body ceiling, individual decline, 2 monthly training phases.
Never write back to source snapshots. Synthetic competition exposure not actual matches.
"""
import random,math,copy,statistics
from collections import Counter
from card_training_v112 import P, physical_weights,compute_card
clamp=lambda v,a,b:max(a,min(b,v))
def sigmoid(x):return 1/(1+math.exp(-clamp(x,-30,30)))
def learning_multiplier(pa,strength=.65):return round(1+strength*clamp((pa-150)/50,0,1)**1.08,4)
def xp_cost(v):return round(7+.13*(v-90)+.035*max(0,v-116)**2+.055*max(0,v-134)**2,2)
def permits(v):return 0 if v<128 else 1 if v<138 else 2 if v<145 else 3
ARCH={
 'fan':dict(body_max=[148,150,150,148,146,142],mental=14.,talent=13.5,decline=27.6,grace=1.45,routine=2.2,body_rate=.028,transfer=.18,focus=['bh.continuity','bh.power','bh.spin','receive.initiative','fh.power','feet.start','feet.recover']),
 'ma':dict(body_max=[147,148,145,147,149,146],mental=19.,talent=12.,decline=31.8,grace=.94,routine=2.30,body_rate=.030,transfer=.19,focus=['fh.continuity','fh.spin','fh.placement','serve.placement','table.short','read.choice','read.opponent_read','feet.recover','stable.sustain']),
 'ordinary':dict(body_max=[130,131,130,133,133,131],mental=5.,talent=2.,decline=30.,grace=1.,routine=1.16,body_rate=.009,transfer=.02,focus=['receive.control','bh.continuity','fh.spin','feet.arrival','read.choice'])}
def age18_card(profiles,schema,pid,years,age18,pa_range):
 a=next(x for x in profiles if x['player_id']==pid and x['year']==years[0]);b=next(x for x in profiles if x['player_id']==pid and x['year']==years[1]);t=(age18-years[0])/(years[1]-years[0]);
 child={g:{k:round(v*(1-t)+b['children'][g][k]*t) for k,v in d.items()} for g,d in a['children'].items()}
 p={k:round(a['P6'][k]*(1-t)+b['P6'][k]*t) for k in P}
 pa=b['PA'];ca=compute_card({'children':child,'P6':p,'PA':pa},schema)['CA_calculated']
 return {'player_id':pid+'_age18','archetype':'fan' if pid=='fan_zhendong' else 'ma','children':child,'P6':p,'PA':pa,'pa_range':pa_range,'CA':ca,'origin':'MODEL_INTERPOLATION_NOT_HISTORICAL'}
def ordinary_card(schema,seed=556):
 r=random.Random(seed);child={g:{k:r.randint(110,116) for k in sub} for g,sub in schema['subskill_weights_pct'].items()};p={k:r.randint(107,111) for k in P}
 return {'player_id':'synthetic_elite_18','archetype':'ordinary','children':child,'P6':p,'PA':181,'pa_range':[175,186],'CA':compute_card({'children':child,'P6':p,'PA':181},schema)['CA_calculated'],'origin':'SYNTHETIC'}

def initialize(card,seed=1001,strength=.65):
 r=random.Random(seed);a=ARCH[card['archetype']];child=copy.deepcopy(card['children']);p=copy.deepcopy(card['P6']);paths=[f'{g}.{k}' for g in child for k in child[g]]
 return {'id':card['player_id'],'archetype':card['archetype'],'children':child,'P6':p,'PA':card['PA'],'pa_range':card['pa_range'],
  'learning_strength':strength,'P_max':{k:clamp(a['body_max'][i]+r.uniform(-1.8,1.8),p[k],150) for i,k in enumerate(P)},
  'talent':{x:a['talent']+r.gauss(0,3.6)+(2.5 if x in a['focus'] else 0) for x in paths},
  'neuromotor':{x:2 if x in a['focus'] else .75 for x in paths},'mental':a['mental']+r.gauss(0,1.4),
  'xp':dict.fromkeys(paths,0.),'permits':dict.fromkeys(paths,0),'P_xp':dict.fromkeys(P,0.),'cap_bonus':{},
  'decline_age':a['decline']+r.uniform(-1,1),'grace':a['grace'],'focus':a['focus'],
  'maturity_mid':(25.8 if card['archetype']=='fan' else 29.4 if card['archetype']=='ma' else 29.5)-9+r.uniform(-1,1),
  'fatigue':18.,'injuries':0,'events':[],'audit':Counter(),'yearly':[]}

def soft_cap(s,path):
 group,k=path.split('.');p=s['P6'];pw=physical_weights(path);mix=sum(p[x]*w for x,w in pw.items())
 alpha=.12 if group in ('read','stable') else .71 if k in ('power','start','arrival') else .52 if k in ('continuity','defense','spin','flick') else .40
 cap=126+alpha*(mix-110)+.36*s['talent'][path]+(s['mental'] if group in ('read','stable') else 0)+s['cap_bonus'].get(path,0)
 if k not in ('power','start','arrival') and group not in ('read','stable'):cap+=.78*s['neuromotor'][path]
 if k=='power':cap=min(cap,126+.90*max(0,p['strength']-112)+.15*max(0,p['burst']-112))
 if k in ('start','arrival'):cap=min(cap,127+.92*max(0,p['speed']-112)+.15*max(0,p['burst']-112))
 return int(clamp(round(cap),96,150))

def exchange(s,path):
 g,k=path.split('.');n=0
 while s['children'][g][k]<soft_cap(s,path):
  v=s['children'][g][k];cost=xp_cost(v);pm=permits(v)
  if s['xp'][path]+1e-8<cost or s['permits'][path]<pm:break
  s['xp'][path]-=cost;s['permits'][path]-=pm;s['children'][g][k]+=1;n+=1
 s['audit']['XP_REDEEMED_LEVELS']+=n

def tech(s,path,d100,r):
 g,k=path.split('.');v=s['children'][g][k];adj=round(3*clamp((s['PA']-180)/20,0,1));e=max(1,d100-adj)
 xp=0;direct=0;permit=0
 if e<=10:
  if v<118:direct=r.randint(2,4)
  elif v<128:direct=r.randint(1,2)
  else:permit=2 if e<=4 else 1;xp=1
 elif e<=20:
  if v<116:direct=1
  elif v>=128:permit=1;xp=1.5
  else:xp=3
 elif e<=50:xp=2.5
 else:xp=1
 s['xp'][path]+=xp*learning_multiplier(s['PA'],s['learning_strength']);s['permits'][path]+=permit
 s['children'][g][k]=min(soft_cap(s,path),v+direct)
 s['audit']['TECH_D100']+=1;s['audit']['DIRECT_LEVELS']+=s['children'][g][k]-v;s['audit']['BREAKTHROUGHS']+=permit
 exchange(s,path)

def trainP(s,key,roll):
 xp=(4 if roll<=5 else 2 if roll<=20 else 1 if roll<=60 else 0)*learning_multiplier(s['PA'],s['learning_strength']);s['P_xp'][key]+=xp
 v=s['P6'][key];cost=8+.30*max(0,v-108)+.06*max(0,v-129)**2
 if s['P_xp'][key]>=cost and v<s['P_max'][key]:s['P6'][key]+=1;s['P_xp'][key]-=cost;s['audit']['P_FOCUS_GROWTH']+=1
 s['audit']['P_D100']+=1

def natural_and_age(s,age,r):
 a=ARCH[s['archetype']];dev=1-sigmoid((age-s['maturity_mid'])/2.4);after=max(0,age-s['decline_age'])
 for p in P:
  room=s['P_max'][p]-s['P6'][p]
  if room>0 and age<32 and r.random()<clamp(room*a['body_rate']*dev*learning_multiplier(s['PA'],s['learning_strength'])**.58,0,.62):s['P6'][p]+=1;s['audit']['P_MATURITY']+=1
  if after:
   vuln={'speed':1.2,'burst':1.25,'strength':.72,'stamina':.83,'agility':1.03,'flexibility':.78}[p]
   if r.random()<min(.75,.022*(after+.25)**1.18*vuln*s['grace']):s['P6'][p]=max(75,s['P6'][p]-1);s['audit']['P_AGE_LOSS']+=1
 for group,sub in s['children'].items():
  for k in sub:
   path=f'{group}.{k}';older=max(0,age-(s['decline_age']+(3.4 if group in ('read','stable') else 1.4)))
   if older and r.random()<min(.43,.021*(older+.5)**1.22*s['grace']):sub[k]=max(65,sub[k]-1);s['audit']['TECH_AGE_LOSS']+=1
   if sub[k]>soft_cap(s,path) and after and r.random()<.14*s['grace']:sub[k]-=1;s['audit']['CAP_EROSION']+=1

def select_weights(s,paths,age):
 focus=set(s['focus']);out=[]
 for path in paths:
  group,k=path.split('.');w=1+(3.7 if path in focus else 0)
  if s['archetype']=='fan' and age<25 and group=='bh':w*=1.48
  if s['archetype']=='ma' and age>=24 and group in ('read','stable','table'):w*=1.50
  if age>s['decline_age'] and group in ('read','stable'):w*=1.42
  if s['children'][group][k]>=soft_cap(s,path):w*=.45
  out.append(w)
 return out

def passive(s,age,r,general=0):
 a=ARCH[s['archetype']];agef=clamp(1.04-.063*max(0,age-31),.31,1.04)
 for path in s['xp']:
  group,k=path.split('.');af=1.10 if path in s['focus'] else .84 if group in ('read','stable') else .95
  gain=(a['routine']+general)*learning_multiplier(s['PA'],s['learning_strength'])*af*agef;s['xp'][path]+=gain;s['audit']['GENERAL_XP']+=gain
  roll=a['transfer']*(1.34 if age<25 else .90 if age<32 else .43)
  if path in s['focus']:roll*=1.45
  if age>=35:roll*=clamp(1-.10*(age-34),.30,1)
  if s['children'][group][k]>=128 and r.random()<min(.48,roll):s['permits'][path]+=1;s['audit']['GENERAL_PERMIT']+=1
  exchange(s,path)

def synthetic_competition(s,age,r,monthly_usage=4):
 paths=list(s['xp']);weights=select_weights(s,paths,age);chosen=r.choices(paths,weights=weights,k=monthly_usage)
 for path in chosen:
  s['xp'][path]+=(.8+.55*r.random())*learning_multiplier(s['PA'],s['learning_strength'])
  if r.random()<min(.35,ARCH[s['archetype']]['transfer']*.65):s['permits'][path]+=1;s['audit']['COMPETITION_PERMIT']+=1
  exchange(s,path)
 s['audit']['SYNTHETIC_MATCH_USE']+=len(chosen)

def dynamic_pa(s,age,r):
 if 19<=age<=36 and r.random()<.009:
  before=s['PA'];s['PA']=int(clamp(before+(1 if r.random()<(.62 if age<28 else .45) else -1),*s['pa_range']))
  if s['PA']!=before:s['events'].append({'age':round(age,2),'PA_before':before,'PA_after':s['PA'],'type':'scouting_revision'})

def simulate(schema,card,seed=1,strength=.65,stop=40,mode='balanced',monthly_usage=4):
 r=random.Random(seed);s=initialize(card,seed,strength);paths=list(s['xp']);start=18
 for month in range((stop-start)*12):
  age=start+month/12;natural_and_age(s,age,r);dynamic_pa(s,age,r);w=select_weights(s,paths,age)
  for phase in range(2):
   a=r.choices(paths,weights=w,k=1)[0];other=w.copy();other[paths.index(a)]=0;b=r.choices(paths,weights=other,k=1)[0]
   for path in (a,b):
    for i in range(2):tech(s,path,r.randint(1,100),r)
   bodyweights=([2,2.3,1.8,1.4,1.1,.7] if s['archetype']=='fan' else [1.8,1.4,1.,2,2,1.1] if s['archetype']=='ma' else [1]*6)
   key=r.choices(P,weights=bodyweights,k=1)[0]
   for i in range(2):trainP(s,key,r.randint(1,100))
   s['fatigue']=clamp(s['fatigue']+r.uniform(3,6),0,100)
  passive(s,age,r,{'conservative':-.3,'balanced':0,'intensive':.5}.get(mode,0))
  synthetic_competition(s,age,r,monthly_usage)
  s['fatigue']=clamp(s['fatigue']-r.uniform(7.5,11.8),0,100)
  if r.random()<(.0016+.001*max(0,age-30)):
   s['injuries']+=1;s['audit']['INJURIES']+=1
   if s['injuries']>2 and r.random()<.2:s['decline_age']-=.3
  if month%12==11:
   calc=compute_card(s,schema);s['yearly'].append({'age':18+(month+1)//12,'CA':calc['CA_calculated'],
     'G9':calc['G9'],'P6':s['P6'].copy(),'PA':s['PA'],'Pmean':round(sum(s['P6'].values())/6,2),'injuries':s['injuries']})
 return s

def scouting_evidence(s):
 v=sorted((n for sub in s['children'].values() for n in sub.values()),reverse=True)
 return {'physical_mean':round(sum(s['P6'].values())/6,2),'top6_tech_mean':round(sum(v[:6])/6,2),
 'neuromotor_high':round(max(s['neuromotor'].values()),2),'learning_mult':learning_multiplier(s['PA'],s['learning_strength']),
 'principle':'PA range requires body OR technique OR sensory learning evidence; no direct PA-to-G stat increase'}
