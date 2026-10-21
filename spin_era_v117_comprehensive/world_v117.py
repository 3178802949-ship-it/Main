"""V1.1.7 finite-horizon career world with shared time and compact match ledgers.

Legacy worlds are never converted here. Transactions clone only current actors
and small append-only indexes; full shot logs are optional external artifacts.
"""
from __future__ import annotations

from collections import Counter
import calendar as month_calendar
import copy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import Card
import Game
from Area import v117 as Area
from Training import v117 as Training
from common import canonical_json
import career_v116 as legacy_career
import career_v117 as career

VERSION = 'SPIN_ERA_V1.1.7_CANDIDATE_1'
RULESET = 'V1.1.7-CANDIDATE-1'
PHASE_DAYS = 15
FULL_TRAINING_DAYS = 10
MAX_COMPETITION_FATIGUE = 90

# Explicit compatibility boundary: numerical/runtime dependencies and the data
# used for snapshots, era context and future schedules. Documentation, reports,
# experiments and checkout location deliberately do not affect continuation.
FINGERPRINT_FILES = (
    'world_v117.py', 'common/__init__.py', 'Card/__init__.py',
    'Training/__init__.py', 'Training/v117.py', 'Area/__init__.py', 'Area/v117.py',
    'Game/__init__.py', 'Game/worker.py', 'Game/engine_v117.py', 'Game/light_v117.py',
    'Game/tactics_v117.py', 'Game/integration_v117.py', 'Game/geometry.py',
    'Game/observed_tactics.py', 'Game/specialist_engine.py',
    'runtime/card_training_v112.py', 'runtime/career_v114.py', 'runtime/career_v115.py',
    'runtime/career_v116.py', 'runtime/career_v117.py', 'runtime/ranking_v112.py',
    'runtime/era_lcm_v11.py', 'runtime/game_v112.py', 'runtime/game_v113.py',
    'runtime/game_v114.py', 'runtime/game_v115.py', 'runtime/tactical_match_v116.py',
    'runtime/specialist_rubber_v116.py', 'data/area_catalog.json',
    'data/presets_normalized.json', 'data/original/spin_era_v013_frozen_attribute_schema.json',
    'data/original/spin_era_players_archive_2000_2026_v12.json',
    'data/calendar_2027_v117.json', 'data/calendar_2028_v117.json',
)


def _hash(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def ruleset_fingerprint():
    """Bind a checkpoint to a fixed, location-independent code/data set."""
    root = Path(__file__).resolve().parent
    files = {}
    for relative in FINGERPRINT_FILES:
        try:
            files[relative] = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        except OSError as error:
            raise ValueError(f'WORLD_RULESET_DEPENDENCY_MISSING:{relative}') from error
    return dict(algorithm='SHA256_FIXED_FILES_V117_1', ruleset=RULESET,
                sha256=_hash(files), files=files)


def _check_fingerprint(data):
    recorded, current = data.get('ruleset_fingerprint'), ruleset_fingerprint()
    if recorded != current:
        prior_files = recorded.get('files', {}) if isinstance(recorded, dict) else {}
        differences = sorted(path for path in set(prior_files) | set(current['files'])
                             if prior_files.get(path) != current['files'].get(path))
        raise ValueError('WORLD_RULESET_FINGERPRINT_MISMATCH:' + ','.join(differences or ['manifest'])
                         + '; restore the checkpoint\'s original code/data before continuation')


def _period(base, month, phase=0):
    start = date.fromisoformat(base)
    ordinal = start.year * 12 + start.month - 1 + month
    return date(ordinal // 12, ordinal % 12 + 1, 16 if phase else 1)


def _clock(state):
    return state['month'], state['training_release']['phase']


def _phase_end(base, state):
    start = _period(base, *_clock(state))
    end = date(start.year, start.month, 15 if start.day == 1 else month_calendar.monthrange(start.year, start.month)[1])
    return min(end, date.fromisoformat(Area.HORIZON_END))


def _activity(state):
    return dict(month=state['month'], phase=state['training_release']['phase'],
                competition_days=0, match_count=0, effort=0., movement_m=0.,
                last_match_date=None, last_competition_day=None)


class WorldSession:
    def __init__(self, data, artifacts=None):
        self.data = data
        self.artifacts = {} if artifacts is None else artifacts

    @classmethod
    def create(cls, cards, year, *, start_date=None, world_id='career-v117', seed=117,
               main_player_id=None, calendar=None, mode='sandbox', game_ruleset=RULESET):
        if type(year) is not int or type(seed) is not int or not isinstance(world_id, str) or not world_id:
            raise ValueError('explicit year, integer seed and world identity required')
        if mode not in ('sandbox', 'historical_reference') or game_ruleset not in (None, RULESET):
            raise ValueError('unsupported V1.1.7 world configuration')
        start = date.fromisoformat(start_date or f'{year}-01-01')
        Area.ensure_date(start.isoformat())
        if start.year != year or start.day != 1:
            raise ValueError('start must be the first day of a month in the selected year')
        normalized = []
        for raw in cards:
            source = Card.normalize(raw)
            if source.get('year', year) > year or (source.get('snapshot_date') and date.fromisoformat(source['snapshot_date']) > start):
                raise ValueError('future card evidence cannot enter an earlier world')
            if source.get('year', year) < year and (source.get('selection', {}).get('mode') != 'PRIOR_BASELINE_NOT_GROWN' or 'model_start_age' not in source):
                raise ValueError('older snapshot needs an explicit prior baseline and model_start_age')
            age = source.get('model_start_age', source.get('age_approx', source.get('age', 18)))
            if type(source.get('birth_year')) is int and abs(year - source['birth_year'] - age) > 1:
                raise ValueError('model age conflicts with birth-year evidence')
            normalized.append(career.prepare_card(source, seed=seed))
        ids = [c['player_id'] for c in normalized]
        people = [c['player_id'] if c.get('source_prototype') == 'SYNTHETIC'
                  else c.get('source_person_id', c['player_id'].removesuffix('_age18')) for c in normalized]
        if not ids or len(set(ids)) != len(ids) or len(set(people)) != len(people):
            raise ValueError('one contemporary card per participant and source person required')
        main_player_id = main_player_id or ids[0]
        if main_player_id not in ids:
            raise ValueError('main player is not loaded')
        cal = copy.deepcopy(calendar or Area.calendar_for_year(year, mode))
        check = Area.validate_calendar(cal, year)
        if not check['valid']:
            raise ValueError(f'invalid calendar: {check["errors"]}')
        book, states, resources = Card.RankingBook(), {}, {}
        for card in normalized:
            pid = card['player_id']
            book.register_player(pid)
            states[pid] = Training.initialize(card, seed=legacy_career.rng_for(seed, 'world-player', pid).randint(1, 2**31 - 1),
                curve=card.get('growth_curve', 'balanced_progress'),
                start_age=card.get('model_start_age', card.get('age_approx', card.get('age', 18))))
            setup = card.get('career_resources', {})
            units = setup.get('investment_units', 12)
            if type(units) is not int or not 0 <= units <= 48:
                raise ValueError('starting investment units must be an integer in 0..48')
            resources[pid] = dict(year=year, investment_units=units,
                national_eligible=setup.get('national_eligible', False) is True,
                frontier_tokens=0, reward_tokens_granted=0, championship_windows=0,
                paid_camp_until=0,
                provenance='EXPLICIT_START_CONFIGURATION' if setup else 'STANDARD_CLUB_START')
        data = dict(version=VERSION, game_ruleset=RULESET, world_id=world_id, mode=mode,
            ruleset_fingerprint=ruleset_fingerprint(),
            classification='SIMULATED', seed=seed, base_date=start.isoformat(), current_date=start.isoformat(),
            main_player_id=main_player_id, horizon_end=Area.HORIZON_END, completed=False,
            calendar=cal, era=Area.get_era(year), calendar_archive=[],
            metadata={c['player_id']: c for c in normalized}, players=states,
            activity={pid: _activity(s) for pid, s in states.items()}, resources=resources,
            ranking=book.snapshot(), matches={}, match_meta={}, events={}, entries=[], titles=[],
            audit_chain=[], audit_head='0' * 64, complete_roster=False,
            archive_policy='COMPACT_CHECKPOINT_EXTERNAL_OPTIONAL_FULL_LOGS')
        result = cls(data)
        result.consistency_check(deep=True)
        return result

    def _fork(self, players=()):
        data = dict(self.data)
        for key in ('players', 'activity', 'resources', 'matches', 'match_meta', 'events'):
            data[key] = dict(self.data[key])
        for key in ('titles', 'entries', 'audit_chain', 'calendar_archive'):
            data[key] = list(self.data[key])
        for pid in players:
            data['players'][pid] = copy.deepcopy(self.data['players'][pid])
            data['activity'][pid] = dict(self.data['activity'][pid])
            data['resources'][pid] = dict(self.data['resources'][pid])
        return WorldSession(data, dict(self.artifacts))

    def _writable(self, *, catchup=None):
        if self.data['mode'] != 'sandbox':
            raise ValueError('historical reference mode is read-only')
        if self.data['completed']:
            primary = self.data['players'][self.data['main_player_id']]
            if catchup is None or _clock(self.data['players'][catchup]) >= _clock(primary):
                raise ValueError('career horizon reached at the 2028 Olympic cutoff')

    def _new_id(self, event_id, *, calendar_event=False):
        if not isinstance(event_id, str) or not event_id:
            raise ValueError('nonempty event identity required')
        if event_id in self.data['events'] or event_id in self.data['matches']:
            raise ValueError('DUPLICATE_WORLD_EVENT')
        if not calendar_event and event_id in {e['event_id'] for e in self.data['calendar']['events']}:
            raise ValueError('identity is reserved for a calendar competition')

    def _record(self, kind, event_id, payload):
        entry = dict(sequence=len(self.data['audit_chain']), kind=kind, id=event_id,
                     payload_sha256=_hash(payload), previous=self.data['audit_head'])
        entry['sha256'] = _hash(entry)
        self.data['audit_chain'].append(entry)
        self.data['audit_head'] = entry['sha256']

    def _commit(self, proposed):
        proposed.consistency_check()
        self.data, self.artifacts = proposed.data, proposed.artifacts

    def _resource_year(self, pid):
        state = self.data['players'][pid]
        year = _period(self.data['base_date'], *_clock(state)).year
        value = self.data['resources'][pid]
        if value['year'] != year:
            value.update(year=year, investment_units=min(24, value['investment_units'] + 12),
                         frontier_tokens=0, reward_tokens_granted=0, championship_windows=0)
        return value

    def card(self, player_id):
        state = self.data['players'][player_id]
        value = copy.deepcopy(self.data['metadata'][player_id])
        performance = Training.performance_card(state)
        value.update(copy.deepcopy(performance))
        for key in ('PA', 'pa_range', 'learning_factor', 'style_preference', 'xp', 'permits', 'P_xp', 'fatigue', 'injuries', 'cap_bonus'):
            if key in state:
                value[key] = copy.deepcopy(state[key])
        value.update(age_approx=state['start_age'] + (state['month'] + state['training_release']['phase'] / 2) / 12,
                     world_id=self.data['world_id'], classification='SIMULATED',
                     training_clock=dict(month=state['month'], phase=state['training_release']['phase']),
                     career_resources=dict(self.data['resources'][player_id]),
                     phase_activity=dict(self.data['activity'][player_id]))
        value['age'] = value['age_approx']
        value['development_profile'] = dict(body_max=state['P_max'], talent=state['talent'], neuromotor=state['neuromotor'],
            mental=state['mental'], focus=state['focus'], body_maturation_rate=state['body_maturation_rate'], classification='SIMULATED_DEVELOPMENT_STATE')
        value['ranking'] = copy.deepcopy(self.data['ranking']['players'][player_id])
        ranks = self.rankings()
        value['ranking_state'] = dict(asof=self.data['current_date'], scope=ranks['scope'],
            **next(row for row in ranks['standings'] if row['player_id'] == player_id),
            youth_elo=value['ranking']['youth_elo'], points_system=ranks['points_system'],
            uncalibrated_specialist_summary=ranks['uncalibrated_specialist_summary'],
            uncalibrated_specialist_summary_event_ids=list(ranks['uncalibrated_specialist_summary_event_ids']))
        value['simulated_career'] = dict(titles=[t for t in self.data['titles'] if t['player_id'] == player_id],
            matches=[mid for mid, m in self.data['matches'].items() if player_id in m['participant_ids']], classification='SIMULATED')
        return Card.recompute(value)

    def rankings(self, complete_pool=False):
        if complete_pool and not self.data['complete_roster']:
            raise ValueError('world has no declared complete ranking pool')
        result = Card.RankingBook.from_snapshot(self.data['ranking']).world_ranking(
            self.data['current_date'], list(self.data['players']), complete_pool=complete_pool)
        experimental = sorted(eid for eid, event in self.data['events'].items()
            if event.get('type') == 'completed_tournament'
            and event.get('calibration_status') == 'UNCALIBRATED'
            and event.get('experimental_scope') == 'SPECIALIST_SUMMARY')
        result['uncalibrated_specialist_summary'] = bool(experimental)
        result['uncalibrated_specialist_summary_event_ids'] = experimental
        return result

    def _match_card(self, player_id):
        """Project current playing attributes without transmitting career ledgers.

        PA, training banks, titles, ranking history and future potential never
        enter Game. Hand/equipment/tactics remain explicit rather than inferred.
        """
        performance = Training.performance_card(self.data['players'][player_id])
        value = {key: copy.deepcopy(performance[key]) for key in
                 ('player_id', 'children', 'P6', 'G9', 'CA', 'body_limitations', 'ca_semantics')}
        metadata = self.data['metadata'][player_id]
        for key in ('style', 'hand', 'handedness', 'rubbers', 'rubber', 'fh_rubber', 'bh_rubber',
                    'rubber_fh', 'rubber_bh', 'equipment', 'experimental_anti_spin',
                    'tactical_family', 'tactical_plan'):
            if key in metadata:
                value[key] = copy.deepcopy(metadata[key])
        return value

    def set_calendar(self, calendar):
        self._writable()
        year = date.fromisoformat(self.data['current_date']).year
        check = Area.validate_calendar(calendar, year)
        if not check['valid']:
            raise ValueError(f'calendar preflight failed: {check["errors"]}')
        replacements = {e['event_id']: e for e in calendar['events']}
        for old in self.data['calendar']['events']:
            if old['event_id'] in self.data['events'] and self.data['calendar']['year'] == year and replacements.get(old['event_id']) != old:
                raise ValueError('completed calendar entries are immutable')
        for event in calendar['events']:
            existing = self.data['events'].get(event['event_id'])
            if event['event_id'] in self.data['matches'] or existing and existing.get('type') != 'completed_tournament':
                raise ValueError('calendar identity collides with existing activity')
        proposed = self._fork()
        proposed.data['calendar_archive'].append(dict(year=self.data['calendar']['year'], sha256=_hash(self.data['calendar'])))
        proposed.data['calendar'] = copy.deepcopy(calendar)
        proposed.data['era'] = Area.get_era(year)
        self._commit(proposed)
        return check

    def confirm_sandbox_event(self, event_id):
        self._writable()
        if event_id in self.data['events']:
            raise ValueError('completed event cannot be reconfigured')
        found = [e for e in self.data['calendar']['events'] if e['event_id'] == event_id]
        if len(found) != 1 or found[0]['status'] != 'SIMULATED':
            raise ValueError('only explicit simulated events can be confirmed')
        proposed = self._fork()
        proposed.data['calendar'] = copy.deepcopy(self.data['calendar'])
        event = next(e for e in proposed.data['calendar']['events'] if e['event_id'] == event_id)
        event.update(confirmed=True, confirmation_scope='THIS_SANDBOX_ONLY_NOT_REAL_HISTORY')
        self._commit(proposed)
        return copy.deepcopy(event)

    def _check_actor(self, pid, *, in_event=False):
        if pid not in self.data['players']:
            raise ValueError('participant is not loaded')
        state = self.data['players'][pid]
        primary = self.data['players'][self.data['main_player_id']]
        if _clock(state) != _clock(primary):
            raise ValueError('participants must share the current world phase')
        if state['month'] < state.get('rehab_until', 0):
            raise ValueError('rehabilitation prohibits competition')
        if not in_event and state['fatigue'] >= MAX_COMPETITION_FATIGUE:
            raise ValueError('fatigue requires rest before further competition')

    def _effort(self, log, index):
        evidence = log.get('fatigue_cost_evidence', {})
        items = evidence.get('per_player', [])
        if len(items) != 2:
            raise ValueError('V1.1.7 match must supply per-player effort evidence')
        value = items[index]
        return float(value['effort']), float(value.get('movement_m', value.get('estimated_movement_m', 0)))

    def _injury_chance(self, pid, source_id, effort=0.):
        state = self.data['players'][pid]
        if state['month'] < state.get('rehab_until', 0):
            return None
        probability = min(.065, .001 + max(0., state['fatigue'] - 55) * .0008 + max(0., effort - 250) * .000025)
        rng = legacy_career.rng_for(self.data['seed'], 'world-health', source_id, pid)
        draw = rng.random()
        if draw >= probability:
            return dict(probability=probability, draw=draw, occurred=False)
        severity = rng.choices((1, 2, 3), (7, 2, 1))[0]
        injury_id = f'injury:{source_id}:{pid}'
        entry = career.injury(state, injury_id, state['month'], severity=severity)
        record = dict(type='injury', player_id=pid, source_id=source_id, probability=probability, draw=draw, receipt=entry)
        self.data['events'][injury_id] = record
        self._record('event', injury_id, record)
        return dict(probability=probability, draw=draw, occurred=True, injury_id=injury_id, severity=severity)

    def _play(self, a, b, match_id, seed, *, detail_level='summary', event_id=None, when=None, kind='adult_singles', charge_day=True):
        self._new_id(match_id)
        if a == b or type(seed) is not int or detail_level not in ('summary', 'full'):
            raise ValueError('distinct actors, integer seed and explicit detail mode required')
        for pid in (a, b):
            self._check_actor(pid, in_event=event_id is not None)
        day = date.fromisoformat(when or self.data['current_date'])
        Area.ensure_date(day.isoformat())
        for pid in (a, b):
            activity = self.data['activity'][pid]
            unavailable = activity.get('last_competition_day') or activity['last_match_date']
            if charge_day and unavailable:
                day = max(day, date.fromisoformat(unavailable) + timedelta(days=1))
        if day > _phase_end(self.data['base_date'], self.data['players'][a]):
            raise ValueError('no competition day remains in this half-month')
        if any(self.data['activity'][p]['competition_days'] + int(charge_day) > PHASE_DAYS for p in (a, b)):
            raise ValueError('phase competition time budget exhausted')
        raw = Game.play_match([self._match_card(a), self._match_card(b)], seed, match_id, world_id=self.data['world_id'],
            fatigue=tuple(self.data['players'][p]['fatigue'] for p in (a, b)), ruleset=RULESET, detail_level=detail_level)
        compact = Game.compact_log(raw)
        Game.verify_log(compact)
        if detail_level == 'full':
            self.artifacts[raw['log_sha256']] = raw
        costs, health = {}, {}
        for index, pid in enumerate((a, b)):
            effort, movement = self._effort(compact, index)
            delta = min(18., 2 + .10 * effort + movement / 180)
            state, activity = self.data['players'][pid], self.data['activity'][pid]
            state['fatigue'] = min(100., state['fatigue'] + delta)
            activity.update(competition_days=activity['competition_days'] + int(charge_day),
                match_count=activity['match_count'] + 1, effort=activity['effort'] + effort,
                movement_m=activity['movement_m'] + movement, last_match_date=day.isoformat())
            if charge_day:
                activity['last_competition_day'] = day.isoformat()
            costs[pid] = round(delta, 6)
            # Tournament health is settled once after the completed draw; a
            # coarse between-round adapter must not roll back a whole bracket
            # because a finalist acquires an injury halfway through processing.
            health[pid] = (dict(deferred_to=event_id) if event_id is not None
                           else self._injury_chance(pid, match_id, effort))
        self.data['matches'][match_id] = compact
        self.data['match_meta'][match_id] = dict(event_id=event_id, date=day.isoformat(),
            participant_clocks={p: dict(zip(('month', 'phase'), _clock(self.data['players'][p]))) for p in (a, b)},
            fatigue_cost=costs, health=health, ranking_settled=event_id is not None,
            detail_level=detail_level, source_log_sha256=raw['log_sha256'])
        self._record('match', match_id, compact)
        if event_id is not None:
            book = Card.RankingBook.from_snapshot(self.data['ranking'])
            book.settle_match(match_id, a, b, compact['participant_ids'][compact['winner']], day.isoformat(), kind=kind)
            self.data['ranking'] = book.snapshot()
        self.data['current_date'] = max(self.data['current_date'], day.isoformat())
        return raw

    def play_practice(self, a, b, match_id, seed, *, detail_level='summary'):
        self._writable()
        if a not in self.data['players'] or b not in self.data['players']:
            raise ValueError('participant is not loaded')
        proposed = self._fork((a, b))
        raw = proposed._play(a, b, match_id, seed, detail_level=detail_level)
        event = dict(type='practice', match_id=match_id, ranking_settled=False,
                     date=proposed.data['match_meta'][match_id]['date'])
        proposed.data['events'][match_id] = event
        proposed._record('event', match_id, event)
        self._commit(proposed)
        return copy.deepcopy(raw)

    def _environment_access(self, pid, name, mode):
        if name not in ('club', 'national', 'frontier'):
            raise ValueError('unknown training environment')
        budget = self._resource_year(pid)
        if mode == 'rest':
            return 0
        qualified = budget['national_eligible'] or (name == 'national' and self.data['players'][pid]['month'] < budget['paid_camp_until'])
        if name != 'club' and not qualified:
            raise ValueError('national training requires declared or earned eligibility')
        cost = dict(club=0, national=1, frontier=3)[name]
        if name == 'frontier' and budget['frontier_tokens'] < 1:
            raise ValueError('frontier training needs a finite earned opportunity')
        if budget['investment_units'] < cost:
            raise ValueError('training investment budget exhausted')
        budget['investment_units'] -= cost
        if name == 'frontier':
            budget['frontier_tokens'] -= 1
        return cost

    def invest_training(self, player_id, event_id, *, units=3):
        """Allocate finite development units to a temporary high-quality camp.

        These are abstract scenario resources, not money or official national
        team membership. Elite frontier opportunities remain achievement-gated.
        """
        self._writable()
        self._new_id(event_id)
        if player_id not in self.data['players'] or type(units) is not int or not 3 <= units <= 12:
            raise ValueError('loaded actor and 3..12 investment units required')
        proposed = self._fork((player_id,))
        budget = proposed._resource_year(player_id)
        if budget['investment_units'] < units:
            raise ValueError('training investment budget exhausted')
        budget['investment_units'] -= units
        month = proposed.data['players'][player_id]['month']
        budget['paid_camp_until'] = max(month, budget['paid_camp_until']) + units
        entry = dict(type='training_investment', player_id=player_id, units=units,
                     month=month, national_quality_camp_until=budget['paid_camp_until'],
                     official_membership_granted=False)
        proposed.data['events'][event_id] = entry
        proposed._record('event', event_id, entry)
        self._commit(proposed)
        return copy.deepcopy(entry)

    def train_phase(self, player_id, plan, event_id, *, environment_name='club', review_match_ids=(), training_days=None):
        if player_id not in self.data['players']:
            raise ValueError('player is not loaded')
        self._writable(catchup=player_id)
        self._new_id(event_id)
        proposed = self._fork((player_id,))
        state = proposed.data['players'][player_id]
        primary = proposed.data['players'][proposed.data['main_player_id']]
        if player_id != self.data['main_player_id'] and _clock(state) >= _clock(primary):
            raise ValueError('NPC cannot train ahead of the main world clock')
        if plan.get('month') != state['month'] or plan.get('phase') != state['training_release']['phase']:
            raise ValueError('PLAN_OUT_OF_SEQUENCE')
        activity = proposed.data['activity'][player_id]
        remaining = max(0, PHASE_DAYS - activity['competition_days'])
        mode = plan.get('mode', 'train')
        days = min(FULL_TRAINING_DAYS, remaining) if training_days is None else training_days
        if type(days) is not int or not 0 <= days <= min(FULL_TRAINING_DAYS, remaining):
            raise ValueError('training days exceed the shared half-month budget')
        if mode == 'train' and days == 0:
            raise ValueError('no training time remains; select rest to close the phase')
        cost = proposed._environment_access(player_id, environment_name, mode)
        effective_plan = copy.deepcopy(plan)
        if any(key in effective_plan for key in ('training_fraction', 'recovery_fraction')):
            raise ValueError('world computes time fractions; callers cannot override them')
        effective_plan['training_fraction'] = days / FULL_TRAINING_DAYS if mode == 'train' else 0.
        effective_plan['recovery_fraction'] = remaining / PHASE_DAYS
        reviews = []
        if len(set(review_match_ids)) != len(review_match_ids):
            raise ValueError('duplicate review source')
        for mid in review_match_ids:
            match, meta = proposed.data['matches'][mid], proposed.data['match_meta'][mid]
            actor_clock = meta['participant_clocks'].get(player_id)
            if not actor_clock or actor_clock['month'] != state['month'] or (actor_clock['month'], actor_clock['phase']) > _clock(state):
                raise ValueError('review evidence is stale, future or belongs to another actor')
            reviews.append(Game.review_event(state, match, player_id))
        before = proposed.card(player_id)
        receipt = Training.settle_phase(state, effective_plan, legacy_career.environment(environment_name), event_id, events=reviews, record=False)
        health = proposed._injury_chance(player_id, event_id) if mode == 'train' else None
        after = proposed.card(player_id)
        summary = dict(type='training_phase', player_id=player_id, month=plan['month'], phase=plan['phase'], mode=mode,
            date=self.data['current_date'], environment=environment_name, investment_cost=cost,
            competition_days=activity['competition_days'], training_days=days if mode == 'train' else 0,
            rest_days=remaining - days if mode == 'train' else remaining,
            routine_recovery_eligible_days=remaining,
            training_fraction=effective_plan['training_fraction'], recovery_fraction=effective_plan['recovery_fraction'],
            CA_before=before['CA'], CA_after=after['CA'], PA_before=before['PA'], PA_after=after['PA'],
            fatigue_after=state['fatigue'], injuries_after=state['injuries'], health=health,
            child_changes={p: after['learned_children'][g][k] - before['learned_children'][g][k]
                           for g, subs in after['learned_children'].items() for k in subs
                           for p in (f'{g}.{k}',) if after['learned_children'][g][k] != before['learned_children'][g][k]},
            receipt_sha256=_hash(receipt))
        proposed.data['events'][event_id] = summary
        proposed._record('event', event_id, summary)
        proposed.data['activity'][player_id] = _activity(state)
        if player_id == proposed.data['main_player_id']:
            next_date = _period(proposed.data['base_date'], *_clock(state))
            if next_date > date.fromisoformat(Area.HORIZON_END):
                proposed.data['current_date'] = Area.HORIZON_END
                proposed.data['completed'] = True
            else:
                proposed.data['current_date'] = max(proposed.data['current_date'], next_date.isoformat())
                if proposed.data['calendar']['year'] != next_date.year:
                    proposed.data['calendar_archive'].append(dict(year=proposed.data['calendar']['year'], sha256=_hash(proposed.data['calendar'])))
                    proposed.data['calendar'] = Area.calendar_for_year(next_date.year)
                    proposed.data['era'] = Area.get_era(next_date.year)
        self._commit(proposed)
        return dict(receipt=receipt, world_settlement=summary, budget_remaining=dict(self.data['resources'][player_id]))

    def apply_injury(self, player_id, event_id, *, severity=2, affected=('speed', 'burst')):
        self._writable()
        self._new_id(event_id)
        proposed = self._fork((player_id,))
        state = proposed.data['players'][player_id]
        receipt = career.injury(state, event_id, state['month'], affected=affected, severity=severity)
        entry = dict(type='injury_scenario', player_id=player_id, receipt=receipt,
                     provenance='EXPLICIT_SCENARIO_NOT_RANDOM_MATCH_OUTCOME')
        proposed.data['events'][event_id] = entry
        proposed._record('event', event_id, entry)
        self._commit(proposed)
        return copy.deepcopy(entry)

    def run_event(self, calendar_event_id, participant_ids, seed, *, detail_level='summary',
                  allow_experimental_specialist_summary=False):
        self._writable()
        self._new_id(calendar_event_id, calendar_event=True)
        if detail_level not in ('summary', 'full') or type(allow_experimental_specialist_summary) is not bool:
            raise ValueError('explicit detail mode and boolean experimental permission required')
        n = len(participant_ids)
        if type(seed) is not int or n < 2 or n > 128 or n & (n - 1) or len(set(participant_ids)) != n:
            raise ValueError('single-elimination field needs 2,4,8,...128 distinct actors')
        event = next((e for e in self.data['calendar']['events'] if e['event_id'] == calendar_event_id), None)
        if not event or event.get('confirmed') is not True or event['status'] != 'SIMULATED':
            raise ValueError('only an explicitly confirmed sandbox event can run')
        if event['kind'] not in ('adult_singles', 'youth_singles'):
            raise ValueError('team competition requires a separate team adapter')
        start, end = date.fromisoformat(event['start_date']), date.fromisoformat(event['end_date'])
        rounds = n.bit_length() - 1
        if start < date.fromisoformat(self.data['current_date']) or (end - start).days + 1 < rounds:
            raise ValueError('event is past or too short for at most one match per player per day')
        primary = self.data['players'][self.data['main_player_id']]
        if start < _period(self.data['base_date'], *_clock(primary)) or end > _phase_end(self.data['base_date'], primary):
            raise ValueError('event must be inside the current half-month and horizon')
        travel = event.get('travel_days', 1)
        if type(travel) is not int or not 0 <= travel <= 3:
            raise ValueError('travel_days must be 0..3')
        days = (end - start).days + 1 + travel
        checks, specialist_entries = {}, []
        entry_CA = {}
        for pid in participant_ids:
            self._check_actor(pid)
            occupied = self.data['activity'][pid].get('last_competition_day')
            if occupied and date.fromisoformat(occupied) >= start:
                raise ValueError('participant already has competition on the event start day')
            if self.data['activity'][pid]['competition_days'] + days > PHASE_DAYS:
                raise ValueError('event and travel exceed remaining phase time')
            entry_card = self.card(pid)
            entry_CA[pid] = entry_card['CA']
            checks[pid] = Area.check_entry(self.data['calendar'], calendar_event_id, entry_card, self.data['entries'])
            if not checks[pid]['eligible']:
                raise ValueError(f'entry rejected for {pid}: {checks[pid]["errors"]}')
            if detail_level == 'summary':
                from Game import tactics_v117 as plans
                from specialist_rubber_v116 import rubber_for
                kind = plans.specialist_kind(entry_card)
                faces = {wing: rubber_for(entry_card, wing) for wing in ('fh', 'bh')}
                if kind in ('chopper', 'short_pips', 'long_pips') or entry_card.get('style') == 'modern_chopper' or any(
                        face in ('short_pips', 'raw_pips', 'long_pips', 'anti_spin') for face in faces.values()):
                    specialist_entries.append(dict(player_id=pid, tactical_kind=kind,
                        style=entry_card.get('style'), rubbers=faces))
        if specialist_entries and not allow_experimental_specialist_summary:
            raise ValueError('SPECIALIST_SUMMARY_REQUIRES_EXPLICIT_EXPERIMENTAL_OPT_IN:'
                + ','.join(row['player_id'] for row in specialist_entries)
                + '; select full explicitly or allow_experimental_specialist_summary=True')
        proposed = self._fork(participant_ids)
        rng = legacy_career.rng_for(seed, self.data['world_id'], calendar_event_id)
        draw = list(participant_ids)
        rng.shuffle(draw)
        bracket, finishes, round_number = [], {}, 0
        loser_finish = {2: 'runner_up', 4: 'semifinal', 8: 'quarterfinal', 16: 'r16', 32: 'r32', 64: 'r64', 128: 'r128'}
        while len(draw) > 1:
            advanced = []
            for index in range(0, len(draw), 2):
                a, b = draw[index:index + 2]
                mid = f'{calendar_event_id}:r{round_number + 1}:m{index // 2 + 1}'
                log = proposed._play(a, b, mid, rng.randint(1, 2**31 - 1), detail_level=detail_level,
                    event_id=calendar_event_id, when=(start + timedelta(days=round_number)).isoformat(), kind=event['kind'], charge_day=False)
                winner = log['participant_ids'][log['winner']]
                loser = b if winner == a else a
                advanced.append(winner)
                finishes[loser] = loser_finish[len(draw)]
                bracket.append(dict(round=round_number + 1, match_id=mid, players=[a, b], winner=winner, games_won=log['games_won']))
            draw, round_number = advanced, round_number + 1
        winner = draw[0]
        finishes[winner] = 'champion'
        book = Card.RankingBook.from_snapshot(proposed.data['ranking'])
        scoring = []
        for pid, finish in finishes.items():
            scoring.append(book.record_event(pid, calendar_event_id, end.isoformat(), event['level'], finish, kind=event['kind']))
            proposed.data['entries'].append(dict(player_id=pid, event_id=calendar_event_id))
            proposed.data['activity'][pid]['competition_days'] += days
            proposed.data['activity'][pid]['last_competition_day'] = end.isoformat()
        health = {pid: proposed._injury_chance(pid, calendar_event_id,
                    proposed.data['activity'][pid]['effort']) for pid in participant_ids}
        proposed.data['ranking'] = book.snapshot()
        title = dict(player_id=winner, event_id=calendar_event_id, date=end.isoformat(), classification='SIMULATED', draw_size=n)
        proposed.data['titles'].append(title)
        growth_event = None
        opponents = [next(pid for pid in line['players'] if pid != winner)
                     for line in bracket if winner in line['players']]
        mean_opponent_CA = sum(entry_CA[pid] for pid in opponents) / len(opponents)
        peer_wins = sum(entry_CA[pid] >= entry_CA[winner] - 8 for pid in opponents)
        # A title's label and a tiny draw cannot certify elite development.
        # The opportunity requires two actual near-peer wins and a genuinely
        # strong opposition, measured before fatigue affects the bracket.
        qualified = n >= 4 and mean_opponent_CA >= 165 and peer_wins >= 2
        challenge = max(0., min(1., .65 + (mean_opponent_CA - entry_CA[winner]) / 40))
        challenge *= max(0., min(1., (mean_opponent_CA - 140) / 35))
        qualification = dict(eligible=qualified, mean_opponent_CA=mean_opponent_CA,
            winner_entry_CA=entry_CA[winner], near_peer_wins=peer_wins,
            required_mean_CA=165, required_near_peer_wins=2, near_peer_margin=8,
            opponent_entry_CA={pid: entry_CA[pid] for pid in opponents}, challenge=challenge,
            rule='ACTUAL_OPPOSITION_NOT_EVENT_PRESTIGE_OR_DRAW_LABEL')
        if qualified:
            budget = proposed._resource_year(winner)
            budget['national_eligible'] = True
            budget['investment_units'] = min(24, budget['investment_units'] + 3)
            if budget['reward_tokens_granted'] < 2:
                budget['frontier_tokens'] += 1
                budget['reward_tokens_granted'] += 1
            usage = Counter()
            for line in bracket:
                log = proposed.data['matches'][line['match_id']]
                if winner in log['participant_ids']:
                    usage.update(log['exposure_by_player'][log['participant_ids'].index(winner)]['usage'])
            paths = [p for p, count in usage.most_common() if count >= 8][:3]
            if paths and budget['championship_windows'] < 2:
                source_event = dict(id=f'champion-learning:{calendar_event_id}:{winner}', month=proposed.data['players'][winner]['month'],
                    kind='champion', source='WORLD_EVENT', evidence_ref=calendar_event_id, paths=paths,
                    usage={p: usage[p] for p in paths}, challenge=challenge,
                    review_quality=min(.9, .55 + .35 * min(1., sum(usage[p] for p in paths) / 150)),
                    level='major' if event['level'] in ('olympics', 'world_championships', 'world_cup', 'major') else 'normal')
                growth_event = career.register_champion(proposed.data['players'][winner], source_event)
                budget['championship_windows'] += 1
        receipt = dict(type='completed_tournament', event_id=calendar_event_id, winner=winner, draw_size=n,
            classification='SIMULATED', level=event['level'], kind=event['kind'], start_date=start.isoformat(), end_date=end.isoformat(),
            finishes=finishes, bracket=bracket, scoring=scoring, entry_preflight=checks, time_cost_days=days,
            champion_development=growth_event, post_event_health=health,
            development_qualification=qualification,
            note='Elite opportunities require actual strong near-peer opposition; injury checks occur after the draw.')
        if specialist_entries:
            receipt.update(calibration_status='UNCALIBRATED', experimental_scope='SPECIALIST_SUMMARY',
                allow_experimental_specialist_summary=True, specialist_participants=specialist_entries,
                calibration_note='Explicit experimental summary results affect sandbox ranking, titles and development evidence; no full fallback occurred.')
            for line in bracket:
                proposed.data['match_meta'][line['match_id']].update(calibration_status='UNCALIBRATED',
                    experimental_scope='SPECIALIST_SUMMARY', allow_experimental_specialist_summary=True)
        proposed.data['events'][calendar_event_id] = receipt
        proposed.data['current_date'] = end.isoformat()
        proposed._record('event', calendar_event_id, receipt)
        self._commit(proposed)
        return copy.deepcopy(receipt)

    def export_artifacts(self, directory):
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        result = []
        for digest, log in self.artifacts.items():
            Game.verify_log(log)
            path = destination / f'{digest}.json'
            content = json.dumps(log, ensure_ascii=False, allow_nan=False)
            if path.exists() and path.read_text() != content:
                raise ValueError('existing full artifact differs; never overwrite it')
            path.write_text(content)
            result.append(str(path))
        return result

    def attach_artifact(self, path):
        log = json.loads(Path(path).read_text())
        Game.verify_log(log)
        digest = log['log_sha256']
        if log.get('world_id') != self.data['world_id'] or not any(m.get('full_log_sha256') == digest for m in self.data['matches'].values()):
            raise ValueError('full artifact is not referenced by this checkpoint')
        self.artifacts[digest] = log
        return digest

    def consistency_check(self, *, deep=False):
        data = self.data
        if data.get('version') != VERSION or data.get('game_ruleset') != RULESET or data.get('horizon_end') != Area.HORIZON_END:
            raise ValueError('WORLD_RULESET_VERSION_MISMATCH')
        ids = set(data['players'])
        if not ids or any(set(data[key]) != ids for key in ('metadata', 'activity', 'resources')) or set(data['ranking']['players']) != ids:
            raise ValueError('world roster mismatch')
        primary = data['players'][data['main_player_id']]
        if any(_clock(s) > _clock(primary) for s in data['players'].values()):
            raise ValueError('NPC contains future-phase information')
        current = date.fromisoformat(data['current_date'])
        Area.ensure_date(current.isoformat())
        if data['completed']:
            if data['current_date'] != Area.HORIZON_END:
                raise ValueError('completed world must stop at the declared horizon')
        elif not _period(data['base_date'], *_clock(primary)) <= current <= _phase_end(data['base_date'], primary):
            raise ValueError('world date and phase clock disagree')
        for pid, state in data['players'].items():
            if state['id'] != pid or not 0 <= state['fatigue'] <= 100 or _clock(state) != (data['activity'][pid]['month'], data['activity'][pid]['phase']):
                raise ValueError('player identity, fatigue or activity clock mismatch')
            if not 0 <= data['activity'][pid]['competition_days'] <= PHASE_DAYS:
                raise ValueError('competition time budget violated')
        if set(data['matches']) != set(data['match_meta']):
            raise ValueError('match metadata missing')
        if data['audit_head'] != (data['audit_chain'][-1]['sha256'] if data['audit_chain'] else '0' * 64):
            raise ValueError('world audit head mismatch')
        if not Area.validate_calendar(data['calendar'])['valid']:
            raise ValueError('calendar no longer valid')
        if not data['completed'] and data['calendar']['year'] != current.year:
            raise ValueError('calendar needs refresh before further actions')
        if deep:
            _check_fingerprint(data)
            for pid, state in data['players'].items():
                Training.load_state(Training.dump_state(state))
                Card.validate(self.card(pid))
            for mid, log in data['matches'].items():
                Game.verify_log(log)
                if log['match_id'] != mid or log['world_id'] != data['world_id'] or log.get('ruleset') != RULESET or not set(log['participant_ids']) <= ids:
                    raise ValueError('match identity or ruleset mismatch')
                if any('points' in game for game in log['games']):
                    raise ValueError('checkpoint must not embed full shot logs')
            previous = '0' * 64
            for index, link in enumerate(data['audit_chain']):
                content = dict(link)
                expected = content.pop('sha256')
                payload = data['matches'][link['id']] if link['kind'] == 'match' else data['events'][link['id']]
                if link['sequence'] != index or link['previous'] != previous or link['payload_sha256'] != _hash(payload) or expected != _hash(content):
                    raise ValueError('append-only audit chain differs')
                previous = expected
            formal = {mid for mid, meta in data['match_meta'].items() if meta['ranking_settled']}
            if formal != set(data['ranking']['matches']):
                raise ValueError('match and Elo settlement ledgers disagree')
            for title in data['titles']:
                event = data['events'].get(title['event_id'], {})
                if event.get('winner') != title['player_id'] or event.get('type') != 'completed_tournament':
                    raise ValueError('title lacks a completed bracket')
            Card.RankingBook.from_snapshot(data['ranking'])
        return dict(valid=True, ruleset=VERSION, game_ruleset=RULESET, current_date=data['current_date'],
            completed=data['completed'], horizon_end=Area.HORIZON_END, players=len(ids), matches=len(data['matches']),
            phase_clock='TWO_PER_MONTH_SHARED_15_DAYS', archive_policy=data['archive_policy'],
            complete_roster=data['complete_roster'], deep=deep)

    def dump(self):
        self.consistency_check(deep=True)
        encoded = json.dumps(self.data, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        return json.dumps(dict(format=VERSION, sha256=hashlib.sha256(encoded.encode()).hexdigest(), payload=json.loads(encoded)),
                          ensure_ascii=False, allow_nan=False, separators=(',', ':'))

    @classmethod
    def load(cls, serialized):
        wrapper = json.loads(serialized)
        if wrapper.get('format') != VERSION:
            raise ValueError('explicit V1.1.7 checkpoint required; legacy worlds are not silently migrated')
        data = wrapper['payload']
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        if hashlib.sha256(encoded.encode()).hexdigest() != wrapper['sha256']:
            raise ValueError('WORLD_CHECKPOINT_CHECKSUM_MISMATCH')
        _check_fingerprint(data)
        for pid, state in data['players'].items():
            data['players'][pid] = Training.load_state(json.dumps(state, ensure_ascii=False, allow_nan=False))
        result = cls(data)
        result.consistency_check(deep=True)
        return result
