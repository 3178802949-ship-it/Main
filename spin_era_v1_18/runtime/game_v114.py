"""V1.1.4 INTEGRATED TEST: expanded causal technique decision adapter.
Monkeypatches the isolated V1.1.3 process only for the synchronous play_match call;
no modifications to other imports or historical record. Nonphysical hypothesis.
"""
import game_v113 as v113
import game_v112 as v112
import math
from collections import Counter
TECH={
 'push_short':('table.short','摆短'),'push_long':('table.push','劈长'),
 'push_side':('table.placement','侧向摆短'),'push_middle':('table.short','中路短球'),
 'fh_flip_short':('table.flick','正手挑打'),'bh_flip_short':('table.flick','反手挑打'),
 'bh_open_twist':('receive.initiative','反手拧拉'),
 'fh_half_open':('fh.spin','正手拉半出台'),'bh_half_open':('bh.spin','反手拉半出台'),
 'fh_attack_half':('fh.continuity','正手冲半出台'),'bh_attack_half':('bh.continuity','反手冲半出台'),
 'fh_attack_punch':('fh.power','正手中路弹击'),'bh_attack_punch':('bh.power','反手中路弹击'),
 'fh_open':('fh.spin','正手起下旋'),'bh_open':('bh.spin','反手起下旋'),
 'block':('bh.defense','挡球'),'chop':('table.chop_control','削球')}
NEW_SERVES={
 'half_long_fh_under':dict(zone='fh_half',spin='back',style='pendulum',mechanism='半出台下旋，引诱接发方犹豫摆短或起板'),
 'half_long_bh_side':dict(zone='bh_half',spin='side_back',style='reverse_pendulum',mechanism='半出台侧下旋，考验反手起板与转位'),
 'half_long_mid_dead':dict(zone='middle_half',spin='dead',style='backhand',mechanism='中路半出台不转，测试长短判断'),
 'fast_long_body':dict(zone='middle_long',spin='top',style='backhand',mechanism='奔中路限制侧身，接发可以反击'),
 'short_no_spin_fh':dict(zone='fh_short',spin='dead',style='reverse_pendulum',mechanism='正手短不转，诱导搓高或挑打'),
 'short_bh_underspin':dict(zone='bh_short',spin='back',style='backhand',mechanism='反手短下旋，争取接发劈长后的起下旋')}
ALL_SERVES={**v113.SERVE_PLANS,**NEW_SERVES}
GROUP={'push':(.22,.38,.19,.06,.15),'flip':(.24,.23,.12,.28,.13),'open':(.25,.07,.14,.37,.17),
 'attack':(.18,.07,.13,.43,.19),'block':(.18,.15,.19,.36,.12),'chop':(.12,.27,.22,.24,.15)}
_serve=v113.serve_policy;_choose=v113.choose_action;_quality=v112._older_quality;_explain=v113.explain_point

def proficiency(card,st,action):
 g,k=TECH.get(action,('table.short',''))[0].split('.');child=card['children'][g][k]
 typ='push' if action.startswith('push_') else 'flip' if 'flip' in action or 'twist' in action else 'open' if 'open' in action else 'attack' if 'attack' in action else 'chop' if action=='chop' else 'block'
 w=GROUP[typ];wing='fh' if action.startswith('fh_') else 'bh'
 v=[v112.gg(card,st,x) for x in ('receive','table','read',wing)]+[child]
 return sum(a*b for a,b in zip(w,v))

def choose_from(card,st,pos,rng,actions,base_weights):
 weights=[]
 for action,baseline in zip(actions,base_weights):
  skill=proficiency(card,st,action)
  factor=max(.45,min(2.,math.exp((skill-118)/35)))
  if st['policy']=='receive_initiative' and any(z in action for z in ('flip','open','attack')):factor*=1.25
  if st['policy']=='defensive_pivot' and action.startswith('push_'):factor*=1.20
  if pos=='limited' and any(z in action for z in ('open','attack','twist')):factor*=.58
  weights.append(baseline*factor)
 return rng.choices(actions,weights=weights)[0]

def receive_action(card,st,ball,pos,rng):
 sp=ball['spin'];length=ball.get('length','long');wing=ball['landed'];under=sp in ('back','side_back')
 if pos=='bad':return choose_from(card,st,pos,rng,['push_long','block','push_short'],[.62,.25,.13])
 if length=='short':
  if under:acts=['push_short','push_long','push_side','fh_flip_short','bh_flip_short','bh_open_twist'];w=[.30,.24,.10,.12,.14,.10]
  elif sp=='dead':acts=['push_short','push_long','fh_flip_short','bh_flip_short','push_middle'];w=[.25,.15,.24,.26,.10]
  else:acts=['fh_flip_short','bh_flip_short','push_short','push_long','bh_open_twist'];w=[.31,.30,.19,.12,.08]
  w=[x*(1.27 if a.startswith(wing+'_') else .82 if a.startswith(('fh_' if wing=='bh' else 'bh_')) else 1) for a,x in zip(acts,w)] if wing in ('fh','bh') else w
 elif length=='half':
  if under:acts=['fh_half_open','bh_half_open','push_long','push_short','bh_open_twist'];w=[.30,.34,.23,.09,.04]
  else:acts=['fh_attack_half','bh_attack_half','fh_half_open','bh_half_open','push_long'];w=[.28,.28,.19,.19,.06]
 elif under:acts=['fh_open','bh_open','push_long','fh_attack_punch','bh_attack_punch'];w=[.32,.37,.18,.06,.07]
 else:acts=['fh_attack_half','bh_attack_half','block','fh_attack_punch','bh_attack_punch'];w=[.29,.29,.12,.14,.16]
 return choose_from(card,st,pos,rng,acts,w)

def serve_policy(card,st,rng):
 if rng.random()<.21:
  keys=list(NEW_SERVES)
  ws=[1.1 if 'half' in NEW_SERVES[k]['zone'] and v112.gg(card,st,'read')>120 else 1 for k in keys]
  k=rng.choices(keys,weights=ws)[0];st['serve_intents'][k]+=1;st['serve_intent_name']=k
  p=NEW_SERVES[k];return p['zone'],p['spin'],p['style']
 return _serve(card,st,rng)

def choose_action(card,st,ball,pos,rng):
 if ball.get('origin')=='service' and ball.get('third_phase')=='receive':return receive_action(card,st,ball,pos,rng)
 if ball.get('origin')=='service_return' and pos in ('good','limited'):
  if ball.get('length')=='half':return choose_from(card,st,pos,rng,['fh_half_open','bh_half_open','fh_attack_half','bh_attack_half','push_long'],[.29,.29,.16,.16,.10])
  if ball.get('length')=='short':return choose_from(card,st,pos,rng,['push_short','push_side','fh_flip_short','bh_flip_short'],[.42,.20,.18,.20])
  if ball['spin']=='back':return choose_from(card,st,pos,rng,['fh_open','bh_open','push_long','fh_attack_punch'],[.48,.24,.20,.08])
 return _choose(card,st,ball,pos,rng)

ALIASES={'fh_flip_short':'flip','bh_flip_short':'flip','bh_open_twist':'bh_open','fh_half_open':'fh_open','bh_half_open':'bh_open',
 'fh_attack_half':'fh_attack','bh_attack_half':'bh_attack','fh_attack_punch':'fh_attack','bh_attack_punch':'bh_attack'}
def shot_quality(card,st,ball,pos,action,rng,step,clutch=False):
 q,pace,spin=_quality(card,st,ball,pos,ALIASES.get(action,action),rng,step,clutch)
 if action in TECH:
  q+=max(-4,min(4,(proficiency(card,st,action)-120)*.115))
  if '_half_' in action:q-=2.3
 return round(q,2),pace,spin

def explain(point):
 r=_explain(point)
 for s in point.get('shots',[]):
  if s.get('action') in TECH:s['technique_label']=TECH[s['action']][1];s['technique_path']=TECH[s['action']][0]
 first=point.get('shots',[{}])[0]
 if r['plan']=='mixed_serve':
  for name,v in NEW_SERVES.items():
   if (v['zone'],v['spin'],v['style'])==(first.get('zone'),first.get('spin'),first.get('style')):
    r['plan']=name;r['intended_mechanism']=v['mechanism'];break
 return r

def play_match(cards,seed,**kwargs):
 old={k:getattr(v113,k) for k in ('serve_policy','choose_action','receive_action','explain_point')};oq=v112._older_quality
 try:
  for k,v in {'serve_policy':serve_policy,'choose_action':choose_action,'receive_action':receive_action,'explain_point':explain}.items():setattr(v113,k,v)
  v112._older_quality=shot_quality
  m=v113.play_match(cards,seed,**kwargs)
 finally:
  v112._older_quality=oq
  for k,v in old.items():setattr(v113,k,v)
 m['engine']='V114_EXPANDED_CAUSAL_DECISION_TEST'
 if kwargs.get('keep_points'):
  cnt=Counter(s['action'] for gm in m['games'] for pt in gm['points'] for s in pt['shots'] if s.get('action') in TECH)
  m['technique_distribution']=dict(cnt)
 return m
