"""Spin Era Game System 1.1 TEST: own, deterministic shot-by-shot state machine.
Independent design experiment; DOES NOT replace frozen v0.16/v1.2 or career history.
A rally state includes landed target, ball spin/pace/quality and receiver readiness.
Every returned shot consumes this state. Both agents use one symmetric algorithm.
"""
from __future__ import annotations
from dataclasses import dataclass,field
from collections import Counter
import random,hashlib,math,copy
G=('serve','receive','fh','bh','feet','read','stable','table','spirit')
P=('speed','burst','strength','stamina','agility','flexibility')

def clamp(x,l,h):return max(l,min(h,x))
def rng_of(*x):return random.Random(int.from_bytes(hashlib.sha256('|'.join(map(str,x)).encode()).digest()[:8],'big'))
def logistic(x):return 1/(1+math.exp(-clamp(x,-20,20)))

def warmup(card,rng,fatigue=25):
    p_roll={k:rng.randint(-4,4) for k in P}
    # Special 20/60/20 psychological logic only via between-game checks.
    g_roll={k:rng.randint(-7,7) for k in G}
    # Stable G reduces extremes slightly rather than granting raw hitting bonus
    stability=card['G9']['stable']
    for k in G:
        if k not in ('stable','read') and rng.random()<clamp((stability-105)*.004,0,.21):
            g_roll[k]=int(g_roll[k]*.55)
        if fatigue>45 and rng.random()<(fatigue-40)/145:
            g_roll[k]-=rng.randint(1,max(1,int((fatigue-35)/10)))
    return {'g_roll':g_roll,'p_roll':p_roll,'form_initial':g_roll.copy(),
            'p_eff':{k:clamp(card['P6'][k]+p_roll[k],0,150) for k in P},
            'read_bonus':0,'stable_bonus':0,'clutch_bonus':0,
            'scouted_weakness':None,'execute_weakness':False,
            'mental':'neutral','match_fatigue':fatigue, 'tactics':Counter(),
            'observations':Counter(), 'game_check_history':[], 'match_stamina':0.0,
            'arousal':0}

def gg(card,st,k):
    # Only G, G daily form, and cognitive modification. Body P used in physical transition,
    # NOT double-counted as global G attack quality modifier.
    b=st['read_bonus'] if k=='read' else st['stable_bonus'] if k=='stable' else 0
    return clamp(card['G9'][k]+st['g_roll'][k]+b,20,157)

def mental_check(rng):
    d=rng.randint(1,100)
    if d<=20:return {'roll':d,'type':'breakthrough','stable_delta':4,'clutch_extra_delta':4}
    if d<=80:return {'roll':d,'type':'normal','stable_delta':rng.randint(-2,2),'clutch_extra_delta':rng.randint(-2,2)}
    return {'roll':d,'type':'collapse','stable_delta':-4,'clutch_extra_delta':-4}

def between_games(cards,state,rng,game_idx):
    checks=[]
    for idx in (0,1):
        card=cards[idx];s=state[idx];opp=state[1-idx];oc=cards[1-idx]
        rolls={k:rng.randint(1,100) for k in ('self','weak','execute')}
        # Purposefully cap situational success: no automatic successes for G>140
        t_self=int(clamp(51+.38*(gg(card,s,'read')-110),25,82))
        t_weak=int(clamp(46+.40*(gg(card,s,'read')-110)-.14*(gg(oc,opp,'read')-110),22,80))
        t_exec=int(clamp(48+.42*(gg(card,s,'read')-110)+.08*(gg(card,s,'stable')-110),24,82))
        ok={k:rolls[k]<={'self':t_self,'weak':t_weak,'execute':t_exec}[k] for k in rolls}
        fix=None
        if ok['self']:
            possible=[k for k in ('serve','receive','fh','bh','feet','table','spirit') if s['g_roll'][k]<0]
            if possible:
                k=min(possible,key=lambda k:s['g_roll'][k]);delta=min(4,-s['g_roll'][k]);s['g_roll'][k]+=delta
                fix={'G':k,'delta':delta}
        # Read/execute is next-game only, not cumulative across a match
        weak=max(('fh','bh','table'),key=lambda k:(127-(oc['G9'][k]+opp['g_roll'][k]))+.05*rng.random())
        s['scouted_weakness']=weak if ok['weak'] else None
        s['execute_weakness']=ok['execute'] and ok['weak']
        s['read_bonus']=4*sum((ok['weak'],ok['execute']))
        psych=mental_check(rng)
        s['mental']=psych['type'];s['stable_bonus']=psych['stable_delta'];s['clutch_bonus']=psych['clutch_extra_delta']
        v={'player':card.get('player_id',str(idx)),'after_game':game_idx,'rolls':rolls,'thresholds':{'self':t_self,'weak':t_weak,'execute':t_exec},
          'successes':ok,'psychology':psych,'weakness':s['scouted_weakness'],'target_usable':s['execute_weakness'],
          'form_repair':fix,'read_delta':s['read_bonus']}
        s['game_check_history'].append(v);checks.append(v)
    return checks

def get_target(card,st,opp,rng,current,action):
    # A targeted weakness only changes probabilities, does not magically force arrival.
    if st['execute_weakness'] and st['scouted_weakness'] and rng.random()<.35+.003*(gg(card,st,'read')-120):
        aim=st['scouted_weakness'];
        if aim=='table':aim='middle'
        st['tactics']['target_known_weakness']+=1
    else:
        if action in ('chop','push','block','lob'):
            weights=[.36,.34,.30]
        elif current.get('target')=='fh':weights=[.30,.44,.26]
        else:weights=[.34,.32,.34]
        aim=rng.choices(['fh','bh','middle'],weights)[0]
    # tactical targeting accuracy depends on technical placement & read
    wing='bh' if action in ('bh_attack','bh_counter','block','chop') else 'fh'
    placement=card['children'][wing]['placement']
    accuracy=clamp(.70+.0035*(placement-115)+.0018*(gg(card,st,'read')-120),.48,.93)
    landed=aim if rng.random()<accuracy else rng.choice(['fh','bh','middle'])
    return aim,landed

def reach(card,st,ball,rng,step):
    pace=ball['pace'];q=ball['quality']
    p=st['p_eff'];feet=gg(card,st,'feet')
    loc=ball['landed'];distance=0 if loc=='middle' else 1
    if loc!='middle' and st.get('previous_location') and loc!=st['previous_location']:distance+=.5
    # Read has minor timing contribution, but NOT a direct shot-power bonus.
    skill=.50*feet+.19*p['speed']+.15*p['agility']+.10*p['flexibility']+.06*gg(card,st,'read')
    # A specialist chopper adopts a deeper, prepared defending position vs topspin.
    if card.get('style')=='modern_chopper' and ball['spin']=='top':skill+=5.8
    demand=121+.29*(q-120)+.22*(pace-120)+7*distance+min(8,step*.26)+st['match_stamina']*.16
    score=skill-demand+rng.gauss(0,11)
    if score<-21:position='miss'
    elif score<-10:position='bad'
    elif score<2:position='limited'
    else:position='good'
    st['previous_location']=loc
    st['observations']['reach_'+position]+=1
    return position,round(score,2)

def choose_action(card,st,ball,pos,rng):
    style=card.get('style','attacker')
    wing='fh' if ball['landed']=='fh' else 'bh' if ball['landed']=='bh' else ('fh' if rng.random()<.5 else 'bh')
    spin=ball['spin']
    if pos=='bad':
        return rng.choice(['lob','block','push']) if style!='modern_chopper' else 'chop'
    if style=='modern_chopper':
        # Specialist choices depend on incoming pace/spin and ability to arrive.
        if spin=='top' and ball['pace']>=119 and rng.random()<(.76 if pos=='good' else .87):return 'chop'
        if spin=='back' and rng.random()<.65:return 'push'
        if rng.random()<(.20 if pos=='limited' else .34):return wing+'_counter'
        return 'chop'
    if pos=='limited':return rng.choices(['block','push','bh_counter' if wing=='bh' else 'fh_counter'],[.52,.18,.30])[0]
    if spin=='back':return rng.choices([wing+'_open','push','flip'],[.67,.25,.08])[0]
    if spin=='top':return rng.choices([wing+'_counter',wing+'_attack','block'],[.38,.43,.19])[0]
    return rng.choices([wing+'_attack','block','flip'],[.67,.19,.14])[0]

def shot_quality(card,st,ball,pos,action,rng,step,clutch=False):
    wing=('bh' if action.startswith('bh_') or action in ('block','chop') and ball['landed']=='bh' else 'fh')
    if action=='chop':
        # Chopper quality emphasizes defensive skills, rotation, variation and placement
        s=card['children'][wing]
        tech=.42*s['defense']+.27*s['spin']+.23*s['placement']+.08*s['continuity']
        spin='back';pace=113+(.24*(tech-120))
    elif action=='push':tech=.65*gg(card,st,'table')+.35*card['children']['table']['push'];spin='back';pace=100+.19*(tech-115)
    elif action=='block':tech=.56*card['children'][wing]['defense']+.44*gg(card,st,wing);spin='top';pace=105+.24*(tech-118)
    elif action=='lob':tech=.68*gg(card,st,'spirit')+.32*gg(card,st,'feet');spin='top';pace=90+.08*(tech-120)
    elif action=='flip':tech=.55*gg(card,st,'table')+.45*gg(card,st,wing);spin='top';pace=121+.30*(tech-120)
    else:
        sub=card['children'][wing]
        if 'open' in action:tech=.45*sub['spin']+.35*gg(card,st,wing)+.20*sub['placement'];spin='top'
        elif 'counter' in action:tech=.35*sub['continuity']+.48*gg(card,st,wing)+.17*sub['power'];spin='top'
        else:tech=.52*gg(card,st,wing)+.29*sub['power']+.19*sub['continuity'];spin='top'
        pace=131+.39*(tech-125)+.13*(st['p_eff']['burst']-120) # body P only affects pace, not again tech
    # 'quality' physically limited by arrival, incoming spin, fatigue, short/long characteristics.
    arrival={'good':0,'limited':-13,'bad':-25}.get(pos,-40)
    spin_conflict=(clamp(6-.065*(gg(card,st,'receive')-120),2.5,8) if ball['spin']=='back' and spin=='top' and action!='flip' else 0)
    quality=clamp(tech+arrival-spin_conflict +rng.gauss(0,7),60,168)
    if action=='chop':quality+=clamp((ball['pace']-120)*.06,-2,3)
    if clutch:quality+=clamp(st['clutch_bonus']*.12,-1,1)
    return round(quality,2),round(pace,2),spin

def point(cards,state,rng,server,score,keep_shots=False):
    # Score in current game before the point, use 10+ as 'clutch'.
    clutch=max(score)>=10 or (min(score)>=8 and abs(score[0]-score[1])<=1)
    scard=cards[server];serv=state[server];recv=1-server
    serve=gg(scard,serv,'serve');serve_spin=rng.choice(['side','back','top'])
    srvq=clamp(117+.39*(serve-120)+rng.gauss(0,9),87,161)
    served=rng.choice(['fh','bh','middle']);ball={'spin':serve_spin,'pace':105+.30*(serve-120),'quality':srvq,'landed':served,'target':served,'pressure':.20}
    shots=[]
    if keep_shots:shots.append({'player':server,'action':'serve','quality':round(srvq,1),'landed':served,'spin':serve_spin,'reach':'service','return_state':'serve'})
    n=recv
    for step in range(1,51):
        c=cards[n];st=state[n];op=state[1-n]
        pos,reach_score=reach(c,st,ball,rng,step)
        if pos=='miss':
            if keep_shots:shots.append({'player':n,'action':'unreached','reach':pos,'return_state':'direct_point_lost','input_target':ball['landed'],'reach_score':reach_score})
            st['observations']['unreached']+=1
            return 1-n,len(shots) if keep_shots else step+1,shots,'unreached'
        action=choose_action(c,st,ball,pos,rng)
        quality,pace,spin=shot_quality(c,st,ball,pos,effective_action,rng,step,clutch)
        if step==2:
            quality+=clamp((c['children']['serve']['third_link']-120)*.13,-3,4)
        stable=gg(c,st,'stable')+(st['clutch_bonus'] if clutch else 0)
        # Fault risk: arrival is dominant; chop is better at surviving fast topspin but may give weak balls.
        base={'good':.062,'limited':.148,'bad':.31}[pos]
        if action in ('fh_attack','bh_attack','fh_counter','bh_counter','fh_open','bh_open'):
            base+=.024
            if action.endswith('open') and ball['spin']=='back':base+=.015
        if action=='chop':base-=.023 if ball['spin']=='top' else .005
        if action=='lob':base-=.016
        # Incoming chop spin makes attacking it difficult, while chops are less direct winners.
        if ball['spin']=='back' and action not in ('chop','push'):
            base+=clamp((ball.get('backspin_strength',130)-124)*.0015,0,.050)*clamp(1-.006*(gg(c,st,'receive')-118),.65,1.17)
        base+=clamp((ball['quality']-137)*.0018,-.017,.07)
        base-=clamp((stable-122)*.0008,-.020,.031)
        base+=clamp((120-quality)*.0007,-.02,.03)
        base+=max(0,step-9)*.0014
        base=clamp(base,.022,.47)
        bad=rng.random()<base
        if bad:
            if keep_shots:shots.append({'player':n,'action':action,'reach':pos,'out_quality':quality,'input_target':ball['landed'], 'return_state':'direct_point_lost','fault_prob':round(base,4)})
            st['observations']['errors']+=1
            return 1-n,len(shots) if keep_shots else step+1,shots,'error'
        # Strong / neutral / high outcomes reflect quality, body and action.
        if action=='lob' or pos=='bad':stateout='high_ball'
        elif quality>=142 and action not in ('chop','push','lob'):stateout='strong_return'
        elif quality<114 and action not in ('chop','push'):stateout='high_ball'
        else:stateout='neutral_return'
        aim,landed=get_target(c,st,op,rng,ball,action)
        if keep_shots:shots.append({'player':n,'action':action,'reach':pos,'out_quality':quality,'pace':pace,'spin':spin,'target':aim,'landed':landed,'return_state':stateout,'fault_prob':round(base,4)})
        st['observations'][action]+=1;st['observations'][stateout]+=1
        # Shot creates physical opponent demands. Chop backspin is spin forcing, not direct pace forcing.
        q_for_next=quality+ (8 if stateout=='strong_return' else 0) + (5 if ball['return_state']=='high_ball' else 0) if 'return_state' in ball else quality+(8 if stateout=='strong_return' else 0)
        ball={'spin':spin,'pace':pace,'quality':q_for_next,'landed':landed,'target':aim,
              'return_state':stateout,'backspin_strength':(quality if action=='chop' else 128),
              'pressure':clamp((q_for_next-120)/65,0,1)}
        if action!='chop' and stateout=='strong_return' and rng.random()<clamp(.038+.0014*(quality-130),.015,.098):
            # Rare outright shot winners not solely from receiver failure.
            return n,len(shots) if keep_shots else step+1,shots,'winner'
        n=1-n
    return rng.choice([0,1]),len(shots) if keep_shots else 51,shots,'rally_limit'

def serve_side(point_idx,game_idx):
    # Official pattern: switch service every 2 points before 10-all, 1 thereafter.
    if point_idx>=20:return (game_idx+point_idx-20)%2
    return (game_idx+(point_idx//2))%2

def play_match(cards,seed,*,keep_points=False,fatigue=(25,25),max_games=7):
    assert len(cards)==2 and max_games==7
    rng=rng_of('SPIN-ERA-1.1-T','MATCH',seed)
    state=[warmup(cards[i],rng,fatigue[i]) for i in (0,1)]
    won=[0,0];games=[];checks=[];total_strokes=0;point_count=0;reaches=Counter();outcomes=Counter();action_counts=Counter();rallies=[]
    for gi in range(7):
        scores=[0,0];pl=[]
        while (max(scores)<11 or abs(scores[0]-scores[1])<2):
            server=serve_side(sum(scores),gi)
            winner,strokes,shots,reason=point(cards,state,rng,server,scores,keep_shots=keep_points)
            scores[winner]+=1;point_count+=1;total_strokes+=strokes;rallies.append(strokes);outcomes[reason]+=1
            if keep_points:
                pl.append({'score_before':[scores[0]-int(winner==0),scores[1]-int(winner==1)],'server':server,'winner':winner,'strokes':strokes,'reason':reason,'shots':shots})
            # observation aggregates, no duplicate counting of conditional states
            for s in shots:
                if s.get('reach') in ('good','limited','bad','miss'):reaches[s['reach']]+=1
                if s.get('return_state') in ('strong_return','neutral_return','high_ball'):outcomes[s['return_state']]+=1
                if 'action' in s:action_counts[s['action']]+=1
            if point_count>1500:raise RuntimeError('excessively long match')
        k=0 if scores[0]>scores[1] else 1;won[k]+=1
        g={'score':scores,'winner':k,'points_count':sum(scores)}
        if keep_points:g['points']=pl
        games.append(g)
        for st in state:st['match_stamina']+=sum(scores)/max(35.,st['p_eff']['stamina'])*2.0
        if won[k]==4:break
        checks.extend(between_games(cards,state,rng,gi+1))
    return {'seed':seed,'winner':0 if won[0]==4 else 1,'games_won':won,'games':games,'points':point_count,'total_strokes':total_strokes,
       'mean_strokes':round(total_strokes/point_count,3),'rallies':rallies,'reaches':dict(reaches),'outcomes':dict(outcomes),
       'actions':dict(action_counts),'between_game_checks':checks,'match_form':[{k:v for k,v in st.items() if k in ('form_initial','p_roll','mental','game_check_history')} for st in state],
       'status':'SIMULATED_NONHISTORICAL_V11_TEST'}

# V1.1.2 EXPERIMENTAL: live serve-receive-third-ball state and repeated counter-counters.
# The base game_v11.py above is retained for bisect/review; definitions below supersede it.
V112_TAG='spin_era_v112_prototype_prethree_counter'
_older_warmup=warmup
_older_between_games=between_games
_older_choose=choose_action
_older_reach=reach
_older_quality=shot_quality

SERVE_ZONES=('fh_short','bh_short','middle_short','fh_long','bh_long','middle_long')
SPINS=('back','dead','top','side_back','side_top')
SERVE_STYLES=('pendulum','reverse_pendulum','backhand','tomahawk')
POLICIES=('third_ball_fh','receive_initiative','bh_squeeze','wide_angles','change_spin','defensive_pivot')

def warmup(card,rng,fatigue=25):
    s=_older_warmup(card,rng,fatigue)
    if card.get('style')=='modern_chopper':initial='defensive_pivot'
    elif card['G9']['serve']>=card['G9']['receive']+5:initial='third_ball_fh'
    elif card['G9']['bh']>card['G9']['fh']+5:initial='bh_squeeze'
    else:initial='receive_initiative'
    s.update({'policy':initial,'policy_stage':0,'policy_events':[],'points_seen':0,
        'serve_forms':Counter(),'serve_ends':Counter(),'return_forms':Counter(),'counter_attempts':0,
        'last_serve':None,'serve_response_knowledge':Counter()})
    return s

def serve_policy(card,s,rng):
    # Bayesian-like fixed partial preferences; not an actual physical trajectory model.
    policy=s['policy']
    if policy=='third_ball_fh':weights=[.29,.35,.14,.06,.11,.05]
    elif policy=='bh_squeeze':weights=[.20,.42,.16,.06,.11,.05]
    elif policy=='change_spin':weights=[.24,.27,.25,.06,.12,.06]
    else:weights=[.25,.32,.20,.065,.105,.06]
    zone=rng.choices(SERVE_ZONES,weights)[0]
    spin_weights=[.28,.12,.09,.35,.16] if policy in ('third_ball_fh','change_spin') else [.26,.15,.13,.29,.17]
    variation=card['children']['serve']['variation']
    side_weight=clamp(.95+.007*(variation-120),.7,1.3)
    spin_weights=[w*side_weight if name.startswith('side_') else w for w,name in zip(spin_weights,SPINS)]
    spin=rng.choices(SPINS,spin_weights)[0]
    styler=rng.choices(SERVE_STYLES,[.46,.29,.17,.08])[0]
    if rng.random()<.07 and s['policy_stage']>0:styler='reverse_pendulum'
    return zone,spin,styler

def third_ball_tendency(st,action,target):
    # Target is an opponent-side landing lane; no guaranteed physical spin return.
    if st['policy']=='third_ball_fh' and action in ('fh_open','fh_attack','fh_counter'):return .10
    if st['policy']=='bh_squeeze' and target=='bh':return .07
    return 0

def response_target(srv,receiver,receiver_state,server_state,rng,action):
    # Conditional *receiver's* response lane, not deterministic spin physics.
    weights={'fh':.33,'bh':.36,'middle':.31}
    if srv['style']=='reverse_pendulum' and srv['spin'] in ('side_back','side_top'):
        # Opponent returns to server BH more often when spin direction is not fully controlled;
        # depends on receiver spin-reading/control, handedness and selected reception.
        spin_read=gg(receiver,receiver_state,'receive')
        extra=clamp(.19-.0025*(spin_read-115),.04,.24)
        if action in ('flip','bh_open','fh_open'):extra*=.45
        if receiver.get('hand')=='left':extra*=.75
        weights['bh']+=extra;weights['fh']-=extra*.60;weights['middle']-=extra*.40
    if receiver_state['policy']=='receive_initiative':weights['middle']+=.06;weights['bh']-=.03;weights['fh']-=.03
    if receiver_state['execute_weakness'] and receiver_state['scouted_weakness']:
        lane=receiver_state['scouted_weakness'] if receiver_state['scouted_weakness']!='table' else 'middle'
        weights[lane]+=0.18
    lanes=list(weights)
    vals=[max(.03,weights[k]) for k in lanes]
    aim=rng.choices(lanes,weights=vals)[0]
    p=clamp(.61+.003*(gg(receiver,receiver_state,'receive')-110),.45,.92)
    return aim, aim if rng.random()<p else rng.choice(lanes)

def receive_action(c,st,srv,pos,rng):
    if pos=='bad':return rng.choice(['push','block'])
    long=srv['length']=='long'
    sp=srv['spin']
    rec=gg(c,st,'receive')
    if long:
        if sp in ('back','side_back'):
            return rng.choices(['bh_open','fh_open','push'],[.46,.36,.18])[0]
        return rng.choices(['bh_attack','fh_attack','block'],[.46,.38,.16])[0]
    if st['policy']=='receive_initiative' or rec>=128:
        return rng.choices(['flip','push_short','bh_open'],[.49,.39,.12])[0]
    if sp in ('back','side_back'):return rng.choices(['push_short','push_long','flip','bh_open'],[.46,.23,.24,.07])[0]
    return rng.choices(['flip','push_short','push_long','block'],[.39,.28,.17,.16])[0]

def reach(card,st,ball,rng,step):
    pos,score=_older_reach(card,st,ball,rng,step)
    # Short pushes force forward interception, often followed by recovery costs.
    if ball.get('length')=='short' and step<=2:
        score+=clamp((gg(card,st,'table')-110)*.13,-3,4)
        if score<-21:pos='miss'
        elif score<-10:pos='bad'
        elif score<2:pos='limited'
        else:pos='good'
    return pos,score

def choose_action(card,st,ball,pos,rng):
    if ball.get('origin')=='service' and ball.get('third_phase')=='receive':return receive_action(card,st,ball,pos,rng)
    a=_older_choose(card,st,ball,pos,rng)
    if st['policy']=='defensive_pivot' and card.get('style')=='modern_chopper' and pos in ('good','limited'):
        if rng.random()<.15:a='chop'
    elif st['policy']=='bh_squeeze' and ball['landed']=='bh' and pos=='good' and ball['spin']!='back':
        if rng.random()<.22:a='bh_counter'
    elif st['policy']=='third_ball_fh' and ball.get('origin')=='service_return' and pos=='good':
        if ball['spin']=='back':a='fh_open' if rng.random()<.72 else a
        elif rng.random()<.52:a='fh_attack'
    return a

def attempt_in_game_adaptation(cards,state,rng,score,game_idx=0):
    if sum(score)<6 or sum(score)%6!=0:return
    for i in (0,1):
        st=state[i];opp=state[1-i];card=cards[i]
        if st['policy_stage']>=3:continue
        stage_now=st['policy_stage']
        minimum_gap=(0,12,18)[stage_now]
        if st['points_seen']-st.get('last_counter_seen',-999)<minimum_gap:continue
        read=gg(card,st,'read')
        # Detect repeated opponent tactic and choose counter, possibly re-counter later.
        roll=rng.randint(1,100)
        threshold=clamp(25+.41*(read-110)+.09*(st['points_seen']-6),15,67)
        threshold*= (0.9,0.48,0.25)[stage_now]
        if roll>threshold:continue
        st['last_counter_seen']=st['points_seen']
        old=st['policy'];enemy=opp['policy']
        counters={'third_ball_fh':'receive_initiative','receive_initiative':'bh_squeeze',
         'bh_squeeze':'wide_angles','wide_angles':'change_spin','change_spin':'third_ball_fh',
         'defensive_pivot':'change_spin'}
        st['policy']=counters.get(enemy,'change_spin')
        if st['policy']==old:st['policy']='wide_angles' if old!='wide_angles' else 'change_spin'
        st['policy_stage']+=1;st['counter_attempts']+=1
        st['policy_events'].append({'game':game_idx+1,'point_at':sum(score),'stage':st['policy_stage'],
             'read_D100':roll,'threshold':round(threshold,1),'opponent_policy':enemy,
             'from':old,'to':st['policy'],'type':['counter','counter_counter','counter_counter_counter'][min(2,st['policy_stage']-1)]})

def point(cards,state,rng,server,score,keep_shots=False):
    scard=cards[server];serv=state[server];recv=1-server;rcard=cards[recv];rst=state[recv]
    clutch=max(score)>=10 or (min(score)>=8 and abs(score[0]-score[1])<=1)
    zone,spin,serve_style=serve_policy(scard,serv,rng)
    aim=zone.rsplit('_',1)[0];length=zone.rsplit('_',1)[1]
    servq=clamp(118+.30*(gg(scard,serv,'serve')-120)
       +.08*(scard['children']['serve']['spin']-120)+.09*(scard['children']['serve']['placement']-120)+rng.gauss(0,8),82,164)
    srv={'origin':'service','third_phase':'receive','spin':spin,'pace':105+(7 if length=='long' else 0),
         'quality':servq,'landed':aim,'target':aim,'length':length,'style':serve_style,
         'backspin_strength':125 if spin in ('back','side_back') else 0}
    serv['serve_forms'][zone+'|'+spin+'|'+serve_style]+=1
    serv['last_serve']={'zone':zone,'spin':spin,'style':serve_style}
    shots=[{'player':server,'action':'serve','zone':zone,'style':serve_style,'spin':spin,
            'length':length,'landed':aim,'quality':round(servq,2),'return_state':'serve'}] if keep_shots else []
    n=recv;ball=srv
    for step in range(1,42):
        c=cards[n];st=state[n];op=state[1-n]
        pos,reach_score=reach(c,st,ball,rng,step)
        if pos=='miss':
            if keep_shots:shots.append({'player':n,'action':'unreached','reach':'miss','input_target':ball['landed'],'return_state':'direct_point_lost'})
            st['observations']['unreached']+=1
            return 1-n,(len(shots)-1 if keep_shots else step),shots,'unreached'
        action=choose_action(c,st,ball,pos,rng)
        effective_action='push' if action.startswith('push_') else action
        # For short service, an attempted offensive opener must pay a placement cost.
        quality,pace,outspin=_older_quality(c,st,{'spin':'back' if ball['spin']=='side_back' else 'top' if ball['spin']=='side_top' else ball['spin'],**{k:v for k,v in ball.items() if k!='spin'}},pos,effective_action,rng,step,clutch)
        if ball.get('origin')=='service' and ball['length']=='short' and action in ('fh_open','bh_open','fh_attack','bh_attack','bh_open_twist'):
            quality-=5
        if step==2:
            quality+=clamp((c['children']['serve']['third_link']-120)*.13,-3,4)
        stable=gg(c,st,'stable')+(st['clutch_bonus'] if clutch else 0)
        base={'good':.073,'limited':.176,'bad':.35}[pos]
        offensive=any(a in action for a in ('attack','counter','open','flip'))
        if offensive:base+=.035
        if action=='chop':base-=.03 if ball['spin'] in ('top','side_top') else .004
        if ball.get('origin')=='service':
            misread=clamp(.075+.003*(servq-120)-.0015*(gg(c,st,'receive')-115)
             +.0013*(cards[1-n]['children']['serve']['disguise']-120)
             -.0012*(c['children']['receive']['spin_read']-120),.018,.21)
            if ball['spin'] in ('side_back','side_top'):misread+=.03
            if effective_action=='push' and ball['spin'] in ('top','side_top'):misread+=.05
            base+=misread
        if ball['spin'] in ('back','side_back') and offensive:
            base+=.027+clamp((ball.get('backspin_strength',127)-125)*.002,0,.045)
        if ball['return_state']=='high_ball' if 'return_state' in ball else False:
            if offensive:base-=.023
        base+=clamp((ball['quality']-130)*.0016,-.022,.071)
        base-=clamp((stable-120)*.0010,-.018,.040)
        base+=max(0,step-8)*.002
        base=clamp(base,.026,.58)
        if rng.random()<base:
            if keep_shots:shots.append({'player':n,'action':action,'reach':pos,'input_target':ball['landed'],
               'quality':round(quality,2),'return_state':'direct_point_lost','error_prob':round(base,4)})
            st['observations']['errors']+=1
            return 1-n,(len(shots) if keep_shots else step+1),shots,'error'
        if action=='lob' or pos=='bad':stateout='high_ball'
        elif quality>=140 and effective_action not in ('chop','push','lob'):stateout='strong_return'
        elif quality<109 and effective_action not in ('chop','push'):stateout='high_ball'
        else:stateout='neutral_return'
        if ball.get('origin')=='service':
            outaim,landed=response_target(serv['last_serve'],c,st,serv,rng,action)
            st['return_forms'][action+'|'+outaim]+=1
        else:
            outaim,landed=get_target(c,st,op,rng,ball,action)
        if keep_shots:shots.append({'player':n,'action':action,'reach':pos,'input_target':ball['landed'],
          'out_quality':round(quality,2),'pace':round(pace,2),'spin':outspin,'target':outaim,
          'landed':landed,'return_state':stateout,'fault_prob':round(base,4), 'phase':'return' if step==1 else 'third_ball' if step==2 else 'rally'})
        st['observations'][action]+=1;st['observations'][stateout]+=1
        if action=='chop':st['observations']['chop_effective']+=1
        if step==1:origin='service_return'
        elif step==2:origin='third_ball'
        else:origin='rally'
        ball={'origin':origin,'spin':outspin,'pace':pace,'quality':quality+(8 if stateout=='strong_return' else 0),
          'landed':landed,'target':outaim,'length':'short' if action in ('push_short','flip','push','push_side','push_middle','fh_flip_short','bh_flip_short') else 'long',
          'return_state':stateout,'backspin_strength':quality if action=='chop' else 126}
        # Live counter style across longer rallies, not scripted winner selection.
        st['points_seen']+=0 if step>1 else 1
        p_win=clamp(.065+.0023*(quality-132),.016,.18) if offensive and stateout=='strong_return' else 0
        if ball.get('origin')=='third_ball' and serv['policy']=='third_ball_fh':p_win+=.025
        if rng.random()<p_win:
            st['observations']['winners']+=1
            return n,(len(shots) if keep_shots else step+1),shots,'winner'
        n=1-n
    return rng.choice([0,1]),(len(shots) if keep_shots else 42),shots,'rally_limit'

_old_play_match=play_match

def play_match(cards,seed,*,keep_points=False,fatigue=(25,25),max_games=7):
    # Exact base BO7 scoring; patch the imported definitions via globals.
    r=_old_play_match(cards,seed,keep_points=keep_points,fatigue=fatigue,max_games=max_games)
    # The base runner resolves overridden point/warmup/choice functions at runtime.
    r['engine']=V112_TAG
    r['serve_distribution']=dict(Counter(s['zone'] for g in r['games'] for p in g.get('points',[]) for s in p['shots'] if s.get('action')=='serve')) if keep_points else {}
    r['spin_distribution']=dict(Counter(s['spin'] for g in r['games'] for p in g.get('points',[]) for s in p['shots'] if s.get('action')=='serve')) if keep_points else {}
    return r

def play_match(cards,seed,*,keep_points=False,fatigue=(25,25),max_games=7):
    if max_games!=7 or len(cards)!=2:raise ValueError('BO7 two players only')
    rng=rng_of('SPIN-ERA-1.1.2','MATCH',seed)
    states=[warmup(cards[i],rng,fatigue[i]) for i in (0,1)]
    won=[0,0];games=[];checks=[];total_strokes=0;points=0;reaches=Counter();outcomes=Counter();actions=Counter();rallies=[]
    for gi in range(7):
        score=[0,0];pl=[]
        while max(score)<11 or abs(score[0]-score[1])<2:
            srv=serve_side(sum(score),gi)
            before=score.copy()
            winner,n,shots,reason=point(cards,states,rng,srv,score,keep_shots=keep_points)
            score[winner]+=1;points+=1;total_strokes+=n;rallies.append(n);outcomes[reason]+=1
            if keep_points:pl.append({'score_before':before,'server':srv,'winner':winner,'strokes':n,'reason':reason,'shots':shots})
            for s in shots:
                if s.get('reach') in ('good','limited','bad','miss'):reaches[s['reach']]+=1
                if s.get('return_state') in ('strong_return','neutral_return','high_ball'):outcomes[s['return_state']]+=1
                if s.get('action'):actions[s['action']]+=1
            attempt_in_game_adaptation(cards,states,rng,score,gi)
            if points>1500:raise RuntimeError('implausible length')
        w=0 if score[0]>score[1] else 1;won[w]+=1
        g={'score':score,'winner':w,'points_count':sum(score)}
        if keep_points:g['points']=pl
        games.append(g)
        for s in states:s['match_stamina']+=sum(score)/max(35.,s['p_eff']['stamina'])*2
        if won[w]==4:break
        checks.extend(between_games(cards,states,rng,gi+1))
    counts=Counter()
    spins=Counter()
    ret=Counter()
    tactics=[]
    for i,s in enumerate(states):
        counts.update(s['serve_forms']);ret.update(s['return_forms']);
        tactics.extend([dict(x,player=cards[i].get('player_id',str(i))) for x in s['policy_events']])
    return {'seed':seed,'engine':V112_TAG,'winner':0 if won[0]==4 else 1,'games_won':won,'games':games,'points':points,
      'total_strokes':total_strokes,'mean_strokes':round(total_strokes/points,3),'rallies':rallies,
      'reaches':dict(reaches),'outcomes':dict(outcomes),'actions':dict(actions),
      'serve_distribution':dict(counts),'return_distribution':dict(ret),
      'tactical_events':tactics,'between_game_checks':checks,
      'match_form':[{'form_initial':s['form_initial'],'p_roll':s['p_roll'],'psychological_state':s['mental'],
       'initial_final_tactics':s['policy'],'counter_level':s['policy_stage']} for s in states],
      'status':'SIMULATED_NONHISTORICAL_V112_TEST'}
