"""Isolated Game runner. All compatibility hooks are scoped and restored."""
import hashlib
import json
from pathlib import Path
import sys
from common import canonical_json
from Game import engine_v1_18 as detailed
from Game import light_v1_18 as light
from Game import formats_v1_18 as formats
from Game import preferences_v118 as preferences
from Game import fatigue_v1_18 as fatigue_patch
import game_v113 as serve_layer


def run(request):
    audit = {c['player_id']: preferences.new_audit(c) for c in request['cards']}
    core = detailed.core
    saved = dict(action=detailed.action_distribution, light=light.shared_action_distribution,
                 runner=core.play_match, serve=core.serve_side,warmup=core.warmup,serve_warmup=serve_layer._old_warm)
    original = detailed.action_distribution
    original_warmup=core.warmup
    physical_audit=[]
    def warmup(card,rng,fatigue=25):
        state=original_warmup(card,rng,fatigue)
        if request.get('physical_fatigue',True):
            fatigue_patch.apply(state,fatigue)
            physical_audit.append(dict(player_id=card['player_id'],**state['physical_fatigue_audit']))
        return state
    def action(card, state, ball, position, tactic):
        return preferences.apply_preferences(original(card,state,ball,position,tactic), card,state,ball,position,
            audit=audit[card['player_id']])
    try:
        detailed.action_distribution = action; light.shared_action_distribution = action
        core.play_match = formats.core_match
        core.warmup=warmup;serve_layer._old_warm=warmup
        core.serve_side = lambda point_index, game_index: formats.server_at(point_index, game_index, request.get('first_server',0))
        kwargs = dict(keep_points=request['detail_level']=='full', fatigue=tuple(request['fatigue']), max_games=request['max_games'])
        if request['detail_level']=='full':
            result = detailed.play_match(request['cards'],request['seed'],**kwargs)
        else:
            result = light.play_match(request['cards'],request['seed'],**kwargs,
                anti_shutout=request.get('anti_shutout',False), first_server=request.get('first_server',0),
                audit_points=request.get('audit_points',True))
    finally:
        detailed.action_distribution=saved['action'];light.shared_action_distribution=saved['light']
        core.play_match=saved['runner'];core.serve_side=saved['serve'];core.warmup=saved['warmup'];serve_layer._old_warm=saved['serve_warmup']
    result['best_of']=request['max_games']; result['first_server']=request.get('first_server',0)
    result['style_preference_audit']=[audit[c['player_id']] for c in request['cards']]
    result['format_rules']=dict(version=formats.VERSION, best_of=request['max_games'],games_to_win=request['max_games']//2+1,
        game_points=11, win_by=2, service_before_deuce=2,service_after_deuce=1,
        deciding_game_change_ends_at=5,geometry_frame='PLAYER_RELATIVE_CANONICAL_ENDS',
        physical_court='SYMMETRIC_NO_END_ADVANTAGE',
        end_changes=[dict(after_game_index=i,reason='BETWEEN_GAMES') for i in range(len(result['games'])-1)] +
            ([dict(game_index=request['max_games']-1,at_first_score_reaching=5,reason='DECIDING_GAME',
                point_index_exact=next((j for j,p in enumerate(result['games'][-1].get('points',[])) if max(p['score_before'])>=5),None))]
                if len(result['games'])==request['max_games'] else []))
    result['physical_fatigue_enabled']=request.get('physical_fatigue',True)
    # Validation probes also warm up at fatigue25. Keep only actual-match rows
    # (the final two calls) so the audit follows the supplied actor ordering.
    result['physical_fatigue_audit']=physical_audit[-2:] if physical_audit else []
    rows=result.get('psychology_audit',[])
    result['anti_shutout']=request.get('anti_shutout',False)
    result['psychology_audit_sha256']=hashlib.sha256(canonical_json(rows).encode()).hexdigest()
    result['psychology_summary']=dict(enabled=result['anti_shutout'],audited_points=len(rows),
        adjusted_points=sum(abs(x['delta_p'])>1e-14 for x in rows),max_absolute_delta=max((abs(x['delta_p']) for x in rows),default=0.),
        bound=.085, default_enabled=False,mechanism='INDEPENDENT_SLACK_AND_COMEBACK_DRAWS_BEFORE_POINT_SAMPLE')
    root=Path(__file__).resolve().parents[1]
    for name in ('worker_v1_18.py','fatigue_v1_18.py','formats_v1_18.py','psychology_v1_18.py','engine_v1_18.py','light_v1_18.py'):
        p=root/'Game'/name;result.setdefault('mechanics_source_sha256',{})[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def main():
    json.dump(run(json.load(sys.stdin)),sys.stdout,ensure_ascii=False,allow_nan=False)
if __name__=='__main__':main()
