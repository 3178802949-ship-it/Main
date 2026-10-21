"""Pure table geometry shared by shot selection, interception and match logs.

Coordinates are absolute, not anatomical lanes: x is half-table width (0.7625m)
and y is half-table length (1.37m). End 0 stands at negative y and faces +y;
end 1 stands at positive y and faces -y. Stances/contact points may be behind
the table. Handedness only maps these coordinates to FH/BH; it adds no skill.
"""
from __future__ import annotations

from collections.abc import Mapping
import math

HALF_WIDTH_M = .7625
HALF_LENGTH_M = 1.37
MIDDLE_X = .18
LENGTH_DEPTH = {'short': .28, 'half': .64, 'long': .90}


def _number(value, name, *, low=None, high=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number, not a boolean')
    if low is not None and value < low or high is not None and value > high:
        raise ValueError(f'{name} outside its allowed range')
    return float(value)


def _end(value):
    if type(value) is not int or value not in (0, 1):
        raise ValueError('table end must be integer 0 or 1')
    return value


def _point(value, name):
    if not isinstance(value, Mapping) or 'x' not in value or 'y' not in value:
        raise ValueError(f'{name} requires absolute x and y coordinates')
    return dict(x=_number(value['x'], f'{name}.x'), y=_number(value['y'], f'{name}.y'))


def _stance(value, name):
    point = _point(value, name)
    point.update(recovery=_number(value.get('recovery', 1.), f'{name}.recovery', low=0, high=1),
                 momentum_x=_number(value.get('momentum_x', 0.), f'{name}.momentum_x'),
                 momentum_y=_number(value.get('momentum_y', 0.), f'{name}.momentum_y'),
                 movement_load=_number(value.get('movement_load', 0.), f'{name}.movement_load', low=0))
    return point


def _hand_value(value):
    if value is None:
        return 'unknown'
    if not isinstance(value, str):
        raise ValueError('handedness must be a string or null')
    text = value.strip().lower().replace('_', '-').replace(' ', '-')
    if text in ('r', 'right', 'right-handed', '右', '右手', '右手持拍'):
        return 'right'
    if text in ('l', 'left', 'left-handed', '左', '左手', '左手持拍'):
        return 'left'
    # Missing/unsupported evidence remains unknown. A name, grip or rubber type
    # is never enough to infer a playing hand.
    return 'unknown'


def normalize_hand(card_or_value):
    """Read explicit hand/handedness fields; reject contradictory evidence."""
    if isinstance(card_or_value, Mapping):
        values = {_hand_value(card_or_value.get(key)) for key in ('hand', 'handedness')}
        known = values - {'unknown'}
        if len(known) > 1:
            raise ValueError('conflicting hand and handedness evidence')
        return next(iter(known)) if known else 'unknown'
    return _hand_value(card_or_value)


def lane_to_point(lane, hand, end, length='long'):
    """Map a receiver-relative table lane to an absolute table bounce.

    Unknown FH/BH geometry returns None, rather than silently assuming right
    handedness. The physical centre line is still known for a middle target.
    """
    end = _end(end)
    hand = normalize_hand(hand)
    if lane not in ('fh', 'bh', 'middle') or length not in LENGTH_DEPTH:
        raise ValueError('unknown lane or length')
    if lane != 'middle' and hand == 'unknown':
        return None
    facing_x = 1 if end == 0 else -1
    forehand_x = 1 if hand == 'right' else -1
    local_x = 0. if lane == 'middle' else .72 * forehand_x * (1 if lane == 'fh' else -1)
    return dict(x=local_x * facing_x, y=LENGTH_DEPTH[length] * (-1 if end == 0 else 1))


def point_to_lane(point, hand, end, stance=None):
    """Return the anatomical lane at the table centre or at a supplied body.

    Without stance this is a nominal table-side label. With stance it describes
    where the ball is relative to the receiver's *current* body. Unknown hands
    return unknown even at the centre; physical middle/body flags are separate.
    """
    end = _end(end)
    point = _point(point, 'point')
    body_x = _point(stance, 'stance')['x'] if stance is not None else 0.
    hand = normalize_hand(hand)
    if hand == 'unknown':
        return 'unknown'
    local_x = (point['x'] - body_x) * (1 if end == 0 else -1)
    if abs(local_x) <= MIDDLE_X:
        return 'middle'
    forehand_x = 1 if hand == 'right' else -1
    return 'fh' if local_x * forehand_x > 0 else 'bh'


def _distance(a, b):
    return math.hypot((a['x'] - b['x']) * HALF_WIDTH_M,
                      (a['y'] - b['y']) * HALF_LENGTH_M)


def map_line(*, hitter_hand, receiver_hand, hitter_end, hitter_stance,
             receiver_stance, incoming, target, technique,
             receiver_contact=None, incoming_contact=None):
    """Describe a line and its physical movement demands, without mutation/RNG.

    incoming and target are actual bounces. Optional contact points keep a long
    ball's deeper interception separate from its bounce: a retreating chopper
    need not run to the table to hit every long ball. Outputs are geometry and
    pressure signals; callers resolve ability and probability with the existing
    G/P/state mechanisms, not with a hidden FH/BH quality multiplier.
    """
    hitter_end = _end(hitter_end)
    receiver_end = 1 - hitter_end
    hitter_hand, receiver_hand = normalize_hand(hitter_hand), normalize_hand(receiver_hand)
    hs, rs = _stance(hitter_stance, 'hitter_stance'), _stance(receiver_stance, 'receiver_stance')
    incoming, target = _point(incoming, 'incoming'), _point(target, 'target')
    hc = _point(incoming_contact, 'incoming_contact') if incoming_contact is not None else incoming.copy()
    rc = _point(receiver_contact, 'receiver_contact') if receiver_contact is not None else target.copy()
    if not isinstance(technique, str) or not technique:
        raise ValueError('nonempty technique identifier required')
    hitter_sign, receiver_sign = (-1 if hitter_end == 0 else 1), (-1 if receiver_end == 0 else 1)
    if incoming['y'] * hitter_sign < 0 or hc['y'] * hitter_sign < 0:
        raise ValueError('incoming bounce/contact must be on the hitter side')
    if target['y'] * receiver_sign < 0 or rc['y'] * receiver_sign < 0:
        raise ValueError('target bounce/contact must be on the receiver side')

    hitter_side = point_to_lane(hc, hitter_hand, hitter_end, hs)
    table_side = point_to_lane(target, receiver_hand, receiver_end)
    contact_side = point_to_lane(rc, receiver_hand, receiver_end, rs)
    dx, dy = rc['x'] - rs['x'], rc['y'] - rs['y']
    dx_m, dy_m = dx * HALF_WIDTH_M, dy * HALF_LENGTH_M
    distance = math.hypot(dx_m, dy_m)
    forward = -dy * receiver_sign * HALF_LENGTH_M
    lateral_direction = 'right' if dx_m > .015 else 'left' if dx_m < -.015 else 'none'
    depth_direction = 'forward' if forward > .015 else 'backward' if forward < -.015 else 'none'
    direction = (lateral_direction if abs(dx_m) >= abs(dy_m) else depth_direction) if distance > .015 else 'none'
    span_x, span_y = target['x'] - hc['x'], target['y'] - hc['y']
    crosscourt = hc['x'] * target['x'] < -(MIDDLE_X ** 2)
    straight = abs(span_x) <= .22
    middle = abs(target['x']) <= MIDDLE_X
    body = abs(dx_m) <= .14 and abs(dy_m) <= .80
    wide = abs(target['x']) >= .82
    wide_angle = wide and abs(span_x) >= .90
    geometric_line = 'down_the_line' if straight else 'crosscourt' if crosscourt else 'angled'
    category = ('body' if body else 'middle' if middle else 'wide_angle' if wide_angle else geometric_line)
    reversing = ((dx * rs['momentum_x'] < -.015 and abs(dx_m) > .08)
                 or (dy * rs['momentum_y'] < -.015 and abs(dy_m) > .08))
    requested_wing = 'fh' if technique.startswith('fh_') else 'bh' if technique.startswith('bh_') else None
    step_around = requested_wing == 'fh' and hitter_side == 'bh'
    cross_body = requested_wing is not None and hitter_side in ('fh', 'bh') and requested_wing != hitter_side
    cross_step = abs(dx_m) > .65 or reversing and abs(dx_m) > .45
    recovery_pressure = min(1., (1 - rs['recovery']) * .35 + min(distance / 2.4, .5)
                            + .18 * reversing + min(rs['movement_load'] / 300., .17))
    hitter_recovery_pressure = min(1., (1 - hs['recovery']) * .65 + abs(hs['x']) * .15 + .20 * step_around)
    return dict(
        coordinate_system='ABSOLUTE_HALF_TABLE_XY',
        mapping_resolved=hitter_hand != 'unknown' and receiver_hand != 'unknown',
        hitter_hand=hitter_hand, receiver_hand=receiver_hand,
        hitter_end=hitter_end, receiver_end=receiver_end,
        incoming=incoming, target=target, incoming_contact=hc, receiver_contact=rc,
        hitter_side=hitter_side,
        hitter_table_side=point_to_lane(incoming, hitter_hand, hitter_end),
        receiver_side=contact_side, receiver_table_side=table_side, receiver_contact_side=contact_side,
        delta=dict(x=dx, y=dy), delta_m=dict(x=dx_m, y=dy_m), distance_m=distance,
        lateral_distance_m=abs(dx_m), depth_distance_m=abs(dy_m),
        forward_distance_m=max(0., forward), backward_distance_m=max(0., -forward),
        direction=direction, lateral_direction=lateral_direction, depth_direction=depth_direction,
        body=body, middle=middle, wide=wide, wide_angle=wide_angle,
        crosscourt=crosscourt, straight=straight,
        line_category=category, geometric_line=geometric_line,
        angle_degrees=math.degrees(math.atan2(abs(span_x) * HALF_WIDTH_M, abs(span_y) * HALF_LENGTH_M)),
        step_around=step_around, cross_body=cross_body, cross_step=cross_step,
        needs_recovery=hs['recovery'] < .85 or step_around,
        reversing=reversing, movement_load=rs['movement_load'],
        recovery_pressure=recovery_pressure, hitter_recovery_pressure=hitter_recovery_pressure,
        next_ball_pressure=recovery_pressure,
        hitter_move_distance_m=_distance(hc, hs), technique=technique)
