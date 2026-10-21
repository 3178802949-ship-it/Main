"""V1.1.7 separate specialist strategies on the preserved match runner.

The existing warm-up, G9/P6/CA, scoring and psychological checks remain
dependencies. A single contact recipe replaces stacked technique aliases;
physical demands and separate specialist plans use observed information.
Only isolated Game.worker processes use the temporary runner hooks.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import math
from pathlib import Path

from common import canonical_json, SCHEMA
from Game import specialist_engine as previous
from Game import tactics_v117 as plans
from Game import geometry as geo
from Game import observed_tactics as observed
import specialist_rubber_v116 as rubber
import tactical_match_v116 as tactical
import game_v115 as legacy

core = legacy.core
TAG = 'V1.1.7-CANDIDATE-1'
CHOP_FAMILIES = ('chop',)


def _sign(end):
    return -1 if end == 0 else 1


def _stance(end, depth=1.12):
    return dict(x=0., y=_sign(end) * depth, recovery=1., momentum_x=0., momentum_y=0., movement_load=0.)


def _absolute_target(lane, length, card, end, rng):
    result = geo.lane_to_point(lane, geo.normalize_hand(card), end, length)
    if result is None:
        # Anatomical evidence is absent. Draw a physical lane independently;
        # preserve the legacy label only as an explicitly unresolved fallback.
        result = dict(x=rng.choice((-.72, 0., .72)), y=_sign(end) * geo.LENGTH_DEPTH[length])
    return result


def _interception(card, end, bounce, length, *, spin='top', quality=120., plan=None):
    if length == 'short':
        depth = .48
    elif length == 'half':
        depth = 1.02
    else:
        if plan is None:
            kind = plans.specialist_kind(card, dict(landed='middle'))
            depth = (1.10 if quality < 118 else 1.68) if kind == 'chopper' and spin in ('top', 'side_top') else 1.18
        else:
            depth = plans.PLANS[plan]['depth']
    spread = 1.12 if depth <= 1.10 else 1.18
    return dict(x=core.clamp(bounce['x'] * spread, -1.40, 1.40), y=_sign(end) * depth)



def _grade(score):
    return 'miss' if score < -21 else 'bad' if score < -10 else 'limited' if score < 2 else 'good'


def reach(card, state, ball, rng, step, end):
    """Physical reach with deliberate preparation and live top-spin/arc demand."""
    stance = state['hgr_position']
    plan = state.get('v117_plan', {}).get('plan')
    contact = _interception(card, end, ball['absolute_target'], ball['length'],
                            spin=ball['spin'], quality=ball['quality'], plan=plan)
    dx = (contact['x'] - stance['x']) * geo.HALF_WIDTH_M
    dy = (contact['y'] - stance['y']) * geo.HALF_LENGTH_M
    distance = math.hypot(dx, dy)
    reverse = ((contact['x'] - stance['x']) * stance['momentum_x'] < -.015
               or (contact['y'] - stance['y']) * stance['momentum_y'] < -.015)
    p = state['p_eff']
    skill = (.50 * core.gg(card, state, 'feet') + .19 * p['speed'] + .15 * p['agility']
             + .10 * p['flexibility'] + .06 * core.gg(card, state, 'read'))
    physical_demand = 7 * distance / geo.HALF_WIDTH_M
    recovery_cost = (1 - stance['recovery']) * 3 + 2.5 * reverse
    load_before = state['hgr_rally_load']
    load_cost = min(5., load_before * .16 + state['hgr_match_load'] * .05)
    spin_demand = (core.clamp((ball.get('spin_strength', 110) - 100) * .035, -2., 3.2)
                   if ball['spin'] in ('top', 'side_top') else 0.)
    # High arcs give travel time; flat/low contacts compress interception time.
    arc_demand = {'high': -2.4, 'defensive_arc': -1.4, 'flat': 1.1,
                  'low': .7, 'low_defensive': .2, 'slow_low': -.8}.get(ball.get('arc', 'normal'), 0.)
    demand = (121 + .29 * (ball['quality'] - 120) + .22 * (ball['pace'] - 120)
              + physical_demand + recovery_cost + min(8, step * .26)
              + state['match_stamina'] * .16 + load_cost + spin_demand + arc_demand)
    score = skill - demand + rng.gauss(0, 11)
    if ball.get('length') == 'short' and step <= 2:
        score += core.clamp((core.gg(card, state, 'table') - 110) * .13, -3, 4)
    pos = _grade(score)
    side = geo.point_to_lane(contact, geo.normalize_hand(card), end, stance)
    mapped = side if side in ('fh', 'bh', 'middle') else ball['landed']
    increment = (distance * .30 + .12 + max(0, ball['pace'] - 110) * .001) * 120 / max(40, p['stamina'])
    state['hgr_rally_load'] += increment
    state['hgr_match_load'] += increment * .08
    movement = dict(position_before=copy.deepcopy(stance), contact=contact, distance_m=round(distance, 5),
        dx_m=round(dx, 5), dy_m=round(dy, 5), direction='left' if dx < -.015 else 'right' if dx > .015 else 'none',
        depth_direction='forward' if dy * _sign(end) < -.015 else 'backward' if dy * _sign(end) > .015 else 'none',
        reversing=bool(reverse), recovery_cost=round(recovery_cost, 4), physical_demand=round(physical_demand, 4),
        spin_demand=round(spin_demand, 4), arc_demand=round(arc_demand, 4), input_arc=ball.get('arc', 'normal'),
        load_before=round(load_before, 5), load_after=round(state['hgr_rally_load'], 5),
        match_load=round(state['hgr_match_load'], 5), mapped_contact_side=side,
        mapping_resolved=side != 'unknown', step_around=False, preparation=plan)
    return pos, round(score, 4), mapped, movement



def _wing(action, ball, card):
    spec = rubber.action_spec(action)
    if spec['wing']:
        return spec['wing']
    if ball['landed'] in ('fh', 'bh'):
        return ball['landed']
    return max(('fh', 'bh'), key=lambda w: card['children'][w]['defense'])


def _tactic(card, state, ball, pos, opponent_position, rng):
    if 'v117_plan' not in state:
        state['v117_plan'] = plans.choose_plan(card, state, ball, opponent_position, rng)
    return state['v117_plan']['plan']



def action_distribution(card, state, ball, pos, tactic):
    """Separate specialist menus on the same legal, own-skill candidate pool."""
    options = previous.action_distribution(card, state, ball, pos, 'v117_neutral')
    chopper = card.get('style') == 'modern_chopper'
    for item in options:
        spec = rubber.action_spec(item['action'])
        weight = item['probability']
        if spec['family'] == 'chop':
            # Remove the old role-wide multiplier; the selected plan now owns
            # defense/counterattack preference and actual preparation depth.
            weight /= (4.4 if ball['spin'] in ('top', 'side_top') else 1.2) if chopper else (.65 if pos == 'bad' else .12)
            if plans.PLANS[tactic]['kind'] != 'chopper':
                weight *= .10 if pos == 'bad' else .06
        weight *= plans.action_multiplier(tactic, spec, item['action'], ball, state.get('hgr_last_family'))
        item['probability'] = weight
    total = sum(item['probability'] for item in options)
    for item in options:
        item['probability'] /= total
    return options



def target_distribution(card, state, ball, opponent_card, opponent_state, action, tactic, end,
                        outgoing_spin='top', outgoing_quality=120.):
    """Only visible stance/hand and the hitter's own observed evidence are used."""
    other_end = 1 - end
    opponent_pos = opponent_state['hgr_position']
    hand = geo.normalize_hand(opponent_card)
    incoming = ball['absolute_target']
    contact = state['hgr_contact']
    candidates = []
    weak = observed.inferred_weakness(state)
    placements = card['children'][_wing(action, ball, card)]['placement']
    read = core.gg(card, state, 'read')
    sensitivity = core.clamp(.55 + (read - 90) / 90, .45, 1.3)
    for x in (-.94, -.65, 0., .65, .94, core.clamp(opponent_pos['x'], -.9, .9)):
        for length in ('long', 'short') if action in ('short_stop_drop', 'push_short', 'push_side', 'push_middle') else ('long',):
            target = dict(x=x, y=_sign(other_end) * geo.LENGTH_DEPTH[length])
            rc = _interception(opponent_card, other_end, target, length, spin=outgoing_spin, quality=outgoing_quality)
            info = geo.map_line(hitter_hand=geo.normalize_hand(card), receiver_hand=hand, hitter_end=end,
                hitter_stance=state['hgr_position'], receiver_stance=opponent_pos, incoming=incoming,
                target=target, technique=action, receiver_contact=rc, incoming_contact=contact)
            tactical_fit = 0.
            if info['receiver_contact_side'] == weak:
                tactical_fit += .9
                if state.get('execute_weakness') and state.get('scouted_weakness') == weak:
                    tactical_fit += .8
            if info['reversing']:
                tactical_fit += .7
            if tactic in ('wide_movement', 'reverse_direction'):
                tactical_fit += info['distance_m'] * .65 + .6 * info['wide_angle']
            if tactic == 'observed_weak_side' and info['receiver_contact_side'] == weak:
                tactical_fit += 1.2
            if tactic == 'short_long':
                tactical_fit += .9 * (length == 'short' and abs(opponent_pos['y']) > 1.4)
            if state.get('hgr_last_line') == 'crosscourt' and info['straight']:
                tactical_fit += .4
            if info['body'] and abs(opponent_pos['x']) > .25:
                tactical_fit += .6
            # Extreme angles require placement. Hand is solely geometric.
            tactical_fit -= max(0., abs(x) - .65) * max(0, 137 - placements) / 18
            candidates.append(dict(target=target, length=length, geometry=info,
                                   weight=math.exp(core.clamp(tactical_fit * sensitivity, -3, 3))))
    total = sum(c['weight'] for c in candidates)
    for c in candidates:
        c['probability'] = c.pop('weight') / total
    return candidates


def _move_to_contact(card, state, movement, wing, end):
    before = movement['position_before']
    contact = movement['contact']
    hand = geo.normalize_hand(card)
    local_fh = (1 if hand == 'right' else -1) * (1 if end == 0 else -1) if hand != 'unknown' else 0
    body_x = contact['x'] - local_fh * (.25 if wing == 'fh' else -.25)
    state['hgr_position'] = dict(x=core.clamp(body_x, -1.6, 1.6), y=contact['y'], recovery=.5,
        momentum_x=body_x - before['x'], momentum_y=contact['y'] - before['y'], movement_load=state['hgr_rally_load'])
    state['hgr_contact'] = contact.copy()


def _recover(card, state, family, end, pace):
    s = state['hgr_position']
    plan = state.get('v117_plan', {}).get('plan')
    desired_depth = plans.PLANS[plan]['depth'] if plan in plans.PLANS else 1.18
    if family in ('attack', 'counter', 'open', 'flip'):
        desired_depth = min(desired_depth, 1.20)
    fraction = core.clamp((.32 + core.gg(card, state, 'feet') * .002) * 115 / max(85, pace), .25, .72)
    dx = -s['x'] * fraction
    dy = (_sign(end) * desired_depth - s['y']) * fraction
    recovery_distance = math.hypot(dx * geo.HALF_WIDTH_M, dy * geo.HALF_LENGTH_M)
    s.update(x=s['x'] + dx, y=s['y'] + dy, recovery=core.clamp(.58 + fraction * .5, 0, 1),
             momentum_x=dx, momentum_y=dy)
    state['hgr_rally_load'] += recovery_distance * .1
    return recovery_distance



def _add_group(target, group, coefficient):
    for key, percent in SCHEMA['subskill_weights_pct'][group].items():
        path = f'{group}.{key}'
        target[path] = target.get(path, 0.) + coefficient * percent / 100


def technique_components(action, wing):
    """Return normalized actual base-skill weights for one contact, not extra XP."""
    if wing not in ('fh', 'bh'):
        raise ValueError('explicit stroke side required')
    spec = rubber.action_spec(action)
    family = spec['family']
    parts = {}
    def direct(key, weight):
        path = f'{wing}.{key}'
        parts[path] = parts.get(path, 0.) + weight
    if family == 'chop':
        for key, weight in (('defense', .42), ('spin', .27), ('placement', .23), ('continuity', .08)):
            direct(key, weight)
    elif action.endswith(('sp_under_attack', 'sp_punch', 'sp_flat_hit', 'lp_flat_attack')):
        for key, weight in (('power', .55), ('continuity', .20), ('placement', .15), ('spin', .10)):
            direct(key, weight)
    elif action.endswith('sp_quick_drive'):
        for key, weight in (('continuity', .55), ('power', .25), ('placement', .20)):
            direct(key, weight)
    elif family == 'block':
        direct('defense', .56)
        _add_group(parts, wing, .44)
    elif family == 'push':
        _add_group(parts, 'table', .55)
        path = spec['technique_path']
        if path.startswith('serve.'):
            path = 'table.push'
        parts[path] = parts.get(path, 0.) + .45
    elif family == 'lob':
        _add_group(parts, 'spirit', .68)
        _add_group(parts, 'feet', .32)
    elif family == 'flip':
        _add_group(parts, 'table', .30)
        _add_group(parts, wing, .25)
        parts[spec['technique_path']] = parts.get(spec['technique_path'], 0.) + .45
    elif family in ('open', 'slow_loop'):
        direct('spin', .45)
        _add_group(parts, wing, .35)
        direct('placement', .20)
    elif family == 'counter':
        direct('continuity', .35)
        _add_group(parts, wing, .48)
        direct('power', .17)
    else:
        _add_group(parts, wing, .52)
        direct('power', .29)
        direct('continuity', .19)
    total = sum(parts.values())
    return {path: round(weight / total, 8) for path, weight in parts.items() if weight > 0}


def _quality(card, state, ball, pos, action, rng, step, clutch, wing):
    """One canonical contact model: no alias-to-BH leakage or quality stacking."""
    parts = technique_components(action, wing)
    tech = sum(card['children'][path.split('.')[0]][path.split('.')[1]] * weight
               for path, weight in parts.items())
    spec = rubber.action_spec(action)
    # Daily form applies to its actual stroke side once. For table/cognitive
    # contributions their own G aggregate supplies only their corresponding share.
    if spec['family'] in ('chop', 'block', 'open', 'slow_loop', 'counter', 'attack'):
        tech += .52 * (core.gg(card, state, wing) - card['G9'][wing])
    else:
        tech += .30 * (core.gg(card, state, 'table') - card['G9']['table'])
        tech += .25 * (core.gg(card, state, wing) - card['G9'][wing])
    if spec['family'] == 'chop':
        pace, spin = 113 + .24 * (tech - 120), 'back'
    elif spec['family'] == 'push':
        pace, spin = 100 + .19 * (tech - 115), 'back'
    elif spec['family'] == 'block':
        pace, spin = 105 + .24 * (tech - 118), 'top'
    elif spec['family'] == 'lob':
        pace, spin = 90 + .08 * (tech - 120), 'top'
    elif spec['family'] == 'flip':
        pace, spin = 121 + .30 * (tech - 120), 'top'
    else:
        pace, spin = 131 + .39 * (tech - 125) + .13 * (state['p_eff']['burst'] - 120), 'top'
        if spec['family'] == 'slow_loop':
            pace -= 9
    arrival = {'good': 0, 'limited': -13, 'bad': -25}.get(pos, -40)
    conflict = (core.clamp(6 - .065 * (core.gg(card, state, 'receive') - 120), 2.5, 8)
                if ball['spin'] in ('back', 'side_back') and spin == 'top' and spec['family'] != 'flip' else 0)
    quality = core.clamp(tech + arrival - conflict + rng.gauss(0, 7), 60, 168)
    if spec['family'] == 'chop':
        quality += core.clamp((ball['pace'] - 120) * .06, -2, 3)
    if clutch:
        quality += core.clamp(state['clutch_bonus'] * .12, -1, 1)
    state['v117_contact_skill'] = tech
    state['v117_technique_components'] = parts
    return round(quality, 2), round(pace, 2), spin


def technical_error_adjustment(contact_skill):
    """A technique changes execution reliability as well as output quality."""
    return core.clamp((120 - contact_skill) * .0014, -.035, .070)



def point(cards, states, rng, server, score, keep_shots=False):
    """Same serve, error/stability and winner framework with physical contacts."""
    for i, state in enumerate(states):
        state['hgr_position'] = _stance(i)
        state['hgr_contact'] = dict(x=0., y=_sign(i) * .90)
        state['hgr_rally_load'] = 0.
        state.setdefault('hgr_match_load', 0.)
    recv = 1 - server
    scard, serv = cards[server], states[server]
    clutch = max(score) >= 10 or (min(score) >= 8 and abs(score[0] - score[1]) <= 1)
    zone, spin, serve_style = core.serve_policy(scard, serv, rng)
    aim, length = zone.rsplit('_', 1)
    servq = core.clamp(118 + .30 * (core.gg(scard, serv, 'serve') - 120)
        + .08 * (scard['children']['serve']['spin'] - 120) + .09 * (scard['children']['serve']['placement'] - 120)
        + rng.gauss(0, 8), 82, 164)
    absolute = _absolute_target(aim, length, cards[recv], recv, rng)
    ball = dict(origin='service', third_phase='receive', spin=spin, pace=105 + (7 if length == 'long' else 0),
        quality=servq, landed=aim, target=aim, length=length, style=serve_style,
        backspin_strength=125 if spin in ('back', 'side_back') else 0, spin_strength=125 if spin != 'dead' else 0, arc='normal',
        absolute_target=absolute, variation=0.)
    serv['serve_forms'][zone + '|' + spin + '|' + serve_style] += 1
    serv['last_serve'] = dict(zone=zone, spin=spin, style=serve_style)
    shots = [dict(player=server, action='serve', zone=zone, style=serve_style, spin=spin, length=length,
                  landed=aim, quality=round(servq, 2), absolute_target=absolute, spin_strength=ball['spin_strength'],
                  return_state='serve', handedness=geo.normalize_hand(scard))] if keep_shots else []
    n = recv
    for step in range(1, 42):
        card, state, op = cards[n], states[n], states[1 - n]
        state['v117_plan'] = plans.choose_plan(card, state, ball, op['hgr_position'], rng)
        pos, score_reach, mapped, movement = reach(card, state, ball, rng, step, n)
        local_ball = dict(ball, landed=mapped)
        if pos == 'miss':
            if keep_shots:
                shots.append(dict(player=n, action='unreached', reach='miss', input_target=mapped,
                    reach_score=score_reach, movement=movement, return_state='direct_point_lost',
                    input_spin=ball['spin'], input_spin_strength=ball['spin_strength']))
            state['observations']['unreached'] += 1
            return 1 - n, len(shots) - 1 if keep_shots else step, shots, 'unreached'
        tactic = _tactic(card, state, local_ball, pos, op['hgr_position'], rng)
        candidates = action_distribution(card, state, local_ball, pos, tactic)
        action = rng.choices([c['action'] for c in candidates], weights=[c['probability'] for c in candidates])[0]
        spec = rubber.action_spec(action)
        wing = _wing(action, local_ball, card)
        mismatch = mapped in ('fh', 'bh') and wing != mapped
        if mismatch:
            movement['step_around'] = wing == 'fh'
            movement['cross_body'] = True
            score_reach -= 4.5 if wing == 'fh' else 3.
            pos = _grade(max(-20.9, score_reach))
        _move_to_contact(card, state, movement, wing, n)
        quality, pace, outspin = _quality(card, state, local_ball, pos, action, rng, step, clutch, wing)
        if ball['origin'] == 'service' and length == 'short' and action in ('fh_open', 'bh_open', 'fh_attack', 'bh_attack', 'bh_open_twist'):
            quality -= 5
        if step == 2:
            quality += core.clamp((card['children']['serve']['third_link'] - 120) * .13, -3, 4)
        material = rubber.rubber_for(card, wing)
        contact = rubber.resolve_contact(material, action, local_ball, base_spin=outspin, base_pace=pace,
                                         base_strength=core.clamp(quality, 0, 170) if outspin != 'dead' else 0.)
        contact = plans.contact_properties(contact, tactic, spec['family'], state.get('hgr_last_family'))
        if spec['family'] == 'slow_loop':
            contact['arc'] = 'high'
        stable = core.gg(card, state, 'stable') + (state['clutch_bonus'] if clutch else 0)
        offensive = spec['family'] in ('attack', 'open', 'counter', 'flip', 'slow_loop')
        base = {'good': .073, 'limited': .176, 'bad': .35}[pos] + (.035 if offensive else 0)
        if spec['family'] == 'chop':
            base -= .03 if ball['spin'] in ('top', 'side_top') else .004
        if ball['origin'] == 'service':
            misread = core.clamp(.075 + .003 * (servq - 120) - .0015 * (core.gg(card, state, 'receive') - 115)
                + .0013 * (cards[1 - n]['children']['serve']['disguise'] - 120)
                - .0012 * (card['children']['receive']['spin_read'] - 120), .018, .21)
            if ball['spin'] in ('side_back', 'side_top'):
                misread += .03
            if spec['family'] == 'push' and ball['spin'] in ('top', 'side_top'):
                misread += .05
            base += misread
        if ball['spin'] in ('back', 'side_back') and offensive:
            base += .027 + core.clamp((ball['backspin_strength'] - 125) * .002, 0, .045)
        if ball.get('return_state') == 'high_ball' and offensive:
            base -= .023
        base += core.clamp((ball['quality'] - 130) * .0016, -.022, .071)
        base -= core.clamp((stable - 120) * .0010, -.018, .040)
        base += max(0, step - 8) * .002
        # Variation is recognized from actual ball properties and accumulated
        # exposure, not an equipment quality bonus or another skill roll.
        knowledge = state.setdefault('hgr_spin_exposure', Counter())
        spin_key = ball.get('rubber', 'serve') + ':' + ball['spin']
        exposure = knowledge[spin_key]
        recognition_risk = max(0., ball.get('variation', 0.)) * .045
        recognition_risk *= core.clamp((145 - core.gg(card, state, 'read')) / 70, .1, .9) / (1 + exposure / 12)
        contact_skill = state['v117_contact_skill']
        technique_fault_adjustment = technical_error_adjustment(contact_skill)
        spin_handling_risk = (core.clamp((ball.get('spin_strength', 110) - 100) * .00045, -.018, .032)
            * core.clamp((145 - card['children']['receive']['spin_read']) / 60, .15, 1.)
            if ball['spin'] in ('top', 'side_top') else 0.)
        early_timing_cost = .008 if tactic == 'pips_early_pressure' else 0.
        base += recognition_risk + min(.045, state['hgr_rally_load'] * .0015) + technique_fault_adjustment + spin_handling_risk + early_timing_cost
        base = core.clamp(base, .026, .58)
        knowledge[spin_key] += 1
        common = dict(player=n, action=action, action_family=spec['family'], stroke_side=wing,
            technique_path=spec['technique_path'], technique_label=spec['label'], rubber=material,
            handedness=geo.normalize_hand(card), reach=pos, reach_score=score_reach, input_target=mapped,
            input_spin=ball['spin'], input_spin_strength=ball['spin_strength'], input_quality=round(ball['quality'], 3),
            movement=movement, out_quality=round(quality, 3), quality=round(quality, 3), pace=contact['pace'],
            spin=contact['spin'], spin_strength=contact['spin_strength'], spin_contact=contact,
            fault_prob=round(base, 6), recognition_risk=round(recognition_risk, 6),
            contact_skill=round(contact_skill, 5), technique_components=state['v117_technique_components'],
            technique_fault_adjustment=round(technique_fault_adjustment, 6),
            spin_handling_risk=round(spin_handling_risk, 6), input_arc=ball.get('arc', 'normal'),
            arc=contact['arc'], specialist_plan=tactic, specialist_kind=state['v117_plan']['kind'],
            preparation_depth=state['v117_plan']['preparation_depth'],
            tactic=tactic, counterattack=card.get('style') == 'modern_chopper' and offensive,
            decision=dict(scenario=legacy.context(local_ball), observed_weakness=observed.inferred_weakness(state),
                          candidates=candidates, chosen=action))
        if rng.random() < base:
            common['return_state'] = 'direct_point_lost'
            if keep_shots:
                shots.append(common)
            observed.observe_shot(op, stroke_side=wing, quality=quality, action_family=spec['family'], length=ball['length'], error=True)
            state['observations']['errors'] += 1
            return 1 - n, len(shots) if keep_shots else step + 1, shots, 'error'
        stateout = ('high_ball' if spec['family'] == 'lob' or pos == 'bad' else
                    'strong_return' if quality >= 140 and offensive else
                    'high_ball' if quality < 109 and offensive else 'neutral_return')
        targets = target_distribution(card, state, local_ball, cards[1 - n], op, action, plans.PLANS[tactic]['target'], n,
                                      outgoing_spin=contact['spin'], outgoing_quality=quality)
        target = rng.choices(targets, weights=[x['probability'] for x in targets])[0]
        intended = target['target'].copy()
        accuracy = core.clamp(.70 + .0035 * (card['children'][wing]['placement'] - 115)
                              + .0018 * (core.gg(card, state, 'read') - 120), .48, .93)
        landed_abs = intended.copy()
        if rng.random() > accuracy:
            landed_abs['x'] = core.clamp(landed_abs['x'] + rng.choice((-.32, .32)), -.98, .98)
        target_length = target['length']
        lane = geo.point_to_lane(landed_abs, geo.normalize_hand(cards[1 - n]), 1 - n)
        if lane == 'unknown':
            lane = rng.choice(('fh', 'bh', 'middle'))
        incoming_contact = state['hgr_contact'].copy()
        info = geo.map_line(hitter_hand=geo.normalize_hand(card), receiver_hand=geo.normalize_hand(cards[1 - n]),
            hitter_end=n, hitter_stance=movement['position_before'], receiver_stance=op['hgr_position'],
            incoming=ball['absolute_target'], target=landed_abs, technique=action,
            receiver_contact=_interception(cards[1 - n], 1 - n, landed_abs, target_length,
                                            spin=contact['spin'], quality=quality),
            incoming_contact=incoming_contact)
        common.update(target=geo.point_to_lane(intended, geo.normalize_hand(cards[1 - n]), 1 - n),
                      landed=lane, length=target_length, absolute_target=landed_abs, intended_absolute_target=intended,
                      geometry=info, return_state=stateout, target_accuracy=round(accuracy, 5),
                      recovery_distance_m=round(_recover(card, state, spec['family'], n, contact['pace']), 5),
                      position_after=copy.deepcopy(state['hgr_position']))
        if keep_shots:
            shots.append(common)
        observed.observe_shot(op, stroke_side=wing, quality=quality, action_family=spec['family'], length=target_length)
        state['observations'][action] += 1
        state['observations'][stateout] += 1
        if ball['origin'] == 'service':
            state['return_forms'][action + '|' + lane] += 1
        state['hgr_last_family'] = spec['family']
        state['hgr_last_line'] = info['geometric_line']
        if step == 1:
            state['points_seen'] += 1
        ball = dict(origin='service_return' if step == 1 else 'third_ball' if step == 2 else 'rally',
                    spin=contact['spin'], spin_strength=contact['spin_strength'], pace=contact['pace'],
                    quality=quality + (8 if stateout == 'strong_return' else 0), landed=lane,
                    target=lane, length=target_length, absolute_target=landed_abs, return_state=stateout,
                    backspin_strength=contact['spin_strength'] if contact['spin'] in ('back', 'side_back') else 0,
                    rubber=material, variation=contact['variation'], arc=contact['arc'])
        p_win = core.clamp(.065 + .0023 * (quality - 132), .016, .18) if offensive and stateout == 'strong_return' else 0
        # No direct chop winner draw. The opponent must still solve the next
        # spin, reach and contact; counterattacks use the ordinary attack path.
        if ball['origin'] == 'third_ball' and serv['policy'] == 'third_ball_fh' and offensive:
            p_win += .025
        if rng.random() < p_win:
            state['observations']['winners'] += 1
            return n, len(shots) if keep_shots else step + 1, shots, 'winner'
        n = 1 - n
    return rng.choice((0, 1)), len(shots) if keep_shots else 42, shots, 'rally_limit'


def play_match(cards, seed, *, keep_points=True, fatigue=(25, 25), max_games=7, detail_level='full'):
    if max_games != 7 or detail_level not in ('full', 'summary'):
        raise ValueError('V1.1.7 detailed engine supports BO7 and full/summary logging')
    for card in cards:
        # Validate explicit tactical choices before any rolls or mutations.
        probe = dict(landed='middle', spin='top', length='long', quality=120.)
        st = core.warmup(card, core.rng_of('V117-TACTIC-VALIDATION'), 25)
        plans.plan_distribution(card, st, probe)
    saved = {k: getattr(core, k) for k in ('point', 'between_games', 'attempt_in_game_adaptation')}
    try:
        core.point = point
        core.between_games = observed.between_games
        core.attempt_in_game_adaptation = observed.attempt_in_game_adaptation
        result = tactical.play_match(cards, seed, keep_points=True, fatigue=fatigue, max_games=max_games)
    finally:
        for key, value in saved.items():
            setattr(core, key, value)
    result.update(engine=TAG, ruleset=TAG, tactical_patch='SEPARATE_SPECIALIST_PLANS_AND_CANONICAL_CONTACTS',
                  detail_level=detail_level)
    result['mechanics_source_sha256'] = {str(p.relative_to(Path(__file__).resolve().parents[1])):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            Path(__file__), Path(plans.__file__), Path(geo.__file__), Path(rubber.__file__), Path(observed.__file__))}
    shots = [s for g in result['games'] for p in g['points'] for s in p['shots']]
    result['technique_distribution'] = dict(Counter(s['action'] for s in shots if s.get('technique_path')))
    result['technique_path_distribution'] = dict(Counter(s['technique_path'] for s in shots if s.get('technique_path')))
    result['action_family_distribution'] = dict(Counter(s['action_family'] for s in shots if s.get('action_family')))
    result['specialist_plan_distribution'] = dict(Counter(s['specialist_plan'] for s in shots if s.get('specialist_plan')))
    result['tactical_choice_audit'] = [dict(player=s['player'], chosen=s['action'], tactic=s['tactic'],
        observed_weakness=s['decision']['observed_weakness']) for s in shots if 'decision' in s]
    workloads = []
    exposure = []
    for player in (0, 1):
        contacts = [s for s in shots if s.get('player') == player and s.get('technique_path')]
        distance = sum(s.get('movement', {}).get('distance_m', 0) + s.get('recovery_distance_m', 0) for s in contacts)
        attacks = sum(s['action_family'] in ('attack', 'counter', 'open', 'flip', 'slow_loop') for s in contacts)
        movement_m = sum(s.get('movement', {}).get('distance_m', 0) for s in shots if s.get('player') == player and s.get('action') == 'unreached') + distance
        workloads.append(dict(contacts=len(contacts), movement_m=round(movement_m, 5),
                              active_attacks=attacks, effort=round(len(contacts) * .08 + movement_m * .18 + attacks * .03, 5)))
        exposure.append(dict(contacts=len(contacts),
            primary_path_counts=dict(Counter(s['technique_path'] for s in contacts)),
            pressure_contacts=sum(s['reach'] in ('limited', 'bad') or s['fault_prob'] >= .2 for s in contacts)))
    result['workload'] = dict(version='CONTACT_DISTANCE_EFFORT_V1', per_player=workloads)
    result['exposure_by_player'] = exposure
    result['metadata_limits'] = dict(handedness=[geo.normalize_hand(c) for c in cards],
        rubbers=[{w: rubber.rubber_for(c, w) for w in ('fh', 'bh')} for c in cards],
        unknown_geometry='LEGACY_RELATIVE_LABEL_UNRESOLVED',
        balance_status='EXPERIMENTAL_NOT_HISTORICAL_CALIBRATION')
    if detail_level == 'summary' or not keep_points:
        for game in result['games']:
            game.pop('points', None)
        result.pop('tactical_choice_audit', None)
        result.pop('causal_examples', None)
    return result

