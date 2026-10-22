"""Small separate decision menus for choppers, pips players and attackers.

Plans alter legal-contact preference, preparation, placement and ball properties.
They never multiply a character's G, quality, CA or learning rewards. All
opponent information is visible position/ball state or the observer's own log.
"""
from __future__ import annotations

import copy
import math

from common import RUNTIME
import game_v112 as core
import specialist_rubber_v116 as rubber
from Game import observed_tactics as observed

PLANS = {
    'chop_heavy': dict(kind='chopper', depth=1.72, target='observed_weak_side', spin_mode='heavy',
                       families={'chop': 4.6, 'block': .7, 'attack': .45, 'counter': .45}),
    'chop_float': dict(kind='chopper', depth=1.56, target='reverse_direction', spin_mode='float',
                       families={'chop': 4.1, 'push': 1.4, 'attack': .45, 'counter': .45}),
    'chop_reposition': dict(kind='chopper', depth=1.68, target='wide_movement', spin_mode='control',
                            families={'chop': 3.6, 'block': 1.2, 'attack': .55}),
    'chop_counter': dict(kind='chopper', depth=1.10, target='finish_weak_ball', spin_mode='normal',
                         families={'attack': 3.1, 'counter': 3.0, 'open': 1.6, 'chop': .55}),
    'chop_table_reset': dict(kind='chopper', depth=.85, target='short_long', spin_mode='control',
                             families={'push': 3.0, 'block': 1.8, 'flip': 1.4, 'chop': .1}),
    'pips_early_pressure': dict(kind='short_pips', depth=1.02, target='observed_weak_side', spin_mode='normal',
                                families={'attack': 2.3, 'counter': 1.5, 'block': .8, 'slow_loop': .25}),
    'pips_punch_finish': dict(kind='short_pips', depth=1.05, target='finish_weak_ball', spin_mode='normal',
                              families={'attack': 3.0, 'open': 1.8, 'block': .55, 'slow_loop': .2}),
    'pips_block_redirect': dict(kind='short_pips', depth=1.06, target='reverse_direction', spin_mode='control',
                                families={'block': 3.1, 'push': 1.3, 'attack': .8, 'slow_loop': .3}),
    'pips_change_rhythm': dict(kind='short_pips', depth=1.12, target='wide_movement', spin_mode='change',
                               families={'block': 1.3, 'push': 1.2, 'attack': 1.2, 'slow_loop': .3}),
    'long_pips_reverse_hold': dict(kind='long_pips', depth=1.12, target='observed_weak_side', spin_mode='normal',
                                   families={'block': 3., 'push': 1.7, 'chop': .7, 'attack': .4}),
    'long_pips_active_change': dict(kind='long_pips', depth=1.05, target='reverse_direction', spin_mode='change',
                                    families={'push': 2.5, 'block': 1.3, 'attack': .7}),
    'long_pips_float': dict(kind='long_pips', depth=1.12, target='short_long', spin_mode='pips_float',
                            families={'block': 2., 'push': 2., 'chop': .6, 'attack': .45}),
    'long_pips_flat_finish': dict(kind='long_pips', depth=1.08, target='finish_weak_ball', spin_mode='normal',
                                  families={'attack': 4., 'block': .6, 'push': .6}),
    'patient_loop': dict(kind='attacker', depth=1.18, target='patient_loop', spin_mode='normal',
                         families={'slow_loop': 1.8, 'open': 1.5, 'attack': .85}),
    'spin_pace_mix': dict(kind='attacker', depth=1.18, target='spin_pace_mix', spin_mode='change', families={}),
    'wide_movement': dict(kind='attacker', depth=1.18, target='wide_movement', spin_mode='normal', families={}),
    'short_long': dict(kind='attacker', depth=1.12, target='short_long', spin_mode='control', families={'push': 1.6}),
    'observed_weak_side': dict(kind='attacker', depth=1.18, target='observed_weak_side', spin_mode='normal', families={}),
    'finish_weak_ball': dict(kind='attacker', depth=1.14, target='finish_weak_ball', spin_mode='normal',
                             families={'attack': 2.2, 'counter': 1.4, 'push': .65}),
}


def specialist_kind(card, ball=None):
    explicit = card.get('tactical_family')
    if explicit is not None:
        if explicit not in ('chopper', 'short_pips', 'long_pips', 'attacker'):
            raise ValueError('unsupported tactical_family')
        if explicit in ('short_pips', 'long_pips'):
            faces = {rubber.rubber_for(card, w) for w in ('fh', 'bh')}
            if explicit == 'short_pips' and not faces.intersection({'short_pips', 'raw_pips'}):
                raise ValueError('short-pips plans require a declared short/raw-pips face')
            if explicit == 'long_pips' and not faces.intersection({'long_pips', 'anti_spin'}):
                raise ValueError('long-pips plans require a declared passive face')
        return explicit
    if card.get('style') == 'modern_chopper':
        return 'chopper'
    side = ball.get('landed') if ball else None
    faces = [rubber.rubber_for(card, side)] if side in ('fh', 'bh') else [rubber.rubber_for(card, w) for w in ('fh', 'bh')]
    if any(face in ('short_pips', 'raw_pips') for face in faces):
        return 'short_pips'
    if any(face in ('long_pips', 'anti_spin') for face in faces):
        return 'long_pips'
    return 'attacker'


def plan_distribution(card, state, ball, opponent_position=None):
    """Build auditable probabilities without reading opponent ratings or RNG."""
    kind = specialist_kind(card, ball)
    choices = [name for name, item in PLANS.items() if item['kind'] == kind]
    requested = card.get('tactical_plan', 'adaptive')
    if isinstance(requested, dict):
        requested = requested.get(kind, 'adaptive')
    if requested != 'adaptive':
        if requested not in choices:
            raise ValueError('tactical_plan is incompatible with this tactical family')
        return [dict(plan=requested, kind=kind, probability=1., preparation_depth=PLANS[requested]['depth'])]
    quality = float(ball.get('quality', 120))
    length, spin = ball.get('length', 'long'), ball.get('spin', 'top')
    short, under = length != 'long', spin in ('back', 'side_back')
    weak = quality < 118 or ball.get('return_state') == 'high_ball'
    read = core.gg(card, state, 'read')
    evidence = observed.inferred_weakness(state)
    weights = {name: 1. for name in choices}
    if kind == 'chopper':
        weights.update(chop_heavy=.4 if short or under else 3.1,
                       chop_float=.35 if short else 1.4,
                       chop_reposition=.35 if short else 1.4,
                       chop_counter=3.4 if weak and not short else .10,
                       chop_table_reset=4.5 if short or under else .20)
    elif kind == 'short_pips':
        weights.update(pips_early_pressure=1.7 if not short else .8,
                       pips_punch_finish=3.2 if weak or under and length != 'short' else .6,
                       pips_block_redirect=2.8 if not under and quality >= 129 else .8,
                       pips_change_rhythm=1.4)
    elif kind == 'long_pips':
        weights.update(long_pips_reverse_hold=2.8 if not under else .7,
                       long_pips_active_change=2.4 if short or under else .8,
                       long_pips_float=1.3,
                       long_pips_flat_finish=3.5 if (spin == 'dead' and quality <= 124 or
                           spin in ('top', 'side_top') and quality <= 112) and length != 'short' else .04)
    else:
        weights.update(patient_loop=1.8 if under else 1.2, spin_pace_mix=1.3,
                       wide_movement=1., short_long=1.6 if opponent_position and abs(opponent_position['y']) > 1.4 and quality < 134 else .3,
                       observed_weak_side=1.6 if evidence else .05, finish_weak_ball=2.8 if weak else .08)
    # Reading only changes condition sensitivity. It adds no quality or G.
    sensitivity = core.clamp(.65 + (read - 100) / 120, .45, 1.15)
    weights = {name: max(.005, value) ** sensitivity for name, value in weights.items()}
    total = sum(weights.values())
    return [dict(plan=name, kind=kind, probability=weights[name] / total,
                 preparation_depth=PLANS[name]['depth']) for name in choices]


def choose_plan(card, state, ball, opponent_position, rng):
    options = plan_distribution(card, state, ball, opponent_position)
    selected = rng.choices(options, weights=[item['probability'] for item in options])[0]
    return dict(selected, distribution=options)


def action_multiplier(plan, spec, action, ball, previous_family=None):
    definition = PLANS[plan]
    multiplier = definition['families'].get(spec['family'], 1.)
    if plan in ('pips_punch_finish', 'pips_early_pressure') and '_sp_' in action:
        multiplier *= 1.3
    if plan == 'long_pips_active_change' and action.endswith(('lp_arch', 'lp_wipe')):
        multiplier *= 1.6
    if plan == 'long_pips_flat_finish' and action.endswith('lp_flat_attack'):
        multiplier *= 1.8
    if plan in ('spin_pace_mix', 'pips_change_rhythm'):
        multiplier *= 1.7 if spec['family'] != previous_family else .7
    if plan == 'short_long' and action == 'short_stop_drop':
        multiplier *= 3.
    return multiplier


def contact_properties(contact, plan, family, previous_family=None):
    """Apply deliberate spin/tempo choices to the already-calculated contact."""
    result = copy.deepcopy(contact)
    mode = PLANS[plan]['spin_mode']
    if mode == 'float' and family == 'chop':
        result.update(spin='dead', spin_strength=round(min(9., result['spin_strength'] * .04 + 2), 3),
                      pace=round(result['pace'] * .96, 3), arc='low_defensive',
                      variation=max(result['variation'], .22), mechanism=result['mechanism'] + '+DELIBERATE_FLOAT')
    elif mode == 'heavy' and family == 'chop':
        result.update(spin_strength=round(min(170., result['spin_strength'] * 1.05), 3),
                      pace=round(result['pace'] * .94, 3), arc='defensive_arc',
                      mechanism=result['mechanism'] + '+HEAVY_SPIN_TEMPO')
    elif mode == 'pips_float' and family in ('block', 'push'):
        result.update(spin_strength=round(result['spin_strength'] * .45, 3),
                      pace=round(result['pace'] * .93, 3), arc='low',
                      variation=max(result['variation'], .17), mechanism=result['mechanism'] + '+REDUCED_REVERSAL')
    elif mode == 'control' and family in ('chop', 'block', 'push'):
        result['pace'] = round(result['pace'] * .94, 3)
    elif mode == 'change' and family != previous_family:
        result['variation'] = max(result['variation'], .10)
        if family in ('push', 'block'):
            result['pace'] = round(result['pace'] * .94, 3)
    return result
