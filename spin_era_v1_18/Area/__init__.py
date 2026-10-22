"""Era context, exact snapshot selection and auditable calendar preflight.

Calendar schema: {year:int, mode:'sandbox'|'historical_reference', complete:bool,
events:[{event_id,name,category:'grand'|'major'|'continental'|'other',level,kind,
start_date,end_date,status,provenance,region,min_age,max_age,confirmed}]}. Dates are ISO
dates or null for unconfirmed references. A structurally valid calendar need not
be publication-ready. No dates, champions, ranking eligibility or NPC development
are invented from missing historical information.
"""
from __future__ import annotations

import copy
from datetime import date
import json

from common import ROOT
import era_lcm_v11 as legacy
import ranking_v112 as ranking

VERSION = 'V1.1.6-AREA-CANDIDATE'
REGIONS = ('Asia', 'Europe', 'Americas', 'Africa', 'Oceania', 'WORLD')
OLYMPIC_YEARS = {2000, 2004, 2008, 2012, 2016, 2021, 2024}
SINGLES_WORLDS = set(range(2001, 2026, 2))
TEAM_WORLDS = {2000, 2001, 2004, 2006, 2008, 2010, 2012, 2014, 2016, 2018, 2022, 2024, 2026}
INDIVIDUAL_CUPS = set(range(2000, 2021)) | {2024, 2025, 2026}
COUNTRY_REGIONS = {
    '中国': 'Asia', '中国台北': 'Asia', '中国香港': 'Asia', '日本': 'Asia',
    '韩国': 'Asia', '印度': 'Asia', '埃及': 'Africa', '尼日利亚': 'Africa', '巴西': 'Americas',
    **dict.fromkeys(('丹麦', '俄罗斯', '克罗地亚', '奥地利', '希腊', '德国', '捷克',
                     '斯洛文尼亚', '比利时', '法国', '瑞典', '白俄罗斯', '罗马尼亚',
                     '葡萄牙', '西班牙'), 'Europe'),
}


def _catalog():
    return json.loads((ROOT / 'data/area_catalog.json').read_text())


def get_era(year):
    if type(year) is not int:
        raise ValueError('year must be an integer')
    for era in _catalog()['eras']:
        if era['start_year'] <= year < era['end_year_exclusive']:
            result = copy.deepcopy(era)
            result['requested_year'] = year
            result['scope'] = 'ERA_DESIGN_CONTEXT_NOT_AUTOMATIC_NPC_EVOLUTION'
            if year >= 2027:
                result['status'] = 'ASSESSMENT_FORWARD_NO_BUILT_ROSTER'
            return result
    raise ValueError('era outside supplied 2000..2027 context')


def _presets():
    path = ROOT / 'data/presets_normalized.json'
    if not path.is_file():
        raise RuntimeError('normalized preset catalog is not installed; include shared data package')
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        raise ValueError('invalid normalized preset catalog')
    for key in ('cards', 'profiles', 'presets'):
        if isinstance(data.get(key), list):
            return data[key]
    raise ValueError('invalid normalized preset catalog')


def list_presets(year=None, player_id=None):
    if year is not None and type(year) is not int:
        raise ValueError('year must be an integer')
    return copy.deepcopy([p for p in _presets()
        if (year is None or p.get('year') == year)
        and (player_id is None or p.get('player_id') == player_id)])


def get_preset(player_id, year, *, allow_prior=False):
    """Exact only by default. Prior snapshots require an explicit, labeled opt-in."""
    if type(year) is not int:
        raise ValueError('year must be an integer')
    choices = list_presets(player_id=player_id)
    exact = [p for p in choices if p.get('year') == year]
    if len(exact) > 1:
        raise ValueError('ambiguous exact preset identity')
    if exact:
        result = exact[0]
        result['selection'] = dict(requested_year=year, source_year=year, mode='EXACT_SNAPSHOT')
        return result
    prior = [p for p in choices if type(p.get('year')) is int and p['year'] <= year]
    if allow_prior and prior:
        selected_year = max(p['year'] for p in prior)
        selected = [p for p in prior if p['year'] == selected_year]
        if len(selected) != 1:
            raise ValueError('ambiguous prior preset identity')
        result = selected[0]
        result['selection'] = dict(requested_year=year, source_year=selected_year,
            mode='PRIOR_BASELINE_NOT_GROWN', warning='No intervening training, aging or historical results were settled.')
        return result
    raise KeyError(f'no exact snapshot for {player_id} in {year}; no future snapshot substituted')


def _anchor_events(year):
    source = json.loads((ROOT / 'data/original/spin_era_players_archive_2000_2026_v12.json').read_text())
    result = []
    for anchor in source['champion_anchors']:
        if anchor['year'] != year:
            continue
        kind = anchor['event_type']
        level = ('olympics' if kind == 'olympic_ms' else 'world_cup'
                 if kind == 'world_cup_ms' else 'world_championships')
        name = {'olympic_ms': '奥运会单打赛', 'world_cup_ms': '世界杯单打赛',
                'world_championship_ms': '世乒赛单打赛',
                'world_team_championship': '世乒赛团体赛'}[kind]
        result.append(dict(event_id=anchor['event_id'], name=name, source_event_type=kind, category='grand',
            level=level, kind='team' if kind == 'world_team_championship' else 'adult_singles',
            start_date=None, end_date=None, status='REFERENCE', region='WORLD',
            min_age=0, max_age=120, confirmed=False, provenance='SOURCE_ARCHIVE_UNVERIFIED',
            historical_reference=copy.deepcopy(anchor),
            note='Imported source reference only; dates and entry lists are not reconstructed. Never grants a simulated title.'))
    return result


def calendar_for_year(year, mode='sandbox'):
    if type(year) is not int or not 2000 <= year <= 2028:
        raise ValueError('calendar support is 2000..2028')
    if mode not in ('sandbox', 'historical_reference'):
        raise ValueError('unknown calendar mode')
    anchors = _anchor_events(year)
    result = dict(version=VERSION, year=year, mode=mode, complete=False,
        classification='SIMULATED' if mode == 'sandbox' else 'UNVERIFIED_REFERENCE',
        provenance_note='No verified full historical calendar is supplied. Ordinary major events have no mandatory annual station count.',
        events=[])
    if mode == 'historical_reference':
        result['events'] = anchors
        return result
    months = (2, 7, 11)
    for index, month in enumerate(months, 1):
        result['events'].append(dict(event_id=f'sandbox_major_{year}_{index:02}',
            name=f'普通大赛示例第{index}站（沙盒占位）', category='major',
            level='pro_tour_major', kind='adult_singles', region='WORLD',
            start_date=f'{year}-{month:02}-10', end_date=f'{year}-{month:02}-13',
            status='SIMULATED', provenance='SIMULATED_NOT_HISTORICAL', confirmed=False,
            min_age=0, max_age=120, placeholder=True))
    # Only dates are synthetic: the grand-event year/type guards remain in force.
    for index, anchor in enumerate(anchors):
        event = {k: copy.deepcopy(v) for k, v in anchor.items() if k != 'historical_reference'}
        event.update(event_id=f'sandbox_{anchor["event_id"]}',
            name=f'{anchor["name"]}（该年项目的沙盒赛程）',
            start_date=f'{year}-04-{4 + index * 5:02}', end_date=f'{year}-04-{6 + index * 5:02}',
            status='SIMULATED', provenance='SIMULATED_DATE_WITH_SOURCE_YEAR_TYPE',
            note='Event year/type follows supplied reference; dates and all simulated results are fictional.')
        if event['level'] == 'olympics' and year == 2021:
            event['nominal_year'] = 2020
        result['events'].append(event)
    result['events'].append(dict(event_id=f'sandbox_continental_asia_{year}',
        name='大型亚洲洲际赛候选（沙盒）', category='continental', level='continental',
        kind='adult_singles', region='Asia', start_date=f'{year}-12-10', end_date=f'{year}-12-13',
        status='SIMULATED', provenance='SIMULATED_NOT_HISTORICAL', confirmed=False,
        min_age=0, max_age=120, placeholder=True))
    return result


def _dates(event, errors, warnings):
    start, end = event.get('start_date'), event.get('end_date')
    if start is None and end is None and event.get('status') in ('REFERENCE', 'PLANNED'):
        warnings.append(f'DATE_UNCONFIRMED:{event.get("event_id")}')
        return None
    try:
        if not isinstance(start, str) or not isinstance(end, str):
            raise ValueError()
        a, b = date.fromisoformat(start), date.fromisoformat(end)
        if a > b:
            raise ValueError()
        return a, b
    except (ValueError, TypeError):
        errors.append(f'INVALID_DATE:{event.get("event_id")}')
        return None


def validate_calendar(calendar, year=None):
    """Structural and supplied-era checks. valid does not certify history or slots."""
    errors, warnings = [], []
    if not isinstance(calendar, dict):
        return dict(valid=False, errors=['INVALID_CALENDAR'], warnings=[], coverage={})
    target = calendar.get('year') if year is None else year
    if type(target) is not int or type(calendar.get('year')) is not int or target != calendar['year']:
        errors.append('CALENDAR_YEAR_MISMATCH')
    if calendar.get('mode') not in ('sandbox', 'historical_reference'):
        errors.append('INVALID_CALENDAR_MODE')
    if type(calendar.get('complete', False)) is not bool:
        errors.append('INVALID_COMPLETE_FLAG')
    events = calendar.get('events')
    if not isinstance(events, list):
        return dict(valid=False, errors=errors + ['EVENTS_MUST_BE_LIST'], warnings=[], coverage={})
    ids, major, grands = set(), [], []
    for event in events:
        if not isinstance(event, dict):
            errors.append('INVALID_EVENT')
            continue
        eid = event.get('event_id')
        if not isinstance(eid, str) or not eid:
            errors.append('MISSING_EVENT_ID')
        elif eid in ids:
            errors.append(f'DUPLICATE_EVENT_ID:{eid}')
        else:
            ids.add(eid)
        dates = _dates(event, errors, warnings)
        if dates and (dates[0].year != target or dates[1].year != target):
            errors.append(f'EVENT_YEAR_MISMATCH:{eid}')
        category, level, kind = event.get('category'), event.get('level'), event.get('kind')
        if category not in ('grand', 'major', 'continental', 'other'):
            errors.append(f'INVALID_CATEGORY:{eid}')
        if level not in ranking.LEVEL or kind not in ('adult_singles', 'youth_singles', 'team'):
            errors.append(f'INVALID_LEVEL_OR_KIND:{eid}')
        if event.get('status') not in ('SIMULATED', 'PLANNED', 'CANCELLED', 'REFERENCE'):
            errors.append(f'INVALID_STATUS:{eid}')
        if event.get('region') not in REGIONS:
            errors.append(f'INVALID_REGION:{eid}')
        if not isinstance(event.get('provenance'), str) or not event.get('provenance'):
            errors.append(f'MISSING_PROVENANCE:{eid}')
        if type(event.get('confirmed', False)) is not bool:
            errors.append(f'INVALID_CONFIRMATION_FLAG:{eid}')
        lo, hi = event.get('min_age', 0), event.get('max_age', 120)
        if type(lo) is not int or type(hi) is not int or not 0 <= lo <= hi <= 120:
            errors.append(f'INVALID_AGE_BAND:{eid}')
        if event.get('placeholder') or not event.get('confirmed', False):
            warnings.append(f'UNCONFIRMED_EVENT:{eid}')
        if isinstance(level, str) and level.startswith('wtt_'):
            if type(target) is int and target < 2021:
                errors.append(f'WTT_BEFORE_SUPPORTED_ERA:{eid}')
        if category == 'continental' and (level != 'continental' or event.get('region') == 'WORLD'):
            errors.append(f'CONTINENTAL_REGION_OR_LEVEL:{eid}')
        if level in ('olympics', 'world_championships', 'world_cup') and category != 'grand':
            errors.append(f'GRAND_LEVEL_REQUIRES_GRAND_CATEGORY:{eid}')
        if level == 'continental' and category != 'continental':
            errors.append(f'CONTINENTAL_LEVEL_REQUIRES_CONTINENTAL_CATEGORY:{eid}')
        if category == 'major':
            major.append(eid)
            if level in ('olympics', 'world_championships', 'world_cup', 'continental'):
                errors.append(f'MAJOR_LEVEL_COLLISION:{eid}')
        if category == 'grand':
            grands.append(eid)
            if kind == 'youth_singles':
                errors.append(f'YOUTH_EVENT_CANNOT_USE_SENIOR_GRAND_LEVEL:{eid}')
            if level not in ('olympics', 'world_championships', 'world_cup'):
                errors.append(f'GRAND_LEVEL_MISMATCH:{eid}')
            if level == 'olympics' and target not in OLYMPIC_YEARS:
                errors.append(f'OLYMPIC_YEAR_NOT_SUPPORTED:{eid}')
            if level == 'olympics' and target == 2021 and event.get('nominal_year') != 2020:
                errors.append(f'POSTPONED_OLYMPIC_NOMINAL_YEAR_REQUIRED:{eid}')
            if level == 'olympics' and kind == 'team' and type(target) is int and target < 2008:
                errors.append(f'OLYMPIC_TEAM_BEFORE_2008:{eid}')
            if level == 'world_championships':
                allowed = TEAM_WORLDS if kind == 'team' else SINGLES_WORLDS
                if target not in allowed:
                    errors.append(f'WORLDS_DISCIPLINE_YEAR_MISMATCH:{eid}')
            if level == 'world_cup' and kind in ('adult_singles', 'youth_singles') and target not in INDIVIDUAL_CUPS:
                errors.append(f'INDIVIDUAL_CUP_YEAR_NOT_SUPPORTED:{eid}')
            if level == 'world_cup' and kind == 'team':
                warnings.append(f'TEAM_CUP_CALENDAR_NOT_RECONSTRUCTED:{eid}')
    if not calendar.get('complete'):
        warnings.append('FULL_CALENDAR_NOT_CERTIFIED')
    if calendar.get('mode') == 'historical_reference':
        warnings.append('SOURCE_ANCHORS_ARE_REFERENCES_NOT_SIMULATED_TITLES')
    coverage = dict(events=len(events), grand_events=len(grands), major_events=len(major),
                    continental_events=sum(isinstance(e, dict) and e.get('category') == 'continental' for e in events))
    return dict(valid=not errors, errors=errors, warnings=warnings, coverage=coverage,
                publication_ready=not errors and not warnings, historical_calendar_verified=False)


def check_entry(calendar, event_id, player, existing_entries=()):
    """Eligibility preflight only: quotas, selection and full rosters remain external."""
    validation = validate_calendar(calendar)
    errors, warnings = list(validation['errors']), []
    if not isinstance(calendar, dict):
        return dict(eligible=False, errors=errors, warnings=warnings)
    if errors:
        return dict(eligible=False, errors=errors, warnings=list(validation['warnings']),
                    scope='STRUCTURAL_PRECHECK_ONLY', official_qualification_confirmed=False)
    matches = [e for e in calendar.get('events', []) if isinstance(e, dict) and e.get('event_id') == event_id]
    if len(matches) != 1:
        return dict(eligible=False, errors=errors + ['EVENT_NOT_UNIQUE_OR_MISSING'], warnings=warnings)
    event = matches[0]
    dates = _dates(event, errors, warnings)
    if not dates:
        errors.append('ENTRY_DATE_NOT_CONFIRMED')
    if event.get('status') in ('CANCELLED', 'REFERENCE'):
        errors.append('EVENT_NOT_OPEN_FOR_SIMULATED_ENTRY')
    if event.get('status') == 'PLANNED' or not event.get('confirmed', False):
        warnings.append('EVENT_REQUIRES_CONFIRMATION_BEFORE_FORMAL_ENTRY')
    if not isinstance(player, dict):
        errors.append('INVALID_PLAYER')
        player = {}
    age = player.get('age', player.get('age_approx'))
    birth = player.get('birth_year')
    birthday = player.get('birth_date', player.get('date_of_birth'))
    if birthday is not None and dates:
        try:
            dob = date.fromisoformat(birthday)
            age = dates[0].year - dob.year - ((dates[0].month, dates[0].day) < (dob.month, dob.day))
        except (ValueError, TypeError):
            errors.append('INVALID_BIRTH_DATE')
            age = None
    elif type(birth) is int and type(calendar.get('year')) is int:
        age = calendar['year'] - birth
        warnings.append('AGE_USES_BIRTH_YEAR_NOT_EXACT_BIRTHDAY')
        if age == event.get('min_age', 0) and age > 0 or age == event.get('max_age', 120) and age < 120:
            errors.append('AGE_CUTOFF_REQUIRES_EXACT_BIRTHDAY')
    if type(age) not in (int, float) or not 0 <= age <= 120:
        errors.append('PLAYER_AGE_REQUIRED')
    elif not event.get('min_age', 0) <= age <= event.get('max_age', 120):
        errors.append('AGE_INELIGIBLE')
    region = player.get('region') or COUNTRY_REGIONS.get(player.get('nation_prototype', player.get('nation')))
    if event.get('region') != 'WORLD':
        if region is None:
            errors.append('REGION_REQUIRED')
        elif region != event['region']:
            errors.append('CONTINENT_INELIGIBLE')
    pid = player.get('player_id', player.get('id'))
    by_id = {e['event_id']: e for e in calendar.get('events', []) if isinstance(e, dict) and isinstance(e.get('event_id'), str)}
    for existing in existing_entries:
        if isinstance(existing, dict) and existing.get('player_id', pid) != pid:
            continue
        old_id = existing.get('event_id') if isinstance(existing, dict) else existing
        if not isinstance(old_id, str) or not old_id:
            errors.append('INVALID_EXISTING_ENTRY')
            continue
        if old_id == event_id:
            errors.append('DUPLICATE_ENTRY')
            continue
        previous = by_id.get(old_id)
        if previous is None:
            warnings.append(f'EXISTING_ENTRY_NOT_IN_CALENDAR:{old_id}')
            continue
        old_dates = _dates(previous, errors, warnings)
        if dates and old_dates and dates[0] <= old_dates[1] and old_dates[0] <= dates[1]:
            errors.append(f'ENTRY_DATE_CONFLICT:{old_id}')
    warnings.append('PRECHECK_ONLY_NO_QUOTA_OR_WORLD_RANK_QUALIFICATION_PROOF')
    return dict(eligible=not errors, errors=errors, warnings=warnings, event_id=event_id,
                scope='STRUCTURAL_PRECHECK_ONLY', official_qualification_confirmed=False)

