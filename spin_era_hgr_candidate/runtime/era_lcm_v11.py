"""Era LCM candidate: Learning, Counterplay, Migration. Opt-in TEST ONLY.
Uses verified exposure/events, never asserts a worldline innovation is historical fact.
"""
from __future__ import annotations
from copy import deepcopy
import math,hashlib,random
DNA={
 '2000_2004': {'problem':'small-ball speed after 21->11 and 40mm transitions','innovations':['serve_return_variation','near_table_transition'],'counter':['receive_reading','placement_compression']},
 '2004_2008': {'problem':'penhold FH dependence and RPB continuous follow-up','innovations':['reverse_penhold_backhand','active_receive'],'counter':['wide_bh_pressure','middle_short']},
 '2008_2012': {'problem':'fast receive initiation and BH transition','innovations':['banana_flick','two_wing_counter'],'counter':['short_deception','spin_reading']},
 '2012_2016': {'problem':'serve receive plus versatile attack system','innovations':['two_wing_initiative','transition_depth'],'counter':['early_counter','quality_chains']},
 '2016_2021': {'problem':'increased shot quality and athletic continuity','innovations':['high_quality_rally','spin_speed_mix'],'counter':['deep_receive','body_line_attack']},
 '2021_2024': {'problem':'near-table speed and top-player adaptation','innovations':['fast_transition','backhand_pressure'],'counter':['pace_deception','counter_reading']},
 '2024_2028': {'problem':'emerging next-generation style competition','innovations':['advanced_banana','rapid_forehand_reset'],'counter':['serve_placement','multi_line_reading']}}

def apply_exposure(world,event_id,recipient,technical_feature,source,year,recording_access,club_contact,month,seed):
    """Probabilistic exposure -> awareness -> testing -> adaptation (not free core G)."""
    key=f'{recipient}|{technical_feature}|{event_id}'
    if key in world.setdefault('event_ids',[]):raise ValueError('repeat event rejected')
    if source not in ('REAL_MENS_BASELINE','SIMULATED','ASSESSMENT'):raise ValueError('unclear source')
    r=random.Random(int.from_bytes(hashlib.sha256(f'{seed}|{recipient}|{technical_feature}|{month}'.encode()).digest()[:8],'big'))
    exposure=clamp(.06+recording_access*.25+club_contact*.40,.02,.83)
    aware=r.random()<exposure
    trial=aware and r.random()<.18+.25*club_contact
    counter=trial and r.random()<.18
    world.setdefault('tech_awareness',{})[str(recipient)+':'+technical_feature]={'aware':aware,'trial':trial,'counter_play':counter,'since':month,'source':source}
    world['event_ids'].append(key)
    return world['tech_awareness'][str(recipient)+':'+technical_feature]

def clamp(x,lo,hi):return min(hi,max(lo,x))
