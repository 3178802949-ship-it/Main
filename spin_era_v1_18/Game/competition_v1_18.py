"""Explicit group formats, multiway ties and evidence-qualified historical draws."""
from fractions import Fraction
import copy
import hashlib
import random
from common import canonical_json
from Game.formats_v1_18 import validate_format, validate_result

VERSION='V1.18-COMPETITION-1'
DEFAULT_TIEBREAKS=('wins','head_to_head','game_difference','point_ratio','point_difference')

def group_table(players,matches,*,best_of=5,tiebreaks=DEFAULT_TIEBREAKS):
    validate_format(best_of)
    if len(set(players))!=len(players) or len(players)<2:raise ValueError('distinct group players required')
    if tuple(tiebreaks)!=DEFAULT_TIEBREAKS and (not tiebreaks or tiebreaks[0]!='wins' or not set(tiebreaks)<=set(DEFAULT_TIEBREAKS)):
        raise ValueError('explicit supported tie-break sequence required')
    rows={p:dict(player_id=p,wins=0,losses=0,games_for=0,games_against=0,points_for=0,points_against=0) for p in players}
    seen=set()
    for m in matches:
        validate_result(m)
        if m.get('best_of')!=best_of:raise ValueError('MIXED_GROUP_FORMAT')
        a,b=m['participant_ids'];pair=frozenset((a,b))
        if a not in rows or b not in rows or len(pair)!=2 or pair in seen:raise ValueError('duplicate or foreign group pairing')
        seen.add(pair)
        for i,p in enumerate((a,b)):
            r=rows[p];r['wins']+=m['winner']==i;r['losses']+=m['winner']!=i
            r['games_for']+=m['games_won'][i];r['games_against']+=m['games_won'][1-i]
            r['points_for']+=sum(g['score'][i] for g in m['games']);r['points_against']+=sum(g['score'][1-i] for g in m['games'])
    tie_groups={}
    for p,row in rows.items():tie_groups.setdefault(row['wins'],[]).append(p)
    mini={p:dict(wins=0,gf=0,ga=0,pf=0,pa=0) for p in players}
    for peers in tie_groups.values():
        for m in matches:
            if set(m['participant_ids'])<=set(peers):
                for i,p in enumerate(m['participant_ids']):
                    t=mini[p];t['wins']+=m['winner']==i;t['gf']+=m['games_won'][i];t['ga']+=m['games_won'][1-i]
                    t['pf']+=sum(g['score'][i] for g in m['games']);t['pa']+=sum(g['score'][1-i] for g in m['games'])
    def key(p):
        r=rows[p];t=mini[p]
        values=dict(wins=(r['wins'],),head_to_head=(t['wins'],Fraction(t['gf'],max(1,t['ga'])),Fraction(t['pf'],max(1,t['pa']))),
            game_difference=(r['games_for']-r['games_against'],),point_ratio=(Fraction(r['points_for'],max(1,r['points_against'])),),
            point_difference=(r['points_for']-r['points_against'],))
        return tuple(v for criterion in tiebreaks for v in values[criterion])
    ordered=sorted(players,key=lambda p:(tuple(-v for v in key(p)),p))
    for i,p in enumerate(ordered):
        rows[p].update(rank=1+sum(key(q)>key(p) for q in players),display_order=i+1,
            head_to_head_mini_table=mini[p],unresolved_sporting_tie=sum(key(p)==key(q) for q in players)>1,
            stable_id_order_is_not_sporting_resolution=True)
    return dict(version=VERSION,best_of=best_of,tiebreaks=list(tiebreaks),standings=[rows[p] for p in ordered],
        complete=len(seen)==len(players)*(len(players)-1)//2,
        historical_status='EXPLICIT_SIMULATION_RULES_NOT_AUTHENTICATED_HISTORICAL_REGULATIONS')

def historical_replacement(entries,player_id,*,seed,qualification_tier,source_refs=()):
    """Only replace a supplied low slot. Never invent real attendance."""
    if not entries or len({x.get('player_id') for x in entries})!=len(entries):raise ValueError('unique supplied entries required')
    eligible=[x for x in entries if x.get('qualification_tier')==qualification_tier and not x.get('confirmed_seed') and not x.get('confirmed_deep_run')]
    if not eligible:raise ValueError('NO_EVIDENCE_COMPATIBLE_LOW_SLOT')
    chosen=random.Random(seed).choice(sorted(eligible,key=lambda x:x['player_id']))
    draw=copy.deepcopy(entries)
    for x in draw:
        if x['player_id']==chosen['player_id']:
            x.update(player_id=player_id,replaces=chosen['player_id'],classification='SIMULATED_REPLACEMENT')
    verified=bool(source_refs) and all(x.get('evidence_status')=='VERIFIED_ATTENDANCE_AND_SLOT' for x in entries)
    return dict(draw=draw,removed_player_id=chosen['player_id'],seed=seed,source_refs=list(source_refs),
        status='EVIDENCE_QUALIFIED_ALTERNATIVE_BRANCH' if verified else 'HYPOTHETICAL',
        source_entries_sha256=hashlib.sha256(canonical_json(entries).encode()).hexdigest(),
        historical_winners_protected_after_actual_player_victory=False)


def qualifiers(table,count):
    if type(count)is not int or not 0<count<len(table['standings']):raise ValueError('qualification count must split the group')
    if not table.get('complete'):raise ValueError('INCOMPLETE_GROUP')
    rows=table['standings']
    if rows[count-1]['rank']==rows[count]['rank']:raise ValueError('UNRESOLVED_GROUP_TIE_NEEDS_DECLARED_PROCEDURE')
    return [r['player_id'] for r in rows[:count]]
