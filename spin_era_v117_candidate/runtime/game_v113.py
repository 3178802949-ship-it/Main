"""V1.1.3 causal tactical front-end on V1.1.2 symmetric shot engine.
NOT a physical spin model. Pre-point plans influence choices, opponent may counter.
Output derived from rolls, never write outcomes as narration prerequisites.
"""
from __future__ import annotations
import game_v112 as base
from collections import Counter

SERVE_PLANS={
 'short_back_then_open':dict(zone='bh_short',spin='back',style='pendulum',mechanism='short underspin limits immediate full swing; tempt a long push then open against backspin',third='open_if_long_push'),
 'short_middle_double_bounce':dict(zone='middle_short',spin='back',style='backhand',mechanism='short middle with strong underside, require careful short touch, then fifth-ball initiative',third='short_exchange_or_open'),
 'side_under_to_fh_triangle':dict(zone='fh_short',spin='side_back',style='reverse_pendulum',mechanism='reverse side-underspin to small forehand triangle tests forward movement, touch angle, and spin read',third='punish_high_or_long'),
 'pendulum_bh_small_triangle':dict(zone='bh_short',spin='side_back',style='pendulum',mechanism='pendulum sidespin to BH small triangle forces nuanced BH short control and creates FH/BH redirect risk',third='preposition_for_next'),
 'pendulum_to_fh_open':dict(zone='fh_short',spin='side_top',style='pendulum',mechanism='sidespin/topspin encourages offensive receive or overrun short touch, preparing FH third attack',third='counter_receive'),
 'reverse_to_fh_short':dict(zone='fh_short',spin='side_top',style='reverse_pendulum',mechanism='reverse sidespin attacks FH short angle, anticipating directed return into server BH',third='bh_open_or_counter'),
 'no_spin_disguise':dict(zone='middle_short',spin='dead',style='pendulum',mechanism='no-spin disguised as underside risks high touch or flick, yielding third-ball opportunity',third='punish_high_ball'),
 'fast_long_bh':dict(zone='bh_long',spin='top',style='backhand',mechanism='surprise fast long BH invites direct receive attack but pressures timing and ready stance',third='block_counter'),
 'long_under_middle':dict(zone='middle_long',spin='back',style='tomahawk',mechanism='deep middle backspin challenges footwork commitment and initial loop against backspin',third='counter_open'),
 'fast_long_fh':dict(zone='fh_long',spin='side_top',style='pendulum',mechanism='wide long fast spin pressures FH preparation and may expose next-angle transition',third='wide_angle_counter')
}

def _weighted_plan(card,st,rng):
    # Policies, stroke aptitude and in-game counters jointly shape serve intentions.
    p=st.get('policy','third_ball_fh'); serve=base.gg(card,st,'serve'); table=base.gg(card,st,'table')
    weights={'short_back_then_open':2.0,'short_middle_double_bounce':1.0,'side_under_to_fh_triangle':1.0,
             'pendulum_bh_small_triangle':1.2,'pendulum_to_fh_open':1.0,'reverse_to_fh_short':1.0,
             'no_spin_disguise':1.0,'fast_long_bh':.65,'long_under_middle':.45,'fast_long_fh':.45}
    if p=='third_ball_fh':
        weights['short_back_then_open']*=1.65;weights['pendulum_to_fh_open']*=1.5
    elif p=='bh_squeeze':
        weights['reverse_to_fh_short']*=1.65;weights['pendulum_bh_small_triangle']*=1.35
    elif p=='receive_initiative': weights['short_middle_double_bounce']*=1.3
    elif p=='change_spin':weights['no_spin_disguise']*=1.7;weights['fast_long_bh']*=1.4
    elif p=='wide_angles':weights['side_under_to_fh_triangle']*=1.5;weights['fast_long_fh']*=1.5
    # Smart opponent or weak server suppresses overuse of risky long serves.
    if serve<110:
        weights['fast_long_fh']*=.78;weights['fast_long_bh']*=.78
    if table>125:weights['short_middle_double_bounce']*=1.25
    names=list(weights)
    return rng.choices(names,weights=list(weights.values()))[0]

def serve_policy(card,st,rng):
    name=_weighted_plan(card,st,rng)
    plan=SERVE_PLANS[name]
    st['serve_intent_name']=name
    st['serve_intents'][name]+=1
    return plan['zone'],plan['spin'],plan['style']

_old_warm=base.warmup
def warmup(card,rng,fatigue=25):
    s=_old_warm(card,rng,fatigue)
    s['serve_intents']=Counter();s['serve_intent_name']=None
    return s

def receive_action(card,st,srv,pos,rng):
    sp=srv['spin'];length=srv.get('length')
    # Draw an approximate read state. Strong receive G + spin-read subskill makes
    # a safe aggressive alternative likelier; counter-adaptation can adapt choices.
    read=.57*base.gg(card,st,'receive')+.43*card['children']['receive']['spin_read']
    table=base.gg(card,st,'table');short=(length=='short')
    reverse=srv['style']=='reverse_pendulum'
    if pos=='bad':return rng.choices(['push_long','block','flip'],[.67,.24,.09])[0]
    if not short:
        if sp in ('back','side_back'):
            ws=[.34,.30,.36] if read<116 else [.42,.37,.21]
            return rng.choices(['bh_open','fh_open','push_long'],ws)[0]
        return rng.choices(['bh_attack','fh_attack','block'],[.41,.40,.19])[0]
    if sp in ('back','side_back'):
        # Short underpin tends to constrain a full-length offensive loop.
        t=base.clamp((table-112)*.004,-.07,.10)
        options=['push_short','push_long','flip','bh_open']
        weights=[.43+t,.28-t*.5,.23-t*.3,.06-t*.2]
        if st['policy']=='receive_initiative':weights=[.35,.17,.39,.09]
        if reverse: weights[2]+=.05;weights[0]-=.05 # small triangle recovery challenge
        return rng.choices(options,weights)[0]
    if sp=='dead':
        return rng.choices(['push_short','flip','push_long','block'],[.33,.42,.17,.08])[0]
    return rng.choices(['flip','push_short','push_long','block'],[.43,.26,.16,.15])[0]

_old_target=base.response_target
def response_target(srv,receiver,receiver_state,server_state,rng,action):
    # Keep same causal mapping as preceding engine, but adjust for specific return
    # action. This is a conditional decision bias, NOT deterministic physical flight.
    aim,landed=_old_target(srv,receiver,receiver_state,server_state,rng,action)
    if action=='push_long' and rng.random()<.11:landed='bh'
    elif action=='push_short' and rng.random()<.09:landed='middle'
    elif action=='flip' and receiver_state.get('policy')=='receive_initiative' and rng.random()<.12:landed='middle'
    return aim,landed

_old_choose=base.choose_action
def choose_action(card,st,ball,pos,rng):
    if ball.get('origin')=='service' and ball.get('third_phase')=='receive':
        return receive_action(card,st,ball,pos,rng)
    if ball.get('origin')=='service_return' and pos=='good':
        # An incoming long push with backspin invites initial spin attack.
        if ball['spin']=='back' and ball.get('length')=='long':
            if st.get('policy')=='third_ball_fh' and card['G9']['fh']>=card['G9']['bh']-3:
                return rng.choices(['fh_open','bh_open','push'],[.69,.18,.13])[0]
            return rng.choices(['fh_open','bh_open','push'],[.37,.45,.18])[0]
        if ball.get('length')=='short':
            return rng.choices(['flip','push_short','push_long'],[.32,.48,.20])[0]
    return _old_choose(card,st,ball,pos,rng)

def explain_point(point):
    shots=point.get('shots',[])
    if not shots:return {'note':'point without shot log'}
    serve=shots[0];recv=shots[1] if len(shots)>1 else None;third=shots[2] if len(shots)>2 else None
    plan=next((name for name,v in SERVE_PLANS.items() if v['zone']==serve['zone'] and v['spin']==serve['spin'] and v['style']==serve['style']),None)
    return {'plan':plan or 'mixed_serve','intended_mechanism':SERVE_PLANS[plan]['mechanism'] if plan else 'varied serve',
            'serve_zone':serve.get('zone'),'serve_spin':serve.get('spin'),
            'received_action':recv.get('action') if recv else None,
            'receive_position':recv.get('reach') if recv else None,
            'receive_land':recv.get('landed') if recv else None,
            'third_ball_action':third.get('action') if third else None,
            'third_ball_position':third.get('reach') if third else None,
            'third_ball_return_state':third.get('return_state') if third else None,
            'end_reason':point['reason'],'winner':point['winner'],
            'causal_note':'Observed actions and rolls only; intention is conditional, not guaranteed result.'}

def play_match(cards,seed,*,keep_points=False,fatigue=(25,25),max_games=7):
    # Target code reads overridable Python module globals; patch calls temporarily.
    functions={'warmup':warmup,'serve_policy':serve_policy,'receive_action':receive_action,
               'response_target':response_target,'choose_action':choose_action}
    saved={k:getattr(base,k) for k in functions}
    try:
        for k,v in functions.items():setattr(base,k,v)
        result=base.play_match(cards,seed,keep_points=keep_points,fatigue=fatigue,max_games=max_games)
    finally:
        for k,v in saved.items():setattr(base,k,v)
    result['engine']='Spin_Era_V1.1.3_CAUSAL_SERVE_TEST'
    if keep_points:
        plans=Counter()
        for game in result['games']:
            for p in game['points']:
                p['causal_trace']=explain_point(p);plans[p['causal_trace']['plan']]+=1
        result['serve_plan_distribution']=dict(plans)
    return result
