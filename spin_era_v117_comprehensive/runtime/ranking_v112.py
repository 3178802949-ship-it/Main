"""Independent Spin Era Unified Ranking proposal, NOT an official historical ITTF ranking.
Two parallel ledgers: competitive Elo and seasonal placement-derived points.
Periods before and after 2018 use appropriate read-only historical references,
but ONE internal point table maintains comparability across eras.
"""
from __future__ import annotations
from dataclasses import dataclass,field
from math import pow
from datetime import date
from typing import Optional

LEVEL={'olympics':2000,'world_championships':2000,'world_cup':1500,
 'wtt_grand_smash':2000,'wtt_champions':1000,'wtt_star_contender':600,
 'wtt_contender':400,'wtt_feeder':125,'pro_tour_major':600,
 'pro_tour_open':400,'continental':500,'international_challenge':125}
# Position reaching a round is awarded for an ENTIRE EVENT, not each win.
FINISH={'champion':1.,'runner_up':.70,'semifinal':.35,'quarterfinal':.175,
 'r16':.088,'r32':.043,'r64':.020,'r128':.008,'qualifier_only':.003}
@dataclass
class Rating:
    name:str
    elo:float=1500.
    youth_elo:float=1500.
    youth_match_count:int=0
    match_count:int=0
    last_date:str=''
    results:list=field(default_factory=list)
    youth_points:list=field(default_factory=list)
    team_points:list=field(default_factory=list)

def expected(a,b):return 1/(1+10**((b-a)/400))
def settle_singles(a:Rating,b:Rating,winner:str,when:str,importance=1.,kind='adult_singles'):
    if winner not in (a.name,b.name):raise ValueError('winner not among players')
    outcome=1.0 if winner==a.name else 0.0
    if kind not in ('adult_singles','youth_singles'):raise ValueError('rating kind unsupported')
    rating_field='elo' if kind=='adult_singles' else 'youth_elo'
    count_field='match_count' if kind=='adult_singles' else 'youth_match_count'
    p=expected(getattr(a,rating_field),getattr(b,rating_field))
    # Decaying K makes well-established ratings more stable.
    k=22 if min(getattr(a,count_field),getattr(b,count_field))>=30 else 32
    delta=round(k*max(.5,min(1.5,importance))*(outcome-p),4)
    setattr(a,rating_field,getattr(a,rating_field)+delta);setattr(b,rating_field,getattr(b,rating_field)-delta)
    setattr(a,count_field,getattr(a,count_field)+1);setattr(b,count_field,getattr(b,count_field)+1)
    a.last_date=b.last_date=when
    return {'match_date':when,'players':[a.name,b.name],'pre_win_prob_A':round(p,4),'elo_delta_A':delta,
      'elo_after':[round(getattr(a,rating_field),2),round(getattr(b,rating_field),2)],'winner':winner,'kind':kind}

def event_points(level,finish,*,qualifier_wins=0,qualification_bonus_cap=.02):
    if level not in LEVEL or finish not in FINISH:raise ValueError('unsupported event / finish')
    base=LEVEL[level]
    # 0.3% for reaching qualifier stages, no high payoff for 1 lucky win
    bonus=min(qualification_bonus_cap,qualifier_wins*.004) if finish=='qualifier_only' else 0
    return round(base*(FINISH[finish]+bonus),2)

def record_result(player:Rating,event_id,when,level,finish,qualifier_wins=0,kind='adult_singles'):
    if any(e['event_id']==event_id for e in player.results+player.youth_points+player.team_points):
        raise ValueError('duplicate event ID')
    if kind not in ('adult_singles','youth_singles','team'):
        raise ValueError('unknown ledger')
    e={'event_id':event_id,'date':when,'level':level,'finish':finish,
        'points':event_points(level,finish,qualifier_wins=qualifier_wins),'kind':kind}
    {'adult_singles':player.results,'youth_singles':player.youth_points,'team':player.team_points}[kind].append(e)
    return e

def adult_ranking_points(player:Rating,asof:str,top_n=8,expiry_days=365):
    day=date.fromisoformat(asof)
    eligible=[e for e in player.results if 0<=(day-date.fromisoformat(e['date'])).days<=expiry_days]
    return round(sum(sorted((e['points'] for e in eligible),reverse=True)[:top_n]),2)

def leaderboard(players,asof):
    return [(i+1,p.name,adult_ranking_points(p,asof),round(p.elo,2)) for i,p in enumerate(sorted(players,
        key=lambda x:(-adult_ranking_points(x,asof),-x.elo,x.name)))]
