"""Spin Era 1.1.5 experimental causal scenario policy.
14 inbound situations, 9+ legal response edges each; live game_v112 shot quality,
serve -> recognition -> reach -> action -> ball state -> third ball -> rally.
All newly generated game records are NONHISTORICAL. Do not import by replacing
original old module files. No real spin physics claimed.
"""
from __future__ import annotations
import game_v114 as b
import game_v113 as b113
import game_v112 as core
from collections import Counter
import math,random

# Core technical actions have exact G43 linkage. Every listed technique is a
# decision policy, not an independent +G, and reuses the same physical strokes.
MORE={
 'fh_soft_flip':('table.flick','fh_attack','正手轻挑'),
 'bh_soft_flip':('table.flick','bh_attack','反手轻挑'),
 'fh_fast_flip':('fh.power','fh_attack','正手暴挑'),
 'bh_fast_flip':('bh.power','bh_attack','反手暴挑'),
 'bh_banana_twist':('receive.initiative','bh_open','反手拧拉侧旋'),
 'bh_reverse_twist':('spirit.improvisation','bh_open','反向拧拉'),
 'fh_inside_flick':('table.placement','fh_attack','正手小三角内挑'),
 'fh_outside_flick':('fh.placement','fh_attack','正手小三角外挑'),
 'bh_inside_flick':('bh.placement','bh_attack','反手小三角内挑'),
 'bh_outside_flick':('bh.placement','bh_attack','反手小三角外挑'),
 'fh_side_open':('fh.spin','fh_open','正手侧旋拉起'),
 'bh_side_open':('bh.spin','bh_open','反手侧旋拉起'),
 'fh_slow_loop':('fh.spin','fh_open','正手高吊弧圈'),
 'bh_slow_loop':('bh.spin','bh_open','反手高吊弧圈'),
 'fh_fast_loop':('fh.power','fh_attack','正手前冲'),
 'bh_fast_loop':('bh.power','bh_attack','反手前冲'),
 'fh_counter_loop':('fh.continuity','fh_counter','正手反拉'),
 'bh_counter_loop':('bh.continuity','bh_counter','反手反拉'),
 'bh_sideswipe':('table.placement','bh_attack','反手侧撇'),
 'fh_sideswipe':('table.placement','fh_attack','正手侧撇'),
 'short_stop_drop':('table.short','push_short','吸短'),
 'short_deep_fake':('serve.disguise','push_long','假摆短后劈长'),
 'fast_long_push':('table.push','push_long','加转劈长'),
 'heavy_under_push':('table.chop_control','push_long','重下旋搓长'),
 'bh_press_block':('bh.defense','block','反手压挡'),
 'fh_press_block':('fh.defense','block','正手压挡'),
 'chop_transition':('table.chop_control','chop','退台削接'),
 'fh_lob_rescue':('spirit.lob_arcs','lob','正手高球救险'),
 'bh_lob_rescue':('spirit.unorthodox_defense','lob','反手高球救险'),
 'middle_jam_counter':('read.choice','bh_counter','中路挤压反击'),
 'fh_half_fast':('fh.power','fh_attack','正手冲半出台'),
 'bh_half_fast':('bh.power','bh_attack','反手冲半出台')
}
# 14 contexts x 9+ options. All options have an actual G43 mapping and
# physically admissible output via fallback shot mechanisms.
SCENARIOS={
 'short_back_bh':['push_short','push_long','push_side','short_stop_drop','bh_soft_flip','bh_fast_flip','bh_banana_twist','bh_reverse_twist','fh_inside_flick','fast_long_push'],
 'short_back_fh':['push_short','push_long','push_side','short_stop_drop','fh_soft_flip','fh_fast_flip','fh_inside_flick','fh_outside_flick','bh_banana_twist','heavy_under_push'],
 'short_side_bh':['push_short','push_long','bh_soft_flip','bh_fast_flip','bh_banana_twist','bh_reverse_twist','bh_inside_flick','bh_outside_flick','bh_sideswipe','short_deep_fake'],
 'short_side_fh':['push_short','push_long','fh_soft_flip','fh_fast_flip','fh_inside_flick','fh_outside_flick','fh_sideswipe','bh_banana_twist','short_stop_drop','push_side'],
 'short_dead':['push_short','push_long','push_side','fh_soft_flip','bh_soft_flip','fh_fast_flip','bh_fast_flip','short_deep_fake','fh_outside_flick','bh_outside_flick'],
 'short_top':['push_short','push_side','fh_soft_flip','bh_soft_flip','fh_fast_flip','bh_fast_flip','fh_sideswipe','bh_sideswipe','bh_press_block','fh_press_block'],
 'half_under_fh':['fh_half_open','fh_half_fast','fh_slow_loop','fh_side_open','push_long','push_short','fh_inside_flick','fh_outside_flick','bh_half_open','heavy_under_push'],
 'half_under_bh':['bh_half_open','bh_half_fast','bh_slow_loop','bh_side_open','push_long','push_short','bh_banana_twist','bh_reverse_twist','fh_half_open','heavy_under_push'],
 'half_top':['fh_half_open','bh_half_open','fh_half_fast','bh_half_fast','fh_fast_loop','bh_fast_loop','bh_press_block','fh_press_block','push_long','middle_jam_counter'],
 'long_under':['fh_open','bh_open','fh_slow_loop','bh_slow_loop','fh_side_open','bh_side_open','fh_fast_loop','bh_fast_loop','heavy_under_push','chop_transition'],
 'long_top':['fh_fast_loop','bh_fast_loop','fh_counter_loop','bh_counter_loop','fh_press_block','bh_press_block','middle_jam_counter','fh_attack_half','bh_attack_half','chop_transition'],
 'long_dead':['fh_fast_loop','bh_fast_loop','fh_counter_loop','bh_counter_loop','middle_jam_counter','fh_press_block','bh_press_block','fh_attack_punch','bh_attack_punch','chop_transition'],
 'rally_top':['fh_counter_loop','bh_counter_loop','fh_fast_loop','bh_fast_loop','fh_press_block','bh_press_block','middle_jam_counter','chop_transition','fh_lob_rescue','bh_lob_rescue'],
 'rally_under':['fh_slow_loop','bh_slow_loop','fh_side_open','bh_side_open','fh_fast_loop','bh_fast_loop','heavy_under_push','chop_transition','short_stop_drop','push_long'],
 'rally_weak':['fh_fast_loop','bh_fast_loop','fh_attack_punch','bh_attack_punch','middle_jam_counter','fh_counter_loop','bh_counter_loop','fh_sideswipe','bh_sideswipe','fh_press_block']
}
assert all(len(x)>=9 for x in SCENARIOS.values())
TECH={**b.TECH,**{name:(path,cn) for name,(path,alias,cn) in MORE.items()}}
ALIASES={**b.ALIASES,**{name:alias for name,(path,alias,cn) in MORE.items()}}
# Several skills in v114 TECH already get handled by original v114 method.
KNOWN=set(b.TECH)
RISKY={'bh_reverse_twist','fh_fast_flip','bh_fast_flip','fh_fast_loop','bh_fast_loop','fh_half_fast','bh_half_fast','short_deep_fake'}
DEFENSIVE={'chop_transition','bh_press_block','fh_press_block','short_stop_drop','push_short','push_long','push_side','heavy_under_push'}


def context(ball):
    short=ball.get('length')=='short';half=ball.get('length')=='half'
    sp=ball.get('spin','top');loc=ball.get('landed','middle')
    under=sp in ('back','side_back');dead=sp=='dead'
    if ball.get('origin')!='service':
        if ball.get('return_state')=='high_ball':return 'rally_weak'
        return 'rally_under' if under else 'rally_top'
    if short:
        if dead:return 'short_dead'
        if sp in ('top','side_top'):return 'short_top'
        if sp=='side_back':return 'short_side_fh' if loc=='fh' else 'short_side_bh'
        return 'short_back_fh' if loc=='fh' else 'short_back_bh'
    if half:return 'half_under_fh' if under and loc=='fh' else 'half_under_bh' if under else 'half_top'
    return 'long_under' if under else 'long_dead' if dead else 'long_top'


def player_aptitude(card,st,action):
    group,child=TECH[action][0].split('.')
    val=card['children'][group][child]
    wing='fh' if action.startswith('fh_') else 'bh' if action.startswith('bh_') else 'table'
    # Explicit weighted drivers: dedicated 43-child, table / receive, read, wing.
    return .38*val+.24*core.gg(card,st,'receive')+.17*core.gg(card,st,'read')+.11*core.gg(card,st,'table')+.10*core.gg(card,st,wing)


def fit(action,ball,pos,ctx):
    wing=ball.get('landed','middle');spin=ball.get('spin');length=ball.get('length','long');q=ball.get('quality',120)
    v=0.
    if pos=='bad':v-=19 if action not in DEFENSIVE else 5
    if pos=='limited':v-=7 if action in RISKY else 2
    if action.startswith('fh_') and wing=='bh':v-=5
    if action.startswith('bh_') and wing=='fh':v-=5
    if length=='short' and ('fast_loop' in action or 'counter_loop' in action):v-=16
    if length=='long' and action in ('push_short','short_stop_drop'):v-=18
    if spin in ('back','side_back') and action in ('fh_press_block','bh_press_block'):v-=12
    if spin in ('top','side_top') and action in ('heavy_under_push','push_long'):v-=11
    if q>137 and action in RISKY:v-=min(13,(q-137)*.32)
    if q<111 and action in ('fh_fast_loop','bh_fast_loop','fh_fast_flip','bh_fast_flip'):v+=4
    return v

# Recorded causal attempt metadata is generated FROM shot state, never narratives first.
CHOICE_AUDIT=Counter()

def choose_policy(card,st,ball,pos,rng):
    ctx=context(ball);choices=SCENARIOS[ctx];q=ball.get('quality',120)
    weights=[]
    for action in choices:
        a=player_aptitude(card,st,action);f=fit(action,ball,pos,ctx)
        w=max(.006,min(9,math.exp((a-115)/27+f/13)))
        if st.get('policy')=='receive_initiative' and action not in DEFENSIVE:w*=1.38
        if st.get('policy')=='defensive_pivot' and action in DEFENSIVE:w*=1.7
        if st.get('policy')=='bh_squeeze' and action.startswith('bh_'):w*=1.35
        if st.get('execute_weakness') and st.get('scouted_weakness')=='bh' and action.startswith('bh_'):w*=1.23
        # Rare deliberate gamble on technically wrong response is possible, not favored.
        weights.append(w)
    chosen=rng.choices(choices,weights=weights)[0]
    CHOICE_AUDIT[(ctx,chosen)]+=1
    return chosen

_old_qual=b.shot_quality
# A per-action additional return-quality penalty affects the ACTUAL model score,
# consequently the error and arrival transitions, not just a prose label.
def quality_policy(card,st,ball,pos,action,rng,step,clutch=False):
    alias=ALIASES.get(action,action)
    # Normalize all short- and long-push variants to defensive contact model.
    if alias in ('push_short','push_long','push_side','push_middle'):alias='push'
    q,pace,spin=_old_qual(card,st,ball,pos,alias,rng,step,clutch)
    if action in TECH:
        a=player_aptitude(card,st,action);ctx=context(ball)
        delta=max(-11.,min(7.,(a-120)*.16))+fit(action,ball,pos,ctx)*.44
        if action in RISKY:delta-=2.0
        q=round(core.clamp(q+delta,60,170),2)
    return q,pace,spin


def action(card,st,ball,pos,rng):
    if pos=='bad' and rng.random()<.60:return 'chop' if card.get('style')=='modern_chopper' else 'block'
    if card.get('style')=='modern_chopper' and ball.get('origin')!='service' and ball['spin'] in ('top','side_top'):
        if rng.random()<.76:return 'chop'
    if ball.get('origin')=='service' or ball.get('origin')=='service_return':return choose_policy(card,st,ball,pos,rng)
    if rng.random()<.44:return choose_policy(card,st,ball,pos,rng)
    return b.choose_action(card,st,ball,pos,rng)


def play_match(cards,seed,*,keep_points=False,fatigue=(25,25),max_games=7):
    saved={k:getattr(b,k) for k in ('choose_action','receive_action','shot_quality')}
    try:
        b.choose_action=action;b.receive_action=choose_policy;b.shot_quality=quality_policy
        result=b.play_match(cards,seed,keep_points=keep_points,fatigue=fatigue,max_games=max_games)
    finally:
        for k,v in saved.items():setattr(b,k,v)
    result['engine']='Spin_Era_V1.1.5_SCENARIO_CAUSAL_CANDIDATE'
    result['scenario_definitions']=len(SCENARIOS)
    result['scenario_response_edges']=sum(map(len,SCENARIOS.values()))
    if keep_points:
        dist=Counter();pairs=Counter();err=Counter();examples=[]
        for game in result['games']:
            for p in game['points']:
                s=p['shots'];a=s[1]['action'] if len(s)>1 else 'unreached'
                serv=s[0];ctx=context({'origin':'service','length':serv.get('length'),'spin':serv.get('spin'),'landed':serv.get('landed')})
                dist[ctx]+=1;pairs[(ctx,a)]+=1
                if a in TECH and len(examples)<12:
                    examples.append({'scenario':ctx,'serve':serv.get('zone'),'spin':serv.get('spin'),
                                     'response':a,'response_cn':TECH[a][1],'player':s[1].get('player'),
                                     'arrived':s[1].get('reach'),'won_by':p['winner'],'strokes':p['strokes']})
        result['response_contexts']=dict(dist)
        result['response_pairs']={f'{k}|{a}':n for (k,a),n in pairs.items()}
        result['causal_examples']=examples
    return result
