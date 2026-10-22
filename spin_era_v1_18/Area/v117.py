"""Bounded V1.1.7 era/calendar adapter, ending with the 2028 Olympic window.

The archive supplies champion-year anchors and a synthetic schedule generator,
not complete verified 2025/2026 calendars. Forward templates reuse that declared
structure. They never reconstruct official dates, qualification or champions.
Legacy Area functions and their global year sets are left unchanged.
"""
from __future__ import annotations

import copy
from datetime import date
import json
from types import FunctionType

import Area as legacy
from common import ROOT

VERSION = 'V1.1.7-AREA-1'
HORIZON_START = '2000-01-01'
HORIZON_END = '2028-07-30'
OLYMPIC_WINDOW_2028 = ('2028-07-16', '2028-07-29')


def _original(name):
    return getattr(legacy, '_legacy_' + name, getattr(legacy, name))


_BASE_ERA = _original('get_era')
_BASE_CALENDAR = _original('calendar_for_year')
_BASE_VALIDATOR = _original('validate_calendar')
_BASE_ENTRY = _original('check_entry')


def _bound_function(original, bindings):
    """Reuse frozen preflight code with local bindings, never a global patch."""
    namespace = dict(original.__globals__)
    namespace.update(bindings)
    function = FunctionType(original.__code__, namespace, original.__name__,
                            original.__defaults__, original.__closure__)
    function.__kwdefaults__ = copy.copy(original.__kwdefaults__)
    return function


_FORWARD_VALIDATOR = _bound_function(_BASE_VALIDATOR, dict(
    OLYMPIC_YEARS=set(legacy.OLYMPIC_YEARS) | {2028},
    SINGLES_WORLDS=set(legacy.SINGLES_WORLDS) | {2027},
    TEAM_WORLDS=set(legacy.TEAM_WORLDS) | {2028},
    INDIVIDUAL_CUPS=set(legacy.INDIVIDUAL_CUPS) | {2027, 2028}))


def ensure_date(value):
    """Return an ISO date in the playable interval; reject rather than clamp."""
    if isinstance(value, str):
        try:
            day = date.fromisoformat(value)
        except ValueError as error:
            raise ValueError('a valid ISO date is required') from error
    elif type(value) is date:
        day = value
    else:
        raise ValueError('a date or ISO date string is required')
    if not date.fromisoformat(HORIZON_START) <= day <= date.fromisoformat(HORIZON_END):
        raise ValueError(f'TIMELINE_OUTSIDE_HORIZON:{HORIZON_START}..{HORIZON_END}')
    return day.isoformat()


def _year(year):
    if type(year) is not int or not 2000 <= year <= 2028:
        raise ValueError('V1.1.7 calendar/era support is 2000..2028 Olympic cutoff')
    return year


def get_era(year):
    """Carry forward the last supplied design context, explicitly as a forecast."""
    _year(year)
    result = copy.deepcopy(_BASE_ERA(min(year, 2027)))
    result['requested_year'] = year
    result['career_horizon_end'] = HORIZON_END
    if year >= 2027:
        result.update(version=VERSION, source_era_id=result['era_id'],
            status='SIMULATED_FORWARD_NO_BUILT_ROSTER', classification='SIMULATED_FORWARD',
            end_year_exclusive=2029,
            scope='BOUNDED_FORWARD_DESIGN_CONTEXT_NOT_AUTOMATIC_NPC_EVOLUTION',
            provenance='LAST_SUPPLIED_ERA_CONTEXT_EXTENDED_AS_EXPLICIT_SANDBOX',
            note='No new historical roster or technical evolution is certified; play stops at the 2028 Olympic cutoff.')
    return result


def _forward_calendar(year):
    path = ROOT / 'data' / f'calendar_{year}_v117.json'
    if not path.is_file():
        raise RuntimeError(f'missing V1.1.7 forward calendar template: {path.name}')
    return json.loads(path.read_text())


def calendar_for_year(year, mode='sandbox'):
    _year(year)
    if mode not in ('sandbox', 'historical_reference'):
        raise ValueError('unknown calendar mode')
    if year <= 2026:
        result = copy.deepcopy(_BASE_CALENDAR(year, mode))
        result.update(version=VERSION, career_horizon_end=HORIZON_END)
        return result
    result = _forward_calendar(year)
    result['mode'] = mode
    if mode == 'historical_reference':
        # Future references cannot masquerade as reconstructed history. Keep
        # only explicitly unconfirmed planning records, without invented dates.
        result['classification'] = 'UNVERIFIED_FORWARD_PLANNING_REFERENCE'
        for event in result['events']:
            event.update(status='PLANNED', start_date=None, end_date=None, confirmed=False)
            event['note'] += ' Reference mode leaves the actual dates unconfirmed.'
    check = validate_calendar(result, year)
    if not check['valid']:
        raise RuntimeError(f'invalid packaged forward calendar: {check["errors"]}')
    return result


def validate_calendar(calendar, year=None):
    """Retain old discipline/entry guards, plus forward declarations and cutoff."""
    target = calendar.get('year') if isinstance(calendar, dict) and year is None else year
    if isinstance(calendar, dict) and type(target) is not int:
        # The preserved validator's year-set membership assumes a hashable
        # year after recording its type error. Reject malformed values first.
        return dict(valid=False, errors=['CALENDAR_YEAR_MISMATCH', 'CALENDAR_OUTSIDE_CAREER_HORIZON'],
                    warnings=[], coverage={}, publication_ready=False,
                    historical_calendar_verified=False, career_horizon_end=HORIZON_END)
    result = _FORWARD_VALIDATOR(calendar, year)
    errors = list(result['errors'])
    warnings = list(result['warnings'])
    if not isinstance(calendar, dict):
        return result
    target = calendar.get('year') if year is None else year
    if type(target) is not int or not 2000 <= target <= 2028:
        errors.append('CALENDAR_OUTSIDE_CAREER_HORIZON')
    if type(target) is int and target >= 2027 and calendar.get('mode') == 'historical_reference':
        warnings = [item for item in warnings if item != 'SOURCE_ANCHORS_ARE_REFERENCES_NOT_SIMULATED_TITLES']
        warnings.append('FORWARD_PLANS_ARE_NOT_HISTORICAL_RESULTS')
    if calendar.get('historical_calendar_verified') is True:
        errors.append('CALENDAR_CANNOT_SELF_CERTIFY_HISTORY')
    for event in calendar.get('events', []) if isinstance(calendar.get('events'), list) else []:
        if not isinstance(event, dict):
            continue
        eid = event.get('event_id')
        for key in ('start_date', 'end_date'):
            if event.get(key) is not None:
                try:
                    ensure_date(event[key])
                except (ValueError, TypeError):
                    errors.append(f'EVENT_OUTSIDE_CAREER_HORIZON:{eid}:{key}')
        if type(target) is int and target >= 2027:
            if event.get('future_schedule') is not True:
                errors.append(f'FORWARD_SCHEDULE_DECLARATION_REQUIRED:{eid}')
            if event.get('status') not in ('SIMULATED', 'PLANNED', 'CANCELLED'):
                errors.append(f'FORWARD_EVENT_MUST_BE_SIMULATED_OR_PLANNED:{eid}')
            if event.get('historical_schedule_verified') is True:
                errors.append(f'FORWARD_EVENT_CANNOT_SELF_CERTIFY_HISTORY:{eid}')
            warnings.append(f'FORWARD_DATES_NOT_OFFICIALLY_VERIFIED:{eid}')
    result.update(valid=not errors, errors=list(dict.fromkeys(errors)),
                  warnings=list(dict.fromkeys(warnings)), historical_calendar_verified=False,
                  career_horizon_end=HORIZON_END)
    result['publication_ready'] = result['valid'] and not result['warnings']
    return result


_FORWARD_ENTRY = _bound_function(_BASE_ENTRY, dict(validate_calendar=validate_calendar))


def check_entry(calendar, event_id, player, existing_entries=()):
    """Use the same age/region/conflict logic with the new bounded validator."""
    return _FORWARD_ENTRY(calendar, event_id, player, existing_entries)
