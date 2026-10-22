"""One odd-game scoring contract. Core loop preserves BO7 RNG when unchanged."""
from collections import Counter
import game_v112 as core

VERSION = 'V1.18-FORMATS-1'

def validate_format(best_of):
    if type(best_of) is not int or best_of not in (3, 5, 7):
        raise ValueError('best_of must be 3, 5 or 7')
    return best_of // 2 + 1

def server_at(point_index, game_index, first_server=0):
    if first_server not in (0, 1): raise ValueError('first_server must be 0 or 1')
    return (first_server + game_index + (point_index // 2 if point_index < 20 else point_index - 20)) % 2

def score_valid(score):
    if not isinstance(score, list) or len(score) != 2 or any(type(x) is not int or x < 0 for x in score):
        return False
    hi, lo = max(score), min(score)
    return (hi == 11 and lo <= 9) or (lo >= 10 and hi == lo + 2)

def validate_result(result, best_of=None, *, verify_points=True):
    fmt = result.get('best_of', best_of)
    if fmt is None: fmt = 2 * max(result.get('games_won', [0, 0])) - 1
    needed = validate_format(fmt)
    counts = [0, 0]; total = 0
    for gi, g in enumerate(result.get('games', [])):
        if max(counts) >= needed: raise ValueError('game after match clinched')
        score = g['score']
        if not score_valid(score): raise ValueError('invalid game score')
        winner = int(score[1] > score[0])
        if g.get('winner', winner) != winner or g.get('points_count', sum(score)) != sum(score):
            raise ValueError('game winner or point count mismatch')
        counts[winner] += 1; total += sum(score)
        if verify_points and 'points' in g:
            running = [0, 0]
            for p in g['points']:
                if max(running) >= 11 and abs(running[0]-running[1]) >= 2: raise ValueError('point after game ended')
                if p.get('score_before') != running or p.get('winner') not in (0, 1): raise ValueError('point chronology mismatch')
                if p.get('server') != server_at(sum(running), gi, result.get('first_server', 0)): raise ValueError('service order mismatch')
                running[p['winner']] += 1
            if running != score: raise ValueError('game and point totals differ')
    if counts != result.get('games_won') or max(counts) != needed or result.get('winner') != counts.index(needed):
        raise ValueError('match score or winner mismatch')
    if result.get('points', total) != total: raise ValueError('total point count mismatch')
    return True

def core_match(cards,seed,*,keep_points=False,fatigue=(25,25),max_games=7):
    if max_games not in (3,5,7) or len(cards)!=2:raise ValueError('BO3/5/7 two players required')
    rng=core.rng_of('SPIN-ERA-1.1.2','MATCH',seed)
    states=[core.warmup(cards[i],rng,fatigue[i]) for i in (0,1)]
    won=[0,0];games=[];checks=[];total_strokes=0;points=0;reaches=Counter();outcomes=Counter();actions=Counter();rallies=[]
    for gi in range(max_games):
        score=[0,0];pl=[]
        while max(score)<11 or abs(score[0]-score[1])<2:
            srv=core.serve_side(sum(score),gi)
            before=score.copy()
            winner,n,shots,reason=core.point(cards,states,rng,srv,score,keep_shots=keep_points)
            score[winner]+=1;points+=1;total_strokes+=n;rallies.append(n);outcomes[reason]+=1
            if keep_points:pl.append({'score_before':before,'server':srv,'winner':winner,'strokes':n,'reason':reason,'shots':shots})
            for s in shots:
                if s.get('reach') in ('good','limited','bad','miss'):reaches[s['reach']]+=1
                if s.get('return_state') in ('strong_return','neutral_return','high_ball'):outcomes[s['return_state']]+=1
                if s.get('action'):actions[s['action']]+=1
            core.attempt_in_game_adaptation(cards,states,rng,score,gi)
            if points>1500:raise RuntimeError('implausible length')
        w=0 if score[0]>score[1] else 1;won[w]+=1
        g={'score':score,'winner':w,'points_count':sum(score)}
        if keep_points:g['points']=pl
        games.append(g)
        for s in states:s['match_stamina']+=sum(score)/max(35.,s['p_eff']['stamina'])*2
        if won[w]==max_games//2+1:break
        checks.extend(core.between_games(cards,states,rng,gi+1))
    counts=Counter()
    spins=Counter()
    ret=Counter()
    tactics=[]
    for i,s in enumerate(states):
        counts.update(s['serve_forms']);ret.update(s['return_forms']);
        tactics.extend([dict(x,player=cards[i].get('player_id',str(i))) for x in s['policy_events']])
    return {'seed':seed,'engine':core.V112_TAG,'winner':0 if won[0]==max_games//2+1 else 1,'games_won':won,'games':games,'points':points,
      'total_strokes':total_strokes,'mean_strokes':round(total_strokes/points,3),'rallies':rallies,
      'reaches':dict(reaches),'outcomes':dict(outcomes),'actions':dict(actions),
      'serve_distribution':dict(counts),'return_distribution':dict(ret),
      'tactical_events':tactics,'between_game_checks':checks,
      'match_form':[{'form_initial':s['form_initial'],'p_roll':s['p_roll'],'psychological_state':s['mental'],
       'initial_final_tactics':s['policy'],'counter_level':s['policy_stage']} for s in states],
      'status':'SIMULATED_NONHISTORICAL_V112_TEST'}
