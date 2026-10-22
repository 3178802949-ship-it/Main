"""V1.1.7 综合版 era context and conservative source-time boundaries.

Calendar dates remain the explicit V1.1.7 sandbox plan. New functions check
declared dates and separate historical knowledge from out-of-world design
material; they do not authenticate a source or invent equipment chronologies.
"""
from __future__ import annotations

import copy
from datetime import date

from Area import v117 as previous

VERSION = 'V1.1.7-COMPREHENSIVE-AREA-1'
HORIZON_START = previous.HORIZON_START
HORIZON_END = previous.HORIZON_END
OLYMPIC_WINDOW_2028 = previous.OLYMPIC_WINDOW_2028
ensure_date = previous.ensure_date
validate_calendar = previous.validate_calendar
check_entry = previous.check_entry


def _asof(value):
    if type(value) is int:
        if not 2000 <= value <= 2028:
            raise ValueError('era context year must be 2000..2028')
        day = min(date(value, 12, 31), date.fromisoformat(HORIZON_END))
        return day, 'YEAR_END'
    return date.fromisoformat(ensure_date(value)), 'DAY'


def get_era(year):
    result = previous.get_era(year)
    result['context_version'] = VERSION
    result['source_policy'] = 'DATED_FACTS_OR_EXPLICIT_OUT_OF_WORLD_DESIGN_PRIOR'
    return result


def calendar_for_year(year, mode='sandbox'):
    result = previous.calendar_for_year(year, mode)
    result['context_version'] = VERSION
    return result


def context_for_date(value):
    day, precision = _asof(value)
    return dict(version=VERSION, as_of=day.isoformat(), temporal_precision=precision,
        era=get_era(day.year), horizon_end=HORIZON_END,
        source_policy='NO_FUTURE_SOURCE_AS_IN_WORLD_KNOWLEDGE',
        calendar_accuracy='SIMULATION_TEMPLATE_NOT_VERIFIED_COMPLETE_HISTORY')


def _source_date(source):
    # Exact dates outrank a publication year. Invalid explicit dates do not
    # fall back to a convenient earlier year.
    for key in ('source_date', 'publication_date', 'available_from', 'date'):
        value = source.get(key)
        if value is not None:
            if not isinstance(value, str):
                raise ValueError('invalid source date')
            try:
                return date.fromisoformat(value), 'DAY'
            except ValueError as error:
                raise ValueError('invalid source date') from error
    for key in ('source_year', 'publication_year', 'year'):
        value = source.get(key)
        if value is not None:
            if type(value) is not int or not 1 <= value <= 9999:
                raise ValueError('invalid source year')
            return date(value, 12, 31), 'YEAR_END'
    return None, 'UNKNOWN'


def filter_temporal_sources(sources, as_of, *, allow_design_priors=False):
    """Partition declared sources; late/undated material is never known fact.

    An explicit design-prior option may retain late or undated material for the
    author. It remains labelled outside the character's historical knowledge.
    A dated source merely being available does not authenticate its contents.
    """
    day, precision = _asof(as_of)
    if type(allow_design_priors) is not bool or not isinstance(sources, (list, tuple)):
        raise ValueError('sources must be a sequence and design-prior option boolean')
    available, design, excluded, warnings = [], [], [], []
    for index, raw in enumerate(sources):
        source_id = raw.get('source_id', raw.get('id', f'source:{index}')) if isinstance(raw, dict) else f'source:{index}'
        if not isinstance(raw, dict):
            excluded.append(dict(source_id=source_id, reason='MALFORMED_SOURCE'))
            warnings.append(f'MALFORMED_SOURCE:{source_id}')
            continue
        source = copy.deepcopy(raw)
        try:
            published, source_precision = _source_date(source)
        except ValueError:
            excluded.append(dict(source_id=source_id, reason='INVALID_DECLARED_DATE'))
            warnings.append(f'INVALID_SOURCE_DATE:{source_id}')
            continue
        if published is not None and published <= day:
            source.update(temporal_scope='AVAILABLE_BY_WORLD_DATE',
                availability_checked_through=day.isoformat(), temporal_precision=source_precision,
                authentication='DECLARED_DATE_ONLY_NOT_SOURCE_VERIFICATION')
            available.append(source)
            continue
        reason = 'UNDATED_SOURCE' if published is None else 'FUTURE_SOURCE'
        if allow_design_priors:
            source.update(temporal_scope='OUT_OF_WORLD_DESIGN_PRIOR',
                not_in_world_knowledge=True, reason=reason,
                availability_checked_through=day.isoformat())
            design.append(source)
        else:
            excluded.append(dict(source_id=source_id, reason=reason,
                declared_date=published.isoformat() if published else None))
        warnings.append(f'{reason}:{source_id}')
    return dict(version=VERSION, as_of=day.isoformat(), temporal_precision=precision,
        available=available, design_priors=design, excluded=excluded,
        warnings=list(dict.fromkeys(warnings)),
        validation_boundary='TEMPORAL_DECLARATIONS_NOT_HISTORICAL_AUTHENTICATION')


def validate_context(as_of, *, cards=(), sources=(), rule_items=(), allow_design_priors=False):
    """Validate snapshots and caller-supplied, evidenced chronology constraints.

    Rule items may declare ``verified_not_before`` only alongside a nonempty
    ``evidence_ref`` and ``constraint_status='SOURCE_EVIDENCED'``. This checks the
    declaration, not whether the reference was independently authenticated.
    Missing evidence produces a warning instead of a fabricated historical ban.
    """
    day, precision = _asof(as_of)
    if not isinstance(cards, (list, tuple)) or not isinstance(rule_items, (list, tuple)):
        raise ValueError('cards and rule items must be sequences')
    errors, warnings = [], []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            errors.append(f'MALFORMED_CARD:{index}')
            continue
        pid = card.get('player_id', f'card:{index}')
        year = card.get('year')
        if year is not None and (type(year) is not int or not 1 <= year <= 9999):
            errors.append(f'INVALID_SNAPSHOT_YEAR:{pid}')
        elif year is not None and year > day.year:
            errors.append(f'FUTURE_PLAYER_SNAPSHOT:{pid}')
        elif year is not None and year < day.year:
            warnings.append(f'OLDER_SNAPSHOT_IS_NOT_AUTOMATICALLY_GROWN:{pid}')
        snapshot = card.get('snapshot_date')
        if snapshot is not None:
            try:
                if not isinstance(snapshot, str):
                    raise ValueError('invalid date type')
                stamp = date.fromisoformat(snapshot)
                if stamp > day:
                    errors.append(f'FUTURE_PLAYER_SNAPSHOT_DATE:{pid}')
            except ValueError:
                errors.append(f'INVALID_SNAPSHOT_DATE:{pid}')
    for index, item in enumerate(rule_items):
        if not isinstance(item, dict):
            errors.append(f'MALFORMED_RULE_ITEM:{index}')
            continue
        label = item.get('id', f'item:{index}')
        evidence = item.get('evidence_ref')
        boundary = item.get('verified_not_before')
        if boundary is None or item.get('constraint_status') != 'SOURCE_EVIDENCED' or not isinstance(evidence, str) or not evidence.strip():
            warnings.append(f'UNVERIFIED_CHRONOLOGY_NO_AUTOMATIC_BAN:{label}')
            continue
        try:
            if not isinstance(boundary, str):
                raise ValueError('invalid date type')
            first = date.fromisoformat(boundary)
            if first > day:
                errors.append(f'BEFORE_DECLARED_RULE_AVAILABILITY:{label}')
        except ValueError:
            errors.append(f'INVALID_RULE_ITEM_DATE:{label}')
    partition = filter_temporal_sources(sources, day.isoformat(), allow_design_priors=allow_design_priors)
    warnings.extend(partition['warnings'])
    return dict(valid=not errors, errors=list(dict.fromkeys(errors)),
        warnings=list(dict.fromkeys(warnings)), version=VERSION, as_of=day.isoformat(),
        temporal_precision=precision, source_partition=partition,
        validation_boundary='DECLARED_DATE_CHECKS_NOT_OFFICIAL_ERA_AUTHENTICATION',
        complete_real_2025_2026_calendars_present=False, horizon_end=HORIZON_END)
