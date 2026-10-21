"""Point-level aggregate match model for background V1.1.7 competitions.

This is an explicitly approximate alternative to the shot engine. It does not
run that engine, create a fictitious shot sequence, or use CA to pick winners.
Actual point draws use effective technical traits, P6, initial daily form,
serve/receive, contact families and bounded fatigue. The 11-point/two-clear
scoring rules remain exact. Contact exposure, rally lengths and movement are
sampled aggregate estimates and must never be narrated as observed shots.
"""
from __future__ import annotations

from collections import Counter
import copy
import math

from common import SCHEMA
from Game.geometry import normalize_hand
from Game import observed_tactics
from Game import tactics_v117 as plans
from Game.engine_v117 import technique_components, technical_error_adjustment, action_distribution as shared_action_distribution
from Game import geometry as geo
import game_v112 as core
import specialist_rubber_v116 as rubbers

TAG = 'V1.1.7-LIGHT-4'
OFFENSIVE = frozenset(('attack', 'open', 'counter', 'flip', 'slow_loop'))
PATHS = frozenset(f'{g}.{k}' for g, values in SCHEMA['subskill_weights_pct'].items() for k in values)
# Mirror the detailed serve-quality formula: .30 G9 + .08 spin + .09 placement.
# A single service contact contributes exactly one sampled technical exposure.
SERVE_RECIPE = {f'serve.{key}': (.30 * weight / 100 + (.08 if key == 'spin' else 0)
                                + (.09 if key == 'placement' else 0)) / .47
                for key, weight in SCHEMA['subskill_weights_pct']['serve'].items()}


def _finite(value, name, lo=0., hi=150.):
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f'invalid {name}')
    return float(value)


def _validate(cards, seed, fatigue, max_games, keep_points):
    if not isinstance(cards, (list, tuple)) or len(cards) != 2:
        raise ValueError('two distinct match cards required')
    if type(seed) is not int or type(max_games) is not int or max_games not in (3, 5, 7):
        raise ValueError('integer seed and BO3/BO5/BO7 required')
    if keep_points is not False:
        raise ValueError('light matches provide aggregate evidence only; choose detailed mode for points/shots')
    if len(fatigue) != 2:
        raise ValueError('two fatigue values required')
    ids = []
    for i, card in enumerate(cards):
        ids.append(card.get('player_id'))
        if not isinstance(ids[-1], str) or not ids[-1]:
            raise ValueError('player identity required')
        if set(card.get('children', {})) != set(SCHEMA['core_order']):
            raise ValueError('complete G43 traits required')
        for group, children in SCHEMA['subskill_weights_pct'].items():
            if set(card['children'][group]) != set(children):
                raise ValueError('complete G43 traits required')
            for key, value in card['children'][group].items():
                _finite(value, f'{group}.{key}')
        for key in core.P:
            _finite(card['P6'][key], key)
        for key in core.G:
            _finite(card['G9'][key], key)
        _finite(fatigue[i], 'fatigue', 0, 100)
        normalize_hand(card)
        for wing in ('fh', 'bh'):
            rubbers.rubber_for(card, wing)
    if ids[0] == ids[1]:
        raise ValueError('player identities must differ')


def contact_recipe(action, wing):
    """Use the detailed engine's pure recipe, without running its match runner."""
    return technique_components(action, wing)


def contact_skill(card, state, action, wing):
    recipe = contact_recipe(action, wing)
    raw = sum(card['children'][path.split('.')[0]][path.split('.')[1]] * w for path, w in recipe.items())
    # Own daily form affects the actual wing, regardless of the contact name.
    # P is used in movement/pace, rather than a second global attack-quality bonus.
    family = rubbers.action_spec(action)['family']
    if family in ('chop', 'block', 'open', 'slow_loop', 'counter', 'attack'):
        own_form = .52 * (core.gg(card, state, wing) - card['G9'][wing])
    else:
        own_form = (.30 * (core.gg(card, state, 'table') - card['G9']['table'])
                    + .25 * (core.gg(card, state, wing) - card['G9'][wing]))
    return raw + own_form


def contact_properties(card, state, action, wing, incoming_spin, incoming_strength=120., incoming_quality=120.):
    """Resolve one representative contact with family-specific physical pace."""
    skill = contact_skill(card, state, action, wing)
    family = rubbers.action_spec(action)['family']
    if family == 'chop':
        pace, spin = 113 + .24 * (skill - 120), 'back'
    elif family == 'push':
        pace, spin = 100 + .19 * (skill - 115), 'back'
    elif family == 'block':
        pace, spin = 105 + .24 * (skill - 118), 'top'
    elif family == 'lob':
        pace, spin = 90 + .08 * (skill - 120), 'top'
    elif family == 'flip':
        pace, spin = 121 + .30 * (skill - 120), 'top'
    else:
        pace, spin = 131 + .39 * (skill - 125) + .13 * (state['p_eff']['burst'] - 120), 'top'
        if family == 'slow_loop':
            pace -= 9
    contact = rubbers.resolve_contact(rubbers.rubber_for(card, wing), action,
        dict(spin=incoming_spin, length='long', quality=incoming_quality, spin_strength=incoming_strength),
        base_spin=spin, base_pace=pace, base_strength=core.clamp(skill, 0, 170))
    if state.get('light_plan'):
        contact = plans.contact_properties(contact, state['light_plan'], family, state.get('light_last_family'))
    return contact


def _wing(card, state, rng, defensive=False):
    metric = 'defense' if defensive else 'spin'
    values = [.60 * core.gg(card, state, w) + .40 * card['children'][w][metric] for w in ('fh', 'bh')]
    return rng.choices(('fh', 'bh'), weights=[math.exp(core.clamp((v - 120) / 22, -4, 3)) for v in values])[0]


def _defending_lane(hitter_card, receiver_card, wing, hitter_state, rng):
    """Map chosen cross/straight lines by public hands; no hidden opponent G read."""
    hh, rh = normalize_hand(hitter_card), normalize_hand(receiver_card)
    policy = hitter_state.get('policy')
    cross = rng.random() < (.50 if policy == 'wide_angles' else .68)
    read = core.gg(hitter_card, hitter_state, 'read')
    known = observed_tactics.inferred_weakness(hitter_state)
    if known in ('fh', 'bh') and rng.random() < core.clamp(.22 + .006 * (read - 100), .12, .55):
        return known, 'observed_weak_side', hh != 'unknown' and rh != 'unknown'
    if policy == 'bh_squeeze' and rng.random() < .40:
        return 'bh', 'bh_pressure', hh != 'unknown' and rh != 'unknown'
    if hh == 'unknown' or rh == 'unknown':
        return rng.choice(('fh', 'bh')), 'unresolved_anatomy', False
    # Same-handed crosscourt is like-wing; opposite-handed crosscourt is the
    # opposite wing. Down the line reverses that relationship.
    same = hh == rh
    opposite = (not same) if cross else same
    return ('bh' if wing == 'fh' else 'fh') if opposite else wing, 'crosscourt' if cross else 'straight', True


def _choose_contact(card, state, wing, incoming_spin, incoming_quality, rng, defending=False,
                    incoming_pace=125., incoming_strength=120., incoming_arc='normal'):
    ball = dict(origin='rally', third_phase='rally', return_state='neutral_return', spin=incoming_spin, length='long',
        quality=incoming_quality, landed=wing, pace=incoming_pace, spin_strength=incoming_strength,
        backspin_strength=incoming_strength if incoming_spin in ('back', 'side_back') else 0., arc=incoming_arc)
    selection = plans.choose_plan(card, state, ball, None, rng)
    state['light_plan'] = selection['plan']
    state['light_preparation_depth'] = selection['preparation_depth']
    estimated_pace = (131 + .39 * (core.gg(card, state, wing) - 125)
                      + .13 * (state['p_eff']['burst'] - 120))
    arrival = _arrival(card, state, wing, estimated_pace, ball, incoming_quality, 3.)
    grades = arrival['grades']
    position = (rng.choices([grade for grade, _, _ in grades], weights=[p for _, p, _ in grades])[0]
                if sum(p for _, p, _ in grades) > 1e-12 else 'bad')
    state['hgr_last_family'] = state.get('light_last_family')
    options = shared_action_distribution(card, state, ball, position, selection['plan'])
    selected = rng.choices(options, weights=[candidate['probability'] for candidate in options])[0]
    state['light_contact_wing'] = selected['wing']
    state['light_sampled_arrival'] = position
    state['light_wing_mismatch'] = selected['wing'] != wing
    return selected['action']


def _cdf(z):
    return .5 * (1 + math.erf(z / math.sqrt(2)))


def _phi(z):
    return math.exp(-z * z / 2) / math.sqrt(2 * math.pi)


def _quality_moments(mean, delta, strong):
    """Clipped N(mean,7) moments; integrate the strong-return threshold exactly."""
    sd, lo, hi = 7., 60., 168.
    zl, zu = (lo - mean) / sd, (hi - mean) / sd
    pl, pu = _cdf(zl), _cdf(zu)
    expected = lo * pl + mean * (pu - pl) + sd * (_phi(zl) - _phi(zu)) + hi * (1 - pu) + delta
    if not strong:
        return expected, 0., 0., 0.
    zt = (140 - delta - mean) / sd
    pt, tail = _cdf(zt), 1 - pu
    interval = pu - pt
    center = mean + delta
    first = center * interval + sd * (_phi(zt) - _phi(zu)) + (hi + delta) * tail
    second = ((center * center + sd * sd) * interval
              + 2 * center * sd * (_phi(zt) - _phi(zu))
              + sd * sd * (zt * _phi(zt) - zu * _phi(zu)) + (hi + delta) ** 2 * tail)
    return expected, 1 - pt, first, second


def _movement(card, state, wing, own_pace, expected_contacts):
    """Expected movement over the published target grid; no invented positions."""
    depth = state.get('light_preparation_depth', 1.18)
    feet = core.gg(card, state, 'feet')
    fraction = core.clamp((.32 + feet * .002) * 115 / max(85, own_pace), .25, .72)
    key = (depth, wing, round(fraction, 2))
    cache = state.setdefault('light_geometry_cache', {})
    if key not in cache:
        grid = (-.94, -.65, 0., .65, .94, 0.)
        spread = 1.12 if depth <= 1.10 else 1.18
        offset = .25 if wing == 'fh' else -.25
        first = steady = reverse = recovery_distance = 0.
        for previous in grid:
            body = previous * spread - offset
            stance = body * (1 - fraction)
            momentum = -body * fraction
            recovery_distance += abs(body * fraction) * geo.HALF_WIDTH_M / len(grid)
            for following in grid:
                dx = (following * spread - stance) * geo.HALF_WIDTH_M
                first += math.hypot(following * spread * geo.HALF_WIDTH_M,
                                    (depth - 1.12) * geo.HALF_LENGTH_M) / 36
                steady += abs(dx) / 36
                reverse += int((following * spread - stance) * momentum < -.015) / 36
        recovery_cost = (1 - (.58 + fraction * .5)) * 3 + 2.5 * reverse
        cache[key] = first, steady, recovery_cost, recovery_distance
    first, steady, recovery_cost, recovery_distance = cache[key]
    first_fraction = min(1., 1 / max(1., expected_contacts))
    distance = first_fraction * first + (1 - first_fraction) * steady
    return distance, (1 - first_fraction) * recovery_cost, distance + recovery_distance


def _arrival(card, state, wing, own_pace, incoming_contact, incoming_quality, expected_contacts):
    """Shared arrival proxy for representative menu and absorbing phases."""
    distance, recovery_cost, movement = _movement(card, state, wing, own_pace, expected_contacts)
    p = state['p_eff']
    reach_skill = (.50 * core.gg(card, state, 'feet') + .19 * p['speed'] + .15 * p['agility']
                   + .10 * p['flexibility'] + .06 * core.gg(card, state, 'read'))
    spin = incoming_contact['spin']
    strength = incoming_contact['spin_strength']
    spin_demand = core.clamp((strength - 100) * .035, -2., 3.2) if spin in ('top', 'side_top') else 0.
    arc_demand = {'high': -2.4, 'defensive_arc': -1.4, 'flat': 1.1,
                  'low': .7, 'low_defensive': .2, 'slow_low': -.8}.get(incoming_contact['arc'], 0.)
    load = (distance * .30 + .12 + max(0, incoming_contact['pace'] - 110) * .001) * 120 / max(40, p['stamina'])
    demand = (121 + .29 * (incoming_quality - 120) + .22 * (incoming_contact['pace'] - 120)
              + 7 * distance / geo.HALF_WIDTH_M + recovery_cost + 1.04
              + state['match_stamina'] * .16 + min(5., load * .16) + spin_demand + arc_demand)
    mu = reach_skill - demand
    miss = _cdf((-21 - mu) / 11)
    bad_boundary, limited_boundary = _cdf((-10 - mu) / 11), _cdf((2 - mu) / 11)
    grades = (('bad', bad_boundary - miss, -25.), ('limited', limited_boundary - bad_boundary, -13.),
              ('good', 1 - limited_boundary, 0.))
    return dict(distance=distance, movement=movement, load=load, spin_demand=spin_demand,
                miss=miss, grades=grades)


def _phase(card, state, skill, family, wing, own_contact, incoming_contact, incoming_quality, expected_contacts, clutch):
    """Integrate reach grades, technical errors and legal direct-winner hazards."""
    arrival = _arrival(card, state, wing, own_contact['pace'], incoming_contact, incoming_quality, expected_contacts)
    distance, movement, load, spin_demand, miss, grades = (arrival[key] for key in
        ('distance', 'movement', 'load', 'spin_demand', 'miss', 'grades'))
    spin, strength = incoming_contact['spin'], incoming_contact['spin_strength']
    active = family in OFFENSIVE
    stable = core.gg(card, state, 'stable') + (state['clutch_bonus'] if clutch else 0)
    base_adjustment = (.035 if active else 0.)
    if family == 'chop':
        base_adjustment -= .03 if spin in ('top', 'side_top') else .004
    if spin in ('back', 'side_back') and active:
        base_adjustment += .027 + core.clamp((strength - 125) * .002, 0., .045)
    base_adjustment += core.clamp((incoming_quality - 130) * .0016, -.022, .071)
    base_adjustment -= core.clamp((stable - 120) * .0010, -.018, .040)
    exposure = state.get('light_spin_exposure', {}).get(incoming_contact['rubber'] + ':' + spin, 0)
    base_adjustment += (incoming_contact['variation'] * .045
                        * core.clamp((145 - core.gg(card, state, 'read')) / 70, .1, .9) / (1 + exposure / 12))
    base_adjustment += technical_error_adjustment(skill) + min(.045, load * .0015)
    if spin in ('top', 'side_top'):
        base_adjustment += (core.clamp((strength - 100) * .00045, -.018, .032)
                            * core.clamp((145 - card['children']['receive']['spin_read']) / 60, .15, 1.))
    if state.get('light_plan') == 'pips_early_pressure':
        base_adjustment += .008
    conflict = (core.clamp(6 - .065 * (core.gg(card, state, 'receive') - 120), 2.5, 8)
                if spin in ('back', 'side_back') and family not in ('chop', 'push', 'flip') else 0.)
    delta = (core.clamp((incoming_contact['pace'] - 120) * .06, -2., 3.) if family == 'chop' else 0.)
    if clutch:
        delta += core.clamp(state['clutch_bonus'] * .12, -1., 1.)
    loss, winner, continuation_quality, execution_error = miss, 0., 0., 0.
    for grade, probability, arrival in grades:
        error = core.clamp({'good': .073, 'limited': .176, 'bad': .35}[grade] + base_adjustment, .026, .58)
        mean_q, strong, q_strong, q2_strong = _quality_moments(skill + arrival - conflict, delta, active and grade != 'bad')
        # For 140 <= q <= 172 the published winner formula is linear and lies
        # inside its clamps, so these normal-tail moments avoid threshold bins.
        winner_probability = max(0., (.065 - .0023 * 132) * strong + .0023 * q_strong)
        q_times_winner = (.065 - .0023 * 132) * q_strong + .0023 * q2_strong
        survives_error = probability * (1 - error)
        loss += probability * error
        execution_error += probability * error
        winner += survives_error * winner_probability
        continuation_quality += survives_error * (mean_q + 8 * strong - q_times_winner - 8 * winner_probability)
    continuation = max(0., 1 - loss - winner)
    return dict(loss=loss, winner=winner, continuation=continuation,
                mean_ball_quality=continuation_quality / max(1e-9, continuation),
                arrival_miss=miss, execution_error=execution_error,
                movement_m=movement, unreached_movement_m=distance,
                movement_demand=7 * distance / geo.HALF_WIDTH_M,
                spin_demand=spin_demand, pace_demand=.22 * (incoming_contact['pace'] - 120))


def _absorbed(a, b):
    """Two-phase probabilities, capped at the full engine's 41 contacts."""
    ca, cb = a['continuation'], b['continuation']
    cycle = ca * cb
    cycle20 = cycle ** 20
    series20 = (1 - cycle20) / (1 - cycle) if cycle < 1 - 1e-12 else 20.
    series21 = series20 + cycle20
    start_a = (a['winner'] + ca * b['loss']) * series20 + cycle20 * (a['winner'] + .5 * ca)
    start_b = (b['loss'] + cb * a['winner']) * series20 + cycle20 * (b['loss'] + .5 * cb)
    counts = (.5 * (series21 + cb * series20), .5 * (series21 + ca * series20))
    return .5 * (start_a + start_b), counts


def point_probability(cards, states, server, attacker, attack_action, attack_wing, defend_action, defend_wing, *, target='crosscourt', attack_incoming=None, contact_pair=None, clutch=False):
    """Finite absorbing rally estimate; defense quality is never attack force."""
    defender = 1 - attacker
    ac, dc, ast, dst = cards[attacker], cards[defender], states[attacker], states[defender]
    attack = contact_skill(ac, ast, attack_action, attack_wing)
    defense = contact_skill(dc, dst, defend_action, defend_wing)
    serve = .62 * core.gg(cards[server], states[server], 'serve') + .38 * cards[server]['children']['serve']['disguise']
    receive = .60 * core.gg(cards[1 - server], states[1 - server], 'receive') + .40 * cards[1 - server]['children']['receive']['spin_read']
    serve_edge = core.clamp((serve - receive) / 260 + .018, -.10, .12) * (1 if attacker == server else -1)
    af = rubbers.action_spec(attack_action)['family']
    df = rubbers.action_spec(defend_action)['family']
    incoming = attack_incoming or ('back' if df in ('chop', 'push') else 'top')
    # These are representative contact-pair properties, not a claim that a
    # particular numbered stroke happened. Equipment transforms pace/spin once;
    # it does not multiply the technical quality score.
    if contact_pair is None:
        attack_contact = contact_properties(ac, ast, attack_action, attack_wing, incoming)
        defend_contact = contact_properties(dc, dst, defend_action, defend_wing,
                                           attack_contact['spin'], attack_contact['spin_strength'], attack)
    else:
        # A passive initiator may hand the offensive role to the response.
        # Reorientation never performs equipment conversion a second time.
        attack_contact, defend_contact = contact_pair
    qa, qb, counts = attack, defense, (3., 3.)
    for _ in range(3):
        phase_a = _phase(ac, ast, attack, af, attack_wing, attack_contact, defend_contact, qb, counts[0], clutch)
        phase_b = _phase(dc, dst, defense, df, defend_wing, defend_contact, attack_contact, qa, counts[1], clutch)
        p_attack, counts = _absorbed(phase_a, phase_b)
        qa, qb = phase_a['mean_ball_quality'], phase_b['mean_ball_quality']
    p_attack = core.clamp(p_attack + serve_edge, .01, .99)
    return dict(p_attacker=p_attack, attack_skill=attack, defense_skill=defense,
                attack_error=phase_a['execution_error'], defend_error=phase_b['execution_error'],
                movement_demand=phase_b['movement_demand'],
                attack_family=af, defense_family=df,
                spin_demand=phase_b['spin_demand'], pace_demand=phase_b['pace_demand'],
                spin_return_cost=0., phases=(phase_a, phase_b), expected_contacts=counts,
                probability_method='FINITE_TWO_PHASE_ABSORPTION_41; geometry and initial service are approximations')


def _terminal_events(phases):
    """22 aggregate terminal classes, without constructing any shot sequence."""
    cycle = phases[0]['continuation'] * phases[1]['continuation']
    cycle20 = cycle ** 20
    series20 = (1 - cycle20) / (1 - cycle) if cycle < 1 - 1e-12 else 20.
    events = []
    for start in (0, 1):
        for offset, actor, previous in ((1, start, 1.), (2, 1 - start, phases[start]['continuation'])):
            phase = phases[actor]
            for winner, miss, error, value in ((1 - actor, True, False, phase['arrival_miss']),
                    (1 - actor, False, True, phase['loss'] - phase['arrival_miss']),
                    (actor, False, False, phase['winner'])):
                weight = .5 * previous * value * series20
                if weight > 0:
                    events.append(dict(winner=winner, miss=miss, error=error, terminal=actor, start=start,
                                       offset=offset, final=False, weight=weight))
        phase = phases[start]
        for winner, miss, error, value in ((1 - start, True, False, phase['arrival_miss']),
                (1 - start, False, True, phase['loss'] - phase['arrival_miss']),
                (start, False, False, phase['winner']), (0, False, False, phase['continuation'] * .5),
                (1, False, False, phase['continuation'] * .5)):
            weight = .5 * cycle20 * value
            if weight > 0:
                events.append(dict(winner=winner, miss=miss, error=error, terminal=start, start=start,
                                   offset=41, final=True, weight=weight))
    return events, cycle


def _draw_aggregate_point(rng, matchup):
    """Joint winner/length/contact draw from finite absorbing event classes."""
    winner = 0 if rng.random() < matchup['p_attacker'] else 1
    events, cycle = _terminal_events(matchup['phases'])
    choices = [event for event in events if event['winner'] == winner]
    selected = rng.choices(choices, weights=[event['weight'] for event in choices])[0]
    if selected['final']:
        attempts = 41
    else:
        u = rng.random()
        if cycle < 1e-12:
            cycles = 0
        elif cycle > 1 - 1e-12:
            cycles = min(19, int(u * 20))
        else:
            cycles = min(19, int(math.log(1 - u * (1 - cycle ** 20)) / math.log(cycle)))
        attempts = cycles * 2 + selected['offset']
    attempted = [attempts // 2 + int(attempts % 2 and selected['start'] == actor) for actor in (0, 1)]
    contacted = attempted.copy()
    if selected['miss']:
        contacted[selected['terminal']] -= 1
    return dict(winner=winner, attempted=attempted, contacted=contacted,
                miss=selected['miss'], miss_actor=selected['terminal'] if selected['miss'] else None,
                error_actor=selected['terminal'] if selected['error'] else None,
                contacts=1 + sum(contacted))


def _expose(ledger, recipe, count, rng, pressure):
    # Aggregate contact allocations are sampled here; there is no invented
    # chronology or technique choice on a fictitious numbered shot.
    paths, weights = tuple(recipe), tuple(recipe.values())
    for path in rng.choices(paths, weights=weights, k=count):
        ledger['usage'][path] += 1
        if pressure:
            ledger['pressure'][path] += 1


def play_match(cards, seed, *, fatigue=(25, 25), max_games=7, keep_points=False):
    _validate(cards, seed, fatigue, max_games, keep_points)
    # Same initial stream/mechanism as the detailed runner, then an explicitly
    # different point model. Same seed does not promise identical match results.
    rng = core.rng_of('SPIN-ERA-1.1.2', 'MATCH', seed)
    states = [core.warmup(cards[i], rng, fatigue[i]) for i in (0, 1)]
    needed = max_games // 2 + 1
    won, games, checks = [0, 0], [], []
    exposures = [dict(usage=Counter(), pressure=Counter()), dict(usage=Counter(), pressure=Counter())]
    workloads = [dict(contacts=0, movement_m=0., active_attacks=0, effort=0., estimated=True),
                 dict(contacts=0, movement_m=0., active_attacks=0, effort=0., estimated=True)]
    actions, families, targets, outcomes, rally_hist = Counter(), Counter(), Counter(), Counter(), Counter()
    by_player = [Counter(), Counter()]
    plan_usage = [Counter(), Counter()]
    probability_sum = [0., 0.]
    total_points = total_strokes = 0
    for gi in range(max_games):
        score = [0, 0]
        while max(score) < 11 or abs(score[0] - score[1]) < 2:
            server = core.serve_side(sum(score), gi)
            receiver = 1 - server
            serve = core.gg(cards[server], states[server], 'serve')
            receive = core.gg(cards[receiver], states[receiver], 'receive')
            initiative = core.clamp(.52 + .004 * (serve - receive), .25, .77)
            initiator = server if rng.random() < initiative else receiver
            opponent = 1 - initiator
            first_wing = _wing(cards[initiator], states[initiator], rng,
                               defensive=plans.specialist_kind(cards[initiator]) == 'chopper')
            incoming = 'back' if cards[opponent].get('style') == 'modern_chopper' else 'top'
            first_action = _choose_contact(cards[initiator], states[initiator], first_wing, incoming, 120, rng)
            first_wing = states[initiator]['light_contact_wing']
            response_wing, target, resolved = _defending_lane(cards[initiator], cards[opponent], first_wing, states[initiator], rng)
            first_quality = contact_skill(cards[initiator], states[initiator], first_action, first_wing)
            first_contact = contact_properties(cards[initiator], states[initiator], first_action, first_wing, incoming)
            response_action = _choose_contact(cards[opponent], states[opponent], response_wing,
                first_contact['spin'], first_quality, rng, defending=True,
                incoming_pace=first_contact['pace'], incoming_strength=first_contact['spin_strength'], incoming_arc=first_contact['arc'])
            response_wing = states[opponent]['light_contact_wing']
            response_contact = contact_properties(cards[opponent], states[opponent], response_action,
                response_wing, first_contact['spin'], first_contact['spin_strength'], first_quality)
            first_passive = rubbers.action_spec(first_action)['family'] not in OFFENSIVE
            response_active = rubbers.action_spec(response_action)['family'] in OFFENSIVE
            if first_passive and response_active:
                attacker, defender = opponent, initiator
                attack_action, wing = response_action, response_wing
                # The active response chooses its own target. A passive first
                # contact cannot reserve its controller's favourite defending
                # wing for the rest of an aggregate rally.
                defend_wing, target, resolved = _defending_lane(cards[attacker], cards[defender], wing, states[attacker], rng)
                response_quality = contact_skill(cards[attacker], states[attacker], attack_action, wing)
                defend_action = _choose_contact(cards[defender], states[defender], defend_wing,
                    response_contact['spin'], response_quality, rng, defending=True,
                    incoming_pace=response_contact['pace'], incoming_strength=response_contact['spin_strength'], incoming_arc=response_contact['arc'])
                defend_wing = states[defender]['light_contact_wing']
                defender_contact = contact_properties(cards[defender], states[defender], defend_action,
                    defend_wing, response_contact['spin'], response_contact['spin_strength'], response_quality)
                pair = (response_contact, defender_contact)
                outcomes['initiative_returned_by_passive_contact'] += 1
            else:
                attacker, defender = initiator, opponent
                attack_action, wing, defend_action, defend_wing = first_action, first_wing, response_action, response_wing
                pair = (first_contact, response_contact)
            matchup = point_probability(cards, states, server, attacker, attack_action, wing, defend_action, defend_wing,
                target=target, contact_pair=pair,
                clutch=max(score) >= 10 or min(score) >= 8 and abs(score[0] - score[1]) <= 1)
            p0 = matchup['p_attacker'] if attacker == 0 else 1 - matchup['p_attacker']
            aggregate = _draw_aggregate_point(rng, matchup)
            winner = attacker if aggregate['winner'] == 0 else defender
            contacts = aggregate['contacts']
            if aggregate['miss']:
                outcomes['sampled_unreached_attempts'] += 1
            score[winner] += 1
            total_points += 1
            total_strokes += contacts
            rally_hist[contacts] += 1
            probability_sum[0] += p0
            probability_sum[1] += 1 - p0
            targets[target] += 1
            outcomes['attacker_point' if winner == attacker else 'defender_point'] += 1
            if not resolved:
                outcomes['anatomy_unresolved_points'] += 1
            actions['serve'] += 1
            families['serve'] += 1
            by_player[server]['serve'] += 1
            workloads[server]['contacts'] += 1
            _expose(exposures[server], SERVE_RECIPE, 1, rng, serve < 120)
            for relative, (actor, action, side, quality, phase) in enumerate((
                    (attacker, attack_action, wing, matchup['attack_skill'], matchup['phases'][0]),
                    (defender, defend_action, defend_wing, matchup['defense_skill'], matchup['phases'][1]))):
                number = aggregate['contacted'][relative]
                missed = aggregate['attempted'][relative] - number
                movement = number * phase['movement_m'] + missed * phase['unreached_movement_m']
                if aggregate['error_actor'] == relative:
                    movement -= phase['movement_m'] - phase['unreached_movement_m']
                workloads[actor]['movement_m'] += movement
                if not number:
                    continue
                spec = rubbers.action_spec(action)
                actions[action] += number
                families[spec['family']] += number
                by_player[actor][action] += number
                plan_usage[actor][states[actor]['light_plan']] += number
                states[actor]['light_last_family'] = spec['family']
                pressured = (actor == defender and matchup['movement_demand'] > 3.) or quality < 120
                _expose(exposures[actor], contact_recipe(action, side), number, rng, pressured)
                workloads[actor]['contacts'] += number
                if spec['family'] in ('attack', 'open', 'counter', 'flip', 'slow_loop'):
                    workloads[actor]['active_attacks'] += number
                visible_quality = core.clamp(quality + rng.gauss(0, 5), 50, 180)
                observed_tactics.observe_shot(states[1 - actor], stroke_side=side, quality=visible_quality,
                    action_family=spec['family'], length='long', error=False)
                states[actor]['points_seen'] += 1
            observed_tactics.attempt_in_game_adaptation(cards, states, rng, score, gi)
            if total_points > 1500:
                raise RuntimeError('implausible match length')
        game_winner = 0 if score[0] > score[1] else 1
        won[game_winner] += 1
        games.append(dict(score=score, winner=game_winner, points_count=sum(score)))
        for i, state in enumerate(states):
            state['match_stamina'] += sum(score) / max(35., state['p_eff']['stamina']) * 2
        if won[game_winner] == needed:
            break
        checks.extend(observed_tactics.between_games(cards, states, rng, gi + 1))
    for item in workloads:
        item['effort'] = item['contacts'] * .08 + item['movement_m'] * .18 + item['active_attacks'] * .03
        for key in ('movement_m', 'effort'):
            item[key] = round(item[key], 5)
    final_exposures = [{key: dict(value) for key, value in item.items()} for item in exposures]
    assert all(set(e['usage']) <= PATHS for e in final_exposures)
    return dict(seed=seed, engine=TAG, mode='summary', narrative_scope='AGGREGATE_ONLY',
        winner=0 if won[0] == needed else 1, games_won=won, games=games,
        points=total_points, total_strokes=total_strokes, mean_strokes=round(total_strokes / total_points, 5),
        rally_length_distribution={str(k): v for k, v in sorted(rally_hist.items())},
        rally_method='FINITE_ABSORBING_TERMINAL_CONTACT_SAMPLE_NOT_A_SHOT_TRACE',
        actions=dict(actions), action_family_distribution=dict(families), target_lane_usage=dict(targets),
        outcome_summary=dict(outcomes), per_player_actions=[dict(v) for v in by_player],
        tactical_plan_usage=[dict(v) for v in plan_usage],
        exposure_by_player=final_exposures,
        exposure_provenance='AGGREGATE_CONTACT_SAMPLING',
        exposure_method='SAMPLED_AGGREGATE_CONTACT_ALLOCATIONS_NOT_SHOT_LOG',
        exposure_scope='ALL_SAMPLED_CONTACTS_INCLUDING_SERVE; one technical path allocation per contact',
        pressure_method='MATCHUP_PRESSURE_PROXY_NOT_A_SPECIFIC_SHOT_ERROR',
        workload=dict(source='POINT_AGGREGATE_APPROXIMATION', per_player=workloads),
        average_point_probability=[round(x / total_points, 6) for x in probability_sum],
        between_game_checks=checks,
        match_form=[dict(form_initial=s['form_initial'], p_roll=s['p_roll'],
                         psychological_state=s['mental'], initial_final_tactics=s['policy'],
                         counter_level=s['policy_stage']) for s in states],
        status='SIMULATED_NONHISTORICAL_APPROXIMATE_BACKGROUND_MATCH',
        calibration_status='POINT_MODEL_CANDIDATE_NOT_EQUIVALENT_TO_DETAILED_ENGINE',
        aggregate_model=dict(probability='FINITE_TWO_PHASE_ABSORPTION_41',
            action_menu='SHARED_DETAILED_PURE_DISTRIBUTION; reached-grade representative sample',
            movement='EXPECTED_UNIFORM_TARGET_GRID; first/steady arrival mixture',
            cross_wing='ACTUAL_CHOSEN_WING_AND_MENU_FIT; no full post-reach cross-body grade penalty',
            point_length='JOINT_TERMINAL_EVENT_SAMPLE; missed attempts grant no contact exposure',
            initial_service='SERVE_RECEIVE_EDGE_PROXY; no explicit short/half-long service prefix',
            quality_feedback_iterations=3, shot_chronology=False),
        metadata_limits=dict(handedness=[normalize_hand(c) for c in cards],
            rubbers=[{w: rubbers.rubber_for(c, w) for w in ('fh', 'bh')} for c in cards],
            no_shot_chronology=True, unknown_metadata_inferred=False))
