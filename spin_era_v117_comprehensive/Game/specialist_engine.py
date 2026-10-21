"""Incremental geometry/contact candidate on the frozen V1.1.6 match runner.

The existing warm-up, G9/P6/CA, scoring, shot-quality and psychological formulas
remain dependencies. New code supplies physical demands, legal contacts and
observed-information decisions. Only isolated Game.worker processes use hooks.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import math
from pathlib import Path

from common import canonical_json
from Game import geometry as geo
from Game import observed_tactics as observed
import specialist_rubber_v116 as rubber
import tactical_match_v116 as tactical
import game_v115 as legacy

core = legacy.core
TAG = 'V1.1.6-HGR-CANDIDATE-1'
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


def _interception(card, end, bounce, length, *, spin='top'):
    if length == 'short':
        depth = .48
    elif length == 'half':
        depth = 1.02
    elif card.get('style') == 'modern_chopper' and spin in ('top', 'side_top'):
        depth = 1.72
    else:
        depth = 1.18
    # A long wide ball continues outwards after bouncing; it is not intercepted
    # at the table bounce itself. This is a coarse geometry model, not physics.
    spread = 1.18 if length == 'long' else 1.
    return dict(x=core.clamp(bounce['x'] * spread, -1.40, 1.40), y=_sign(end) * depth)


def _grade(score):
    return 'miss' if score < -21 else 'bad' if score < -10 else 'limited' if score < 2 else 'good'


def reach(card, state, ball, rng, step, end):
    """Original reach skill/noise; actual distance replaces abstract lane cost."""
    stance = state['hgr_position']
    contact = _interception(card, end, ball['absolute_target'], ball['length'], spin=ball['spin'])
    dx = (contact['x'] - stance['x']) * geo.HALF_WIDTH_M
    dy = (contact['y'] - stance['y']) * geo.HALF_LENGTH_M
    distance = math.hypot(dx, dy)
    reverse = ((contact['x'] - stance['x']) * stance['momentum_x'] < -.015
               or (contact['y'] - stance['y']) * stance['momentum_y'] < -.015)
    p = state['p_eff']
    skill = (.50 * core.gg(card, state, 'feet') + .19 * p['speed'] + .15 * p['agility']
             + .10 * p['flexibility'] + .06 * core.gg(card, state, 'read'))
    # No fixed modern_chopper +5.8: a prepared deep stance is represented by
    # its actual distance to the next interception, not an extra ability bonus.
    physical_demand = 7 * distance / geo.HALF_WIDTH_M
    recovery_cost = (1 - stance['recovery']) * 3 + 2.5 * reverse
    load_before = state['hgr_rally_load']
    load_cost = min(5., load_before * .16 + state['hgr_match_load'] * .05)
    demand = (121 + .29 * (ball['quality'] - 120) + .22 * (ball['pace'] - 120)
              + physical_demand + recovery_cost + min(8, step * .26)
              + state['match_stamina'] * .16 + load_cost)
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
                    reversing=bool(reverse), recovery_cost=round(recovery_cost, 4),
                    physical_demand=round(physical_demand, 4), load_before=round(load_before, 5),
                    load_after=round(state['hgr_rally_load'], 5), match_load=round(state['hgr_match_load'], 5),
                    mapped_contact_side=side, mapping_resolved=side != 'unknown', step_around=False)
    return pos, round(score, 4), mapped, movement


def _wing(action, ball, card):
    spec = rubber.action_spec(action)
    if spec['wing']:
        return spec['wing']
    if ball['landed'] in ('fh', 'bh'):
        return ball['landed']
    return max(('fh', 'bh'), key=lambda w: card['children'][w]['defense'])


def _tactic(card, state, ball, pos, opponent_position, rng):
    if card.get('style') == 'modern_chopper':
        choices = ['defend', 'reverse_direction', 'counterattack']
        weights = [3., 1., 2.4 if ball['quality'] < 118 and pos == 'good' else .15]
    else:
        choices = ['patient_loop', 'spin_pace_mix', 'wide_movement', 'short_long', 'observed_weak_side']
        weights = [1.7, 1.3, 1., 1.5 if abs(opponent_position['y']) > 1.4 and ball['quality'] < 134 else .3,
                   1.4 if observed.inferred_weakness(state) else .05]
        if ball['quality'] < 114 and pos == 'good':
            choices.append('finish_weak_ball')
            weights.append(2.5)
    return rng.choices(choices, weights=weights)[0]


def action_distribution(card, state, ball, pos, tactic):
    """Use existing own-skill/fit policy; filter physical and equipment legality."""
    old = tactical.action_distribution(card, state, ball, pos)
    old_candidates = {item['action']: item for item in old['candidates']}
    names = [x['action'] for x in old['candidates']]
    chopper = card.get('style') == 'modern_chopper'
    for wing in ('fh', 'bh'):
        names += rubber.specialist_actions(rubber.rubber_for(card, wing), ball, wing, pos)
        if ball['length'] == 'long':
            names.append(f'{wing}_specialist_chop' if chopper else f'{wing}_chop')
        if chopper and ball['quality'] < 121:
            names.extend((f'{wing}_fast_loop', f'{wing}_counter_loop'))
    if tactic == 'short_long' and ball['quality'] <= 134 and pos != 'bad':
        names.append('short_stop_drop')
    result = []
    for action in dict.fromkeys(names):
        if action in ('chop', 'chop_transition'):
            continue
        spec = rubber.action_spec(action)
        wing = _wing(action, ball, card)
        material = rubber.rubber_for(card, wing)
        if not rubber.legal_action(action, material, ball, pos):
            continue
        group, child = spec['technique_path'].split('.')
        if action in legacy.TECH:
            aptitude = old_candidates[action]['aptitude'] if action in old_candidates else legacy.player_aptitude(card, state, action) - .17 * (core.gg(card, state, 'read') - 120)
            fit = legacy.fit(action, ball, pos, old['scenario'])
        else:
            aptitude = (.38 * card['children'][group][child] + .24 * core.gg(card, state, 'receive')
                        + .17 * 120 + .11 * core.gg(card, state, 'table') + .10 * core.gg(card, state, wing))
            fit = -5 if pos == 'bad' else -2 if pos == 'limited' else 0
        mismatch = ball['landed'] in ('fh', 'bh') and wing != ball['landed']
        if mismatch:
            fit -= 8 if pos == 'good' else 17
        weight = math.exp(core.clamp((aptitude - 115) / 27 + old['fit_temperature'] * fit / 13, -8, 3))
        # Keep the existing live policy preferences operative for newly named
        # contacts as well as legacy actions. State changes therefore still
        # alter actual decisions, rather than just the commentary.
        defensive = spec['family'] in ('chop', 'block', 'push', 'lob')
        if state.get('policy') == 'receive_initiative' and not defensive:
            weight *= 1.38
        if state.get('policy') == 'defensive_pivot' and defensive:
            weight *= 1.7
        if state.get('policy') == 'bh_squeeze' and wing == 'bh':
            weight *= 1.35
        # Style chooses a contact family, never an extra FH/BH quality factor.
        if chopper and spec['family'] == 'chop':
            weight *= 4.4 if ball['spin'] in ('top', 'side_top') else 1.2
        elif spec['family'] == 'chop':
            weight *= .65 if pos == 'bad' else .12
        if tactic == 'counterattack':
            weight *= 2.8 if spec['family'] in ('counter', 'attack') else .65
        elif tactic == 'patient_loop':
            weight *= 1.8 if spec['family'] in ('slow_loop', 'open') else .85 if spec['family'] == 'attack' else 1
        elif tactic == 'spin_pace_mix':
            prior = state.get('hgr_last_family')
            weight *= 1.9 if spec['family'] in ('slow_loop', 'attack', 'counter', 'open') and spec['family'] != prior else 1
        elif tactic == 'short_long':
            weight *= 3. if action == 'short_stop_drop' else 1
        elif tactic == 'finish_weak_ball':
            weight *= 2. if spec['family'] == 'attack' else .7
        result.append(dict(action=action, weight=weight, family=spec['family'], wing=wing))
    if not result:
        # Every face has a legal conservative contact in these contexts. A
        # failed emergency contact remains subject to arrival/error probability.
        action = 'push_long' if ball['spin'] in ('back', 'side_back') else 'block'
        result = [dict(action=action, weight=1., family=rubber.action_spec(action)['family'], wing=_wing(action, ball, card))]
    total = sum(c['weight'] for c in result)
    for c in result:
        c['probability'] = c.pop('weight') / total
    return result


def target_distribution(card, state, ball, opponent_card, opponent_state, action, tactic, end, outgoing_spin='top'):
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
            rc = _interception(opponent_card, other_end, target, length, spin=outgoing_spin)
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
    desired_depth = 1.68 if card.get('style') == 'modern_chopper' and family in ('chop', 'block') else 1.12
    fraction = core.clamp((.32 + core.gg(card, state, 'feet') * .002) * 115 / max(85, pace), .25, .72)
    dx = -s['x'] * fraction
    dy = (_sign(end) * desired_depth - s['y']) * fraction
    recovery_distance = math.hypot(dx * geo.HALF_WIDTH_M, dy * geo.HALF_LENGTH_M)
    s.update(x=s['x'] + dx, y=s['y'] + dy, recovery=core.clamp(.58 + fraction * .5, 0, 1),
             momentum_x=dx, momentum_y=dy)
    state['hgr_rally_load'] += recovery_distance * .1
    return recovery_distance


def _quality(card, state, ball, pos, action, rng, step, clutch, wing):
    spec = rubber.action_spec(action)
    source = dict(ball, landed=wing)
    source['spin'] = 'back' if ball['spin'] == 'side_back' else 'top' if ball['spin'] == 'side_top' else ball['spin']
    query_action = spec['alias'] if action in rubber.ACTION_SPECS else action
    return core._older_quality(card, state, source, pos, query_action, rng, step, clutch)


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
        backspin_strength=125 if spin in ('back', 'side_back') else 0, spin_strength=125 if spin != 'dead' else 0,
        absolute_target=absolute, variation=0.)
    serv['serve_forms'][zone + '|' + spin + '|' + serve_style] += 1
    serv['last_serve'] = dict(zone=zone, spin=spin, style=serve_style)
    shots = [dict(player=server, action='serve', zone=zone, style=serve_style, spin=spin, length=length,
                  landed=aim, quality=round(servq, 2), absolute_target=absolute, spin_strength=ball['spin_strength'],
                  return_state='serve', handedness=geo.normalize_hand(scard))] if keep_shots else []
    n = recv
    for step in range(1, 42):
        card, state, op = cards[n], states[n], states[1 - n]
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
        base += recognition_risk + min(.045, state['hgr_rally_load'] * .0015)
        base = core.clamp(base, .026, .58)
        knowledge[spin_key] += 1
        common = dict(player=n, action=action, action_family=spec['family'], stroke_side=wing,
            technique_path=spec['technique_path'], technique_label=spec['label'], rubber=material,
            handedness=geo.normalize_hand(card), reach=pos, reach_score=score_reach, input_target=mapped,
            input_spin=ball['spin'], input_spin_strength=ball['spin_strength'], input_quality=round(ball['quality'], 3),
            movement=movement, out_quality=round(quality, 3), quality=round(quality, 3), pace=contact['pace'],
            spin=contact['spin'], spin_strength=contact['spin_strength'], spin_contact=contact,
            fault_prob=round(base, 6), recognition_risk=round(recognition_risk, 6),
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
        targets = target_distribution(card, state, local_ball, cards[1 - n], op, action, tactic, n,
                                      outgoing_spin=contact['spin'])
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
            receiver_contact=_interception(cards[1 - n], 1 - n, landed_abs, target_length, spin=contact['spin']),
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
                    rubber=material, variation=contact['variation'])
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


def play_match(cards, seed, *, keep_points=True, fatigue=(25, 25), max_games=7):
    if max_games != 7:
        raise ValueError('HGR candidate currently supports BO7 only')
    saved = {k: getattr(core, k) for k in ('point', 'between_games', 'attempt_in_game_adaptation')}
    try:
        core.point = point
        core.between_games = observed.between_games
        core.attempt_in_game_adaptation = observed.attempt_in_game_adaptation
        result = tactical.play_match(cards, seed, keep_points=keep_points, fatigue=fatigue, max_games=max_games)
    finally:
        for key, value in saved.items():
            setattr(core, key, value)
    result['engine'] = TAG
    result['ruleset'] = TAG
    result['tactical_patch'] = 'OBSERVED_GEOMETRY_CONTACT_CANDIDATE'
    result['mechanics_source_sha256'] = {str(p.relative_to(Path(__file__).resolve().parents[1])):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            Path(__file__), Path(geo.__file__), Path(rubber.__file__), Path(observed.__file__))}
    if keep_points:
        shots = [s for g in result['games'] for p in g['points'] for s in p['shots']]
        result['technique_distribution'] = dict(Counter(s['action'] for s in shots if s.get('technique_path')))
        result['technique_path_distribution'] = dict(Counter(s['technique_path'] for s in shots if s.get('technique_path')))
        result['action_family_distribution'] = dict(Counter(s['action_family'] for s in shots if s.get('action_family')))
        result['tactical_choice_audit'] = [dict(player=s['player'], chosen=s['action'], tactic=s['tactic'],
            observed_weakness=s['decision']['observed_weakness']) for s in shots if 'decision' in s]
    result['metadata_limits'] = dict(handedness=[geo.normalize_hand(c) for c in cards],
        rubbers=[{w: rubber.rubber_for(c, w) for w in ('fh', 'bh')} for c in cards],
        unknown_geometry='LEGACY_RELATIVE_LABEL_UNRESOLVED; physical movement still logged',
        balance_status='EXPERIMENTAL_NOT_HISTORICAL_CALIBRATION')
    return result
