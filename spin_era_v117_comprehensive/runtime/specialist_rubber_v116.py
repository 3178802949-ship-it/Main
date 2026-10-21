"""Conditional rubber/contact mechanics for the additive HGR candidate.

This module changes legal contacts and outgoing ball properties. It never emits
quality, G, CA, XP, success probabilities, or a forehand/backhand multiplier.
Coefficients are transparent experimental contact approximations, not a fitted
equipment physics model. Missing equipment remains unknown and passes through
the existing contact result. No historical card is inferred from a player name.
"""
from __future__ import annotations

import copy
import math

import game_v115 as legacy

RUBBERS = ('inverted', 'short_pips', 'raw_pips', 'long_pips', 'anti_spin', 'unknown')
_ALIASES = {
    'inverted': 'inverted', 'reverse': 'inverted', 'pimples_in': 'inverted', '反胶': 'inverted',
    'short_pips': 'short_pips', 'shortpips': 'short_pips', 'pimples_out': 'short_pips',
    '正胶': 'short_pips', '短颗粒': 'short_pips',
    'raw_pips': 'raw_pips', 'raw_short_pips': 'raw_pips', 'shengjiao': 'raw_pips', '生胶': 'raw_pips',
    'long_pips': 'long_pips', 'longpips': 'long_pips', '长胶': 'long_pips',
    'anti_spin': 'anti_spin', 'antispin': 'anti_spin', '防弧': 'anti_spin', '防弧胶皮': 'anti_spin',
    'unknown': 'unknown', 'unspecified': 'unknown', '未知': 'unknown',
}
SPINS = ('top', 'back', 'dead', 'side_top', 'side_back')
POSITIONS = ('good', 'limited', 'bad', 'miss')


def _rubber(value):
    if value is None:
        return 'unknown'
    if isinstance(value, dict):
        fields = [value[k] for k in ('type', 'kind', 'rubber_type') if k in value]
        if not fields:
            raise ValueError('rubber descriptor needs an explicit type')
        normalized = [_rubber(v) for v in fields]
        if len(set(normalized)) != 1:
            raise ValueError('conflicting rubber descriptor types')
        return normalized[0]
    if not isinstance(value, str):
        raise ValueError('rubber type must be a string or explicit descriptor')
    key = value.strip().lower().replace('-', '_').replace(' ', '_')
    if key not in _ALIASES:
        raise ValueError(f'unsupported rubber type: {value}')
    return _ALIASES[key]


def rubber_for(card, wing):
    """Read one face; canonical ``card['rubbers']`` and explicit aliases agree.

    A whole-player scalar rubber label is rejected because it cannot describe
    two independently configured faces. Anti-spin requires an explicit
    ``experimental_anti_spin=True`` on the card or its equipment object.
    """
    if wing not in ('fh', 'bh') or not isinstance(card, dict):
        raise ValueError('a card and explicit fh/bh wing are required')
    equipment = card.get('equipment', {})
    if equipment is None:
        equipment = {}
    if not isinstance(equipment, dict):
        raise ValueError('equipment must be an object')
    found = []
    for source in (card, equipment):
        for key in ('rubbers', 'rubber'):
            if key not in source or source[key] is None:
                continue
            mapping = source[key]
            if not isinstance(mapping, dict) or set(mapping) - {'fh', 'bh'}:
                raise ValueError('rubber metadata must separately identify fh and bh')
            # Validate both faces, including one not currently being queried.
            normalized = {w: _rubber(v) for w, v in mapping.items()}
            if wing in normalized:
                found.append(normalized[wing])
        for key in (f'{wing}_rubber', f'rubber_{wing}'):
            if key in source:
                found.append(_rubber(source[key]))
    if len(set(found)) > 1:
        raise ValueError('conflicting rubber metadata for one face')
    rubber = found[0] if found else 'unknown'
    if rubber == 'anti_spin' and not (card.get('experimental_anti_spin') is True
                                     or equipment.get('experimental_anti_spin') is True):
        raise ValueError('anti_spin requires experimental_anti_spin=True; no calibrated historical equipment claim')
    return rubber


ACTION_SPECS = {}


def _register(suffix, family, alias, child, label):
    for wing, chinese in (('fh', '正手'), ('bh', '反手')):
        ACTION_SPECS[f'{wing}_{suffix}'] = dict(family=family, alias=alias.format(wing=wing),
            technique_path=f'{wing}.{child}', wing=wing, label=chinese + label)


_register('chop', 'chop', 'chop', 'defense', '普通削球')
_register('specialist_chop', 'chop', 'chop', 'defense', '专业削球')
_register('sp_punch', 'attack', '{wing}_attack', 'power', '颗粒弹击')
_register('sp_quick_drive', 'attack', '{wing}_attack', 'continuity', '颗粒快拨')
_register('sp_block', 'block', 'block', 'defense', '颗粒快挡')
_register('sp_flat_hit', 'attack', '{wing}_attack', 'power', '颗粒撞击')
_register('sp_under_attack', 'open', '{wing}_open', 'power', '颗粒突击下旋')
_register('sp_flick', 'flip', 'flip', 'placement', '颗粒台内挑击')
_register('lp_arch', 'push', 'push', 'placement', '长胶拱')
_register('lp_press', 'block', 'block', 'defense', '长胶磕')
_register('lp_wipe', 'push', 'push', 'placement', '长胶刮')
_register('lp_block', 'block', 'block', 'defense', '长胶挡')
_register('lp_chop', 'chop', 'chop', 'defense', '长胶削球')
_register('lp_flat_attack', 'attack', '{wing}_attack', 'power', '长胶低摩擦反攻')
_register('anti_block', 'block', 'block', 'defense', '防弧被动挡（实验）')


def action_spec(action):
    """Stable classification, with G43 paths matching existing growth parsing."""
    if not isinstance(action, str):
        raise ValueError('action must be a stable string identifier')
    if action in ACTION_SPECS:
        return copy.deepcopy(ACTION_SPECS[action])
    wing = 'fh' if action.startswith('fh_') else 'bh' if action.startswith('bh_') else None
    alias = legacy.ALIASES.get(action, action)
    if wing is None:
        wing = 'fh' if alias.startswith('fh_') else 'bh' if alias.startswith('bh_') else None
    if action in legacy.TECH:
        path, label = legacy.TECH[action]
    elif action in ('fh_attack', 'bh_attack', 'fh_counter', 'bh_counter'):
        path, label = f'{wing}.power' if action.endswith('attack') else f'{wing}.continuity', action
    elif action in ('push', 'flip', 'lob'):
        path = {'push': 'table.push', 'flip': 'table.flick', 'lob': 'spirit.lob_arcs'}[action]
        label = action
    else:
        raise ValueError(f'unregistered action: {action}')
    if alias == 'chop':
        family = 'chop'
    elif alias == 'block':
        family = 'block'
    elif alias.startswith('push'):
        family = 'push'
    elif 'flip' in action or 'flick' in action or 'twist' in action or alias == 'flip':
        family = 'flip'
    elif 'slow_loop' in action:
        family = 'slow_loop'
    elif 'counter' in alias:
        family = 'counter'
    elif 'open' in alias:
        family = 'open'
    elif alias == 'lob':
        family = 'lob'
    else:
        family = 'attack'
    return dict(family=family, alias=alias, technique_path=path, wing=wing, label=label)


def legal_action(action, rubber, ball, pos='good'):
    """Reject incompatible equipment and hard length/spin contact conditions.

    A legal action is still only an attempt: arrival, skill, reading and random
    failures are settled by the match engine. Ordinary poor choices retain that
    uncertainty; no rubber makes a listed action automatically successful.
    """
    rubber = _rubber(rubber)
    if not isinstance(ball, dict) or pos not in POSITIONS:
        raise ValueError('valid ball state and arrival position are required')
    if pos == 'miss':
        return False
    spin, length = ball.get('spin', 'top'), ball.get('length', 'long')
    if spin not in SPINS or length not in ('short', 'half', 'long'):
        raise ValueError('unknown incoming spin or length')
    try:
        spec = action_spec(action)
    except ValueError:
        return False
    under, top = spin in ('back', 'side_back'), spin in ('top', 'side_top')
    if '_sp_' in action:
        if rubber not in ('short_pips', 'raw_pips'):
            return False
        suffix = action.split('_sp_', 1)[1]
        if suffix == 'under_attack':
            return under and length != 'short' and pos != 'bad'
        if suffix == 'flick':
            return length in ('short', 'half') and pos != 'bad'
        if suffix == 'block':
            return top and length != 'short'
        return not under and length != 'short' and pos != 'bad'
    if '_lp_' in action:
        if rubber != 'long_pips':
            return False
        suffix = action.split('_lp_', 1)[1]
        if suffix == 'arch':
            return (under or spin == 'dead') and pos != 'bad'
        if suffix in ('press', 'block'):
            return top and length != 'short'
        if suffix == 'wipe':
            return length in ('short', 'half') or spin.startswith('side_')
        if suffix == 'chop':
            return not under and length == 'long'
        if suffix == 'flat_attack':
            return (length != 'short' and pos == 'good'
                    and ((spin == 'dead' and ball.get('quality', 120) <= 124)
                         or (top and ball.get('quality', 120) <= 112)))
    if '_anti_' in action:
        return rubber == 'anti_spin' and top and length != 'short'
    if spec['family'] == 'chop':
        # A short serve has no safe retreating chop contact at the far table.
        return length == 'long' and (rubber not in ('long_pips', 'anti_spin') or not under)
    if rubber in ('long_pips', 'anti_spin'):
        # Passive faces do not perform a conventional high-friction loop/twist.
        if spec['family'] in ('open', 'counter', 'slow_loop') or 'loop' in action or 'twist' in action:
            return False
        if spec['family'] in ('attack', 'flip'):
            return spin == 'dead' and ball.get('quality', 120) <= 124 and pos != 'bad'
    if spec['family'] in ('open', 'counter', 'slow_loop') or 'loop' in action:
        return length != 'short'
    return True


def specialist_actions(rubber, ball, wing, pos='good'):
    """Return additional equipment-specific actions; chopper style is separate."""
    rubber = _rubber(rubber)
    if wing not in ('fh', 'bh'):
        raise ValueError('explicit fh/bh wing required')
    marker = '_sp_' if rubber in ('short_pips', 'raw_pips') else '_lp_' if rubber == 'long_pips' else '_anti_' if rubber == 'anti_spin' else None
    if marker is None:
        return []
    return [a for a in ACTION_SPECS if a.startswith(wing + marker)
            and legal_action(a, rubber, ball, pos)]


def _number(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be finite in [{low}, {high}]')
    return float(value)


def _signed(spin, strength):
    return strength if spin in ('top', 'side_top') else -strength if spin in ('back', 'side_back') else 0.


def _spin(signed, side=False):
    if abs(signed) < 5:
        return 'dead'
    return ('side_' if side else '') + ('top' if signed > 0 else 'back')


def resolve_contact(rubber, action, ball, *, base_spin, base_pace, base_strength):
    """Transform an already-calculated contact, without an extra quality bonus.

    Signed spin is expressed relative to the ball's direction of travel. Passive
    reversal therefore changes top to back (and back to top) on the return. A
    no-spin incoming ball cannot manufacture strong reversal from nothing.
    ``base_strength`` is the engine's one existing generated-spin estimate; it
    is replaced/mixed here rather than adding another technical aptitude roll.
    """
    rubber = _rubber(rubber)
    spec = action_spec(action)
    if base_spin not in SPINS or ball.get('spin', 'top') not in SPINS:
        raise ValueError('known incoming and base spin categories required')
    if rubber != 'unknown' and not legal_action(action, rubber, ball):
        raise ValueError('illegal contact for the declared rubber and incoming ball')
    pace = _number(base_pace, 'base_pace', 0, 250)
    strength = _number(base_strength, 'base_strength', 0, 200)
    if rubber == 'unknown':
        return dict(spin=base_spin, spin_strength=base_strength, pace=base_pace,
                    arc='legacy', variation=0., mechanism='UNKNOWN_RUBBER_LEGACY_PASSTHROUGH',
                    rubber=rubber, experimental=False)
    incoming_spin = ball.get('spin', 'top')
    incoming_strength = ball.get('spin_strength', ball.get('backspin_strength', 110)
                                 if incoming_spin in ('back', 'side_back') else 110)
    incoming_strength = _number(incoming_strength, 'incoming spin strength', 0, 200)
    incoming = _signed(incoming_spin, incoming_strength)
    base = _signed(base_spin, strength)
    signed = base
    arc = 'high' if spec['family'] == 'slow_loop' else 'defensive_arc' if spec['family'] == 'chop' else 'normal'
    mechanism = 'ACTIVE_FRICTION_CONTACT'
    variation = 0.
    if rubber in ('short_pips', 'raw_pips'):
        retention = .44 if rubber == 'short_pips' else .32
        if spec['family'] == 'chop':
            signed = -(strength * (.64 if rubber == 'short_pips' else .52) + max(0., incoming) * .10)
            arc, mechanism = 'low_defensive', 'PIPS_ACTIVE_CHOP'
        elif spec['family'] in ('attack', 'open', 'counter', 'flip'):
            signed = strength * retention
            pace += 7 if rubber == 'short_pips' else 9
            arc, mechanism = 'flat', 'PIPS_DIRECT_CONTACT'
        elif spec['family'] == 'block':
            signed = max(0., incoming) * retention * .55
            pace += 4
            arc, mechanism = 'low', 'PIPS_QUICK_BLOCK'
        else:
            signed = base * .60
            arc, mechanism = 'low', 'PIPS_CONTROL_CONTACT'
        variation = .10 * incoming_strength / 150
    elif rubber == 'long_pips':
        if spec['family'] == 'chop':
            signed = -max(0., incoming) * .64 - strength * .28
            arc, mechanism = 'defensive_arc', 'LONG_PIPS_ACTIVE_CHOP'
            pace -= 4
        elif spec['family'] in ('block', 'push'):
            retention = .52 if action.endswith('lp_arch') else .54 if action.endswith('lp_wipe') else .72
            signed = -incoming * retention
            pace -= 9 if spec['family'] == 'block' else 5
            arc, mechanism = 'low', 'LONG_PIPS_PASSIVE_REVERSAL'
        else:
            signed = base * .16
            arc, mechanism = 'flat', 'LONG_PIPS_LOW_FRICTION_ATTACK'
        variation = min(.55, abs(signed - base) / 350)
    elif rubber == 'anti_spin':
        signed = -incoming * .80
        pace -= 13
        arc, mechanism = 'slow_low', 'EXPERIMENTAL_ANTI_PASSIVE_REVERSAL'
        variation = min(.55, abs(signed - base) / 350)
    spin = _spin(signed, incoming_spin.startswith('side_') if rubber in ('long_pips', 'anti_spin') else base_spin.startswith('side_'))
    return dict(spin=spin, spin_strength=round(min(170., abs(signed)), 3),
                pace=round(max(45., min(190., pace)), 3), arc=arc,
                variation=round(variation, 5), mechanism=mechanism,
                rubber=rubber, experimental=rubber == 'anti_spin')
