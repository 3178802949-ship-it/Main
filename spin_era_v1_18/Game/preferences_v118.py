"""Small, bounded action preferences on the existing legal probability pool.

Axes describe preferred means, never proficiency or personality. They do not
modify legal contacts, daily form, quality, mistakes, movement or point draws.
The +/-10% multiplier is a transparent game-design candidate, not a published
effect size. All-neutral preferences return the original pool unchanged.
"""
from __future__ import annotations

import copy
import math

from common import RUNTIME
import specialist_rubber_v116 as rubber

VERSION = 'V1.1.7-COMPREHENSIVE-STYLE-PREFERENCE-1'
STYLE_VERSION = 'V1.1.7-COMPREHENSIVE-STYLE-1'
AXES = ('forehand_use', 'backhand_use', 'short_game', 'first_three', 'rally',
        'away_table', 'topspin_preference', 'backspin_control', 'spin_variation',
        'initiative', 'counterattack', 'risk')
OBSERVATION_ONLY = ('rally', 'away_table', 'spin_variation')
MULTIPLIER_BOUND = .10
OFFENSIVE = frozenset(('attack', 'open', 'counter', 'flip', 'slow_loop'))


def axes_of(card):
    profile = card.get('style_profile')
    if profile is None:
        return dict.fromkeys(AXES, .5)
    if not isinstance(profile, dict) or profile.get('version') != STYLE_VERSION:
        raise ValueError('a known style_profile version is required')
    axes = profile.get('axes')
    if not isinstance(axes, dict) or set(axes) != set(AXES):
        raise ValueError('style axes must contain the complete registered axis set')
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in axes.values()):
        raise ValueError('style axes must be finite values in 0..1')
    return dict(axes)


def neutral(axes):
    return all(value == .5 for value in axes.values())


def multiplier(axes, card, state, ball, position, candidate):
    """Bounded soft prior; tactical/arrival/skill weights remain authoritative."""
    action, wing = candidate['action'], candidate['wing']
    family = rubber.action_spec(action)['family']
    active = family in OFFENSIVE
    material = rubber.rubber_for(card, wing)
    features = dict.fromkeys(AXES, 0.)
    features['forehand_use'] = 1. if wing == 'fh' else -1.
    features['backhand_use'] = -features['forehand_use']
    # An illegal table/short contact is never added to the legal menu.
    if ball.get('length') in ('short', 'half_long'):
        features['short_game'] = 1. if family in ('push', 'flip', 'block') else -.35
    elif 'short' in action or action == 'short_stop_drop':
        features['short_game'] = 1.
    # Equipment's later spin conversion must not be mistaken for an inverted
    # topspin preference. Its specialist plans continue to govern that case.
    if material in ('inverted', 'unknown'):
        features['topspin_preference'] = 1. if active else -.25
        features['backspin_control'] = 1. if family in ('push', 'chop') else -.25
    features['initiative'] = 1. if active else -.35
    features['counterattack'] = 1. if family in ('counter', 'block') else -.2
    early = ball.get('origin') in ('service', 'service_return', 'third_ball')
    if early:
        features['first_three'] = 1. if active else -.25
    # Arrival defeats a willingness to take risks; no additional aggressive
    # multiplier is available for a limited or bad contact.
    if position == 'good':
        features['risk'] = 1. if active else -.4
    score = sum((axes[name] - .5) * 2 * value for name, value in features.items()) / 6.
    return 1. + max(-MULTIPLIER_BOUND, min(MULTIPLIER_BOUND, score * MULTIPLIER_BOUND))


def apply_preferences(options, card, state, ball, position, *, audit=None):
    axes = axes_of(card)
    if neutral(axes):
        if audit is not None:
            audit['neutral_calls'] += 1
        return options
    adjusted = copy.deepcopy(options)
    factors = [multiplier(axes, card, state, ball, position, item) for item in options]
    if all(factor == 1. for factor in factors):
        if audit is not None:
            audit['neutral_calls'] += 1
        return options
    total = sum(item['probability'] * factor for item, factor in zip(options, factors))
    if not math.isfinite(total) or total <= 0:
        raise ValueError('invalid candidate probability mass')
    for old, item, factor in zip(options, adjusted, factors):
        item['probability'] = old['probability'] * factor / total
    if audit is not None:
        audit['weighted_calls'] += 1
        audit['min_multiplier'] = min(audit['min_multiplier'], min(factors))
        audit['max_multiplier'] = max(audit['max_multiplier'], max(factors))
        audit['max_pool_probability_shift'] = max(audit['max_pool_probability_shift'],
            max(abs(a['probability'] - b['probability']) for a, b in zip(adjusted, options)))
    return adjusted


def new_audit(card):
    axes = axes_of(card)
    return dict(player_id=card['player_id'], version=VERSION, neutral=neutral(axes),
        active_axes=[name for name in AXES if name not in OBSERVATION_ONLY and axes[name] != .5],
        observation_only_axes=list(OBSERVATION_ONLY), neutral_calls=0, weighted_calls=0,
        min_multiplier=1., max_multiplier=1., max_pool_probability_shift=0.,
        personality_used=False, effect='LEGAL_ACTION_PRIOR_ONLY',
        risk_context='RISK_AXIS_INACTIVE_FOR_LIMITED_OR_BAD_ARRIVAL')
