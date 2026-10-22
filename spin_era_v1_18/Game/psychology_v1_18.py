"""Optional, symmetric and fully auditable score-context hypothesis.

These coefficients are design assumptions, not a claim about real psychology.
Independent deterministic streams avoid perturbing the existing match RNG.
"""
import hashlib
import random
from common import canonical_json
import game_v112 as core

VERSION = 'V1.18-ANTI-SHUTOUT-2'
MAX_DELTA = .085

def _smooth(x):
    x = max(0., min(1., x))
    return x*x*(3-2*x)

def adjust_probability(p0, score, cards, states, server, *, seed, game_index, point_index):
    leader = int(score[1] > score[0]); trailer = 1-leader
    gap = abs(score[0]-score[1])
    strength = _smooth((max(score)-7)/4) * _smooth((gap-4)/5)
    if min(score) >= 10: strength = 0.
    def draw(label):
        token = hashlib.sha256(canonical_json([seed, game_index, point_index, score, label]).encode()).digest()
        return random.Random(int.from_bytes(token[:8], 'big')).random()
    slack_draw, comeback_draw = draw('slack'), draw('comeback')
    stable = core.gg(cards[leader], states[leader], 'stable')
    reading = core.gg(cards[trailer], states[trailer], 'read')
    pressure = cards[trailer]['children']['stable']['pressure']
    fatigue = states[leader].get('match_stamina', 0.)
    slack_p = max(.05, min(.55, .24 + .012*fatigue - .002*(stable-120)))
    comeback_p = max(.05, min(.55, .24 + .0015*(reading-120) + .001*(pressure-120) + (.02 if server==trailer else 0)))
    slack, comeback = slack_draw < slack_p, comeback_draw < comeback_p
    adjustment = MAX_DELTA * strength * (.6*slack + .4*comeback)
    post = min(.999, max(.001, p0 + adjustment*(1 if trailer==0 else -1)))
    return post, dict(game_index=game_index, point_index=point_index, score_before=list(score),
        server=server, leader=leader, trailing=trailer, pre_p=p0, slack_draw=slack_draw,
        comeback_draw=comeback_draw, slack_probability=slack_p, comeback_probability=comeback_p,
        slack_succeeded=bool(slack and strength), comeback_succeeded=bool(comeback and strength),
        activation_strength=strength, delta_p=post-p0, post_p=post, seed=seed,
        version=VERSION, source='DESIGN_HYPOTHESIS_NOT_OBSERVED_EMOTION')
