"""Authoritative, transactional boundary for the four integrated modules."""
from __future__ import annotations
import calendar as dates
import copy
from datetime import date
import hashlib
import json
import math

import Area
import Card
import Game
import Training
from common import canonical_json
import career_v116 as runtime

VERSION = 'SPIN_ERA_V1.1.6_MODULAR_CANDIDATE_1'


def _period(base, month, phase=0):
    start = date.fromisoformat(base)
    ordinal = start.year * 12 + start.month - 1 + month
    return date(ordinal // 12, ordinal % 12 + 1, 16 if phase else 1).isoformat()


class WorldSession:
    def __init__(self, data):
        self.data = data

    @classmethod
    def create(cls, cards, year, *, start_date=None, world_id='sandbox-2006', seed=116,
               main_player_id=None, calendar=None, mode='sandbox'):
        if type(year) is not int or type(seed) is not int or not isinstance(world_id, str) or not world_id:
            raise ValueError('explicit year, world identity and integer seed required')
        if mode not in ('sandbox', 'historical_reference'):
            raise ValueError('unknown world mode')
        day = date.fromisoformat(start_date or f'{year}-01-01')
        if day.year != year or day.day != 1:
            raise ValueError('start_date must be the first day of a month in the selected year')
        normalized = [Card.normalize(c) for c in cards]
        ids = [c['player_id'] for c in normalized]
        if not ids or len(set(ids)) != len(ids):
            raise ValueError('one card per participant identity required')
        persons = [c.get('source_person_id', c['player_id'].removesuffix('_age18'))
                   if c.get('source_prototype') != 'SYNTHETIC' else c['player_id'] for c in normalized]
        if len(set(persons)) != len(persons):
            raise ValueError('multiple snapshots of one person cannot be contemporaneous actors')
        main_player_id = main_player_id or ids[0]
        if main_player_id not in ids:
            raise ValueError('main player not loaded')
        for card in normalized:
            if type(card.get('year')) is int and card['year'] > year:
                raise ValueError('future preset cannot be loaded into this world')
            if card.get('snapshot_date') and date.fromisoformat(card['snapshot_date']) > day:
                raise ValueError('future snapshot date cannot be loaded before its evidence date')
            if type(card.get('year')) is int and card['year'] < year:
                if card.get('selection', {}).get('mode') != 'PRIOR_BASELINE_NOT_GROWN' or 'model_start_age' not in card:
                    raise ValueError('older snapshot requires labeled prior baseline and explicit model_start_age')
            model_age = card.get('model_start_age', card.get('age_approx', 18))
            if type(card.get('birth_year')) is int and abs((year - card['birth_year']) - model_age) > 1:
                raise ValueError('model age conflicts with birth-year evidence')
        calendar = copy.deepcopy(calendar or Area.calendar_for_year(year, mode))
        preflight = Area.validate_calendar(calendar, year)
        if not preflight['valid']:
            raise ValueError(f'invalid calendar: {preflight["errors"]}')
        book = Card.RankingBook()
        states = {}
        for card in normalized:
            pid = card['player_id']
            book.register_player(pid)
            player_seed = runtime.rng_for(seed, 'world-player', pid).randint(1, 2**31 - 1)
            states[pid] = Training.initialize(card, seed=player_seed,
                curve=card.get('growth_curve', 'balanced_progress'),
                start_age=card.get('model_start_age', card.get('age_approx', 18)))
        data = dict(version=VERSION, world_id=world_id, mode=mode, classification='SIMULATED',
            seed=seed, base_date=day.isoformat(), current_date=day.isoformat(),
            main_player_id=main_player_id, calendar=calendar,
            era=Area.get_era(year), metadata={c['player_id']: c for c in normalized},
            players=states, ranking=book.snapshot(), matches={}, match_meta={}, events={},
            entries=[], titles=[], lineage=[], complete_roster=False)
        result = cls(data)
        result.consistency_check()
        return result

    def _writable(self):
        if self.data['mode'] != 'sandbox':
            raise ValueError('historical reference mode is read-only; create an explicit sandbox branch')

    def _new_id(self, event_id, *, calendar_event=False):
        if not isinstance(event_id, str) or not event_id:
            raise ValueError('nonempty event identity required')
        if event_id in self.data['events'] or event_id in self.data['matches']:
            raise ValueError('DUPLICATE_WORLD_EVENT')
        if not calendar_event and event_id in {e['event_id'] for e in self.data['calendar']['events']}:
            raise ValueError('event identity is reserved for a calendar competition')

    def card(self, player_id):
        state = self.data['players'][player_id]
        value = copy.deepcopy(self.data['metadata'][player_id])
        for key in ('children', 'P6', 'PA', 'pa_range', 'learning_factor', 'style_preference',
                    'xp', 'permits', 'P_xp', 'fatigue', 'injuries', 'cap_bonus'):
            value[key] = copy.deepcopy(state[key])
        value['development_profile'] = dict(body_max=state['P_max'], talent=state['talent'],
            neuromotor=state['neuromotor'], mental=state['mental'], focus=state['focus'],
            body_maturation_rate=state['body_maturation_rate'], classification='SIMULATED_DEVELOPMENT_STATE')
        value['age_approx'] = state['start_age'] + (state['month'] + state['training_release']['phase'] / 2) / 12
        value['age'] = value['age_approx']
        value['world_id'] = self.data['world_id']
        value['classification'] = 'SIMULATED'
        value['training_clock'] = dict(month=state['month'], phase=state['training_release']['phase'])
        value['ranking'] = copy.deepcopy(self.data['ranking']['players'][player_id])
        view = self.rankings()
        value['ranking_state'] = dict(asof=self.data['current_date'], scope=view['scope'],
            **next(r for r in view['standings'] if r['player_id'] == player_id),
            youth_elo=value['ranking']['youth_elo'],
            points_system=view['points_system'])
        value['simulated_career'] = dict(titles=[t for t in self.data['titles'] if t['player_id'] == player_id],
            matches=[mid for mid, m in self.data['matches'].items() if player_id in m['participant_ids']],
            classification='SIMULATED')
        return Card.recompute(value)

    def rankings(self, complete_pool=False):
        if complete_pool and not self.data['complete_roster']:
            raise ValueError('world has no declared complete ranking pool; report sample standings')
        return Card.RankingBook.from_snapshot(self.data['ranking']).world_ranking(
            self.data['current_date'], list(self.data['players']), complete_pool=complete_pool)

    def set_calendar(self, calendar):
        """Explicit year rollover/configuration, with previous calendars retained."""
        self._writable()
        year = date.fromisoformat(self.data['current_date']).year
        check = Area.validate_calendar(calendar, year)
        if not check['valid']:
            raise ValueError(f'calendar preflight failed: {check["errors"]}')
        proposed = copy.deepcopy(calendar)
        era = Area.get_era(year)
        for event in proposed['events']:
            existing = self.data['events'].get(event['event_id'])
            if event['event_id'] in self.data['matches'] or (existing and existing.get('type') != 'completed_tournament'):
                raise ValueError('calendar identity collides with an existing non-tournament event')
        if self.data['calendar']['year'] == proposed['year']:
            replacements = {e['event_id']: e for e in proposed['events']}
            for old in self.data['calendar']['events']:
                if old['event_id'] in self.data['events'] and replacements.get(old['event_id']) != old:
                    raise ValueError('completed calendar entries are immutable')
        self.data.setdefault('calendar_archive', []).append(copy.deepcopy(self.data['calendar']))
        self.data['calendar'] = proposed
        self.data['era'] = era
        return check

    def _play(self, a, b, match_id, seed, *, event_id=None, when=None, kind='adult_singles'):
        self._new_id(match_id)
        if a == b or a not in self.data['players'] or b not in self.data['players']:
            raise ValueError('two distinct loaded actors required')
        primary = self.data['players'][self.data['main_player_id']]
        world_clock = dict(month=primary['month'], phase=primary['training_release']['phase'])
        participant_clocks = {pid: dict(month=self.data['players'][pid]['month'],
                                       phase=self.data['players'][pid]['training_release']['phase'])
                              for pid in (a, b)}
        if any(clock != world_clock for clock in participant_clocks.values()):
            raise ValueError('match participants must share the current world phase; settle stale actors first')
        cards = [self.card(a), self.card(b)]
        log = Game.play_match(cards, seed, match_id, world_id=self.data['world_id'],
            fatigue=tuple(self.data['players'][p]['fatigue'] for p in (a, b)))
        fatigue_delta = min(16, 4 + log['points'] / 30)
        for pid in (a, b):
            self.data['players'][pid]['fatigue'] = min(100, self.data['players'][pid]['fatigue'] + fatigue_delta)
        self.data['matches'][match_id] = log
        self.data['match_meta'][match_id] = dict(event_id=event_id, date=when or self.data['current_date'],
            participant_months={p: self.data['players'][p]['month'] for p in (a, b)},
            participant_clocks=participant_clocks, world_clock=world_clock,
            fatigue_cost=fatigue_delta, ranking_settled=event_id is not None)
        if event_id is not None:
            book = Card.RankingBook.from_snapshot(self.data['ranking'])
            book.settle_match(match_id, a, b, log['participant_ids'][log['winner']], when, kind=kind)
            self.data['ranking'] = book.snapshot()
        return log

    def play_practice(self, a, b, match_id, seed):
        self._writable()
        proposed = WorldSession(copy.deepcopy(self.data))
        log = proposed._play(a, b, match_id, seed)
        proposed.data['events'][match_id] = dict(type='practice', match_id=match_id, ranking_settled=False)
        proposed.consistency_check()
        self.data = proposed.data
        return copy.deepcopy(log)

    def train_phase(self, player_id, plan, event_id, *, environment_name='national', review_match_ids=()):
        self._writable()
        self._new_id(event_id)
        proposed = WorldSession(copy.deepcopy(self.data))
        state = proposed.data['players'][player_id]
        if player_id != proposed.data['main_player_id']:
            primary = proposed.data['players'][proposed.data['main_player_id']]
            main_clock = primary['month'] * 2 + primary['training_release']['phase']
            actor_clock = state['month'] * 2 + state['training_release']['phase']
            if actor_clock + 1 > main_clock:
                raise ValueError('NPC cannot consume a future phase before the main world clock')
        reviews = []
        if len(set(review_match_ids)) != len(review_match_ids):
            raise ValueError('duplicate review source')
        for match_id in review_match_ids:
            log = proposed.data['matches'][match_id]
            if log['world_id'] != proposed.data['world_id']:
                raise ValueError('cross-world review rejected')
            if proposed.data['match_meta'][match_id]['participant_months'].get(player_id) != state['month']:
                raise ValueError('only current-month evidence opens a new review window')
            clock = proposed.data['match_meta'][match_id]['participant_clocks'].get(player_id)
            if clock is None or (clock['month'], clock['phase']) > (state['month'], state['training_release']['phase']):
                raise ValueError('future-phase evidence cannot affect an earlier training phase')
            reviews.append(Game.review_event(state, log, player_id))
        receipt = Training.settle_phase(state, plan, runtime.environment(environment_name), event_id, events=reviews)
        proposed.data['events'][event_id] = dict(type='training_phase', player_id=player_id, receipt=receipt)
        if player_id == proposed.data['main_player_id']:
            next_date = _period(proposed.data['base_date'], state['month'], state['training_release']['phase'])
            proposed.data['current_date'] = max(proposed.data['current_date'], next_date)
        proposed.consistency_check()
        self.data = proposed.data
        return copy.deepcopy(receipt)

    def confirm_sandbox_event(self, event_id):
        self._writable()
        if event_id in self.data['events']:
            raise ValueError('completed event cannot be reconfigured')
        events = [e for e in self.data['calendar']['events'] if e['event_id'] == event_id]
        if len(events) != 1 or events[0]['status'] != 'SIMULATED':
            raise ValueError('only an explicit simulated event can be confirmed')
        events[0]['confirmed'] = True
        events[0]['confirmation_scope'] = 'THIS_SANDBOX_ONLY_NOT_REAL_HISTORY'
        return copy.deepcopy(events[0])

    def run_event(self, calendar_event_id, participant_ids, seed):
        """Play a complete 2..128 single-elimination sandbox event, then score once."""
        self._writable()
        self._new_id(calendar_event_id, calendar_event=True)
        n = len(participant_ids)
        if type(seed) is not int or n < 2 or n > 128 or n & (n - 1) or len(set(participant_ids)) != n:
            raise ValueError('single-elimination field must have 2,4,8,...128 distinct actors')
        event = next((e for e in self.data['calendar']['events'] if e['event_id'] == calendar_event_id), None)
        if not event or not event.get('confirmed') or event['status'] != 'SIMULATED':
            raise ValueError('event must be explicitly configured for this sandbox')
        if event['kind'] not in ('adult_singles', 'youth_singles'):
            raise ValueError('team competition needs a team lineup adapter; cannot score as singles')
        start, end = date.fromisoformat(event['start_date']), date.fromisoformat(event['end_date'])
        current = date.fromisoformat(self.data['current_date'])
        if start < current or (start.year, start.month) != (current.year, current.month) or end.month != start.month:
            raise ValueError('event must be upcoming in the current settled month')
        main_state = self.data['players'][self.data['main_player_id']]
        phase_start = date.fromisoformat(_period(self.data['base_date'], main_state['month'], main_state['training_release']['phase']))
        phase_end = (date(phase_start.year, phase_start.month, 15) if main_state['training_release']['phase'] == 0
                     else date(phase_start.year, phase_start.month, dates.monthrange(phase_start.year, phase_start.month)[1]))
        if start < phase_start or end > phase_end:
            raise ValueError('event crosses the current half-month; settle the previous training/rest phase first')
        checks = {}
        for pid in participant_ids:
            if pid not in self.data['players']:
                raise ValueError('entrant is not loaded')
            actor = self.data['players'][pid]
            if (actor['month'], actor['training_release']['phase']) != (main_state['month'], main_state['training_release']['phase']):
                raise ValueError('entrant phase is stale; explicitly settle NPC training or rest first')
            checks[pid] = Area.check_entry(self.data['calendar'], calendar_event_id, self.card(pid), self.data['entries'])
            if not checks[pid]['eligible']:
                raise ValueError(f'entry rejected for {pid}: {checks[pid]["errors"]}')
        proposed = WorldSession(copy.deepcopy(self.data))
        draw = list(participant_ids)
        rng = runtime.rng_for(seed, self.data['world_id'], calendar_event_id)
        rng.shuffle(draw)
        bracket, finishes, round_index = [], {}, 0
        loser_finish = {2: 'runner_up', 4: 'semifinal', 8: 'quarterfinal',
                        16: 'r16', 32: 'r32', 64: 'r64', 128: 'r128'}
        while len(draw) > 1:
            advanced = []
            round_index += 1
            for index in range(0, len(draw), 2):
                a, b = draw[index:index + 2]
                match_id = f'{calendar_event_id}:r{round_index}:m{index // 2 + 1}'
                log = proposed._play(a, b, match_id, rng.randint(1, 2**31 - 1),
                    event_id=calendar_event_id, when=start.isoformat(), kind=event['kind'])
                winner = log['participant_ids'][log['winner']]
                loser = b if winner == a else a
                finishes[loser] = loser_finish[len(draw)]
                advanced.append(winner)
                bracket.append(dict(round=round_index, match_id=match_id, players=[a, b],
                    winner=winner, games_won=log['games_won']))
            draw = advanced
        finishes[draw[0]] = 'champion'
        book = Card.RankingBook.from_snapshot(proposed.data['ranking'])
        scoring = []
        for pid, finish in finishes.items():
            scoring.append(book.record_event(pid, calendar_event_id, end.isoformat(), event['level'], finish, kind=event['kind']))
            proposed.data['entries'].append(dict(player_id=pid, event_id=calendar_event_id))
        proposed.data['ranking'] = book.snapshot()
        proposed.data['titles'].append(dict(player_id=draw[0], event_id=calendar_event_id,
            date=end.isoformat(), classification='SIMULATED', draw_size=n))
        receipt = dict(type='completed_tournament', event_id=calendar_event_id, classification='SIMULATED',
            draw_size=n, level=event['level'], kind=event['kind'], winner=draw[0],
            start_date=start.isoformat(), end_date=end.isoformat(),
            finishes=finishes, bracket=bracket, scoring=scoring, entry_preflight=checks,
            note='Internal S-PTS sandbox; a small draw does not certify real major-event strength.')
        proposed.data['events'][calendar_event_id] = receipt
        proposed.data['current_date'] = end.isoformat()
        proposed.consistency_check()
        self.data = proposed.data
        return copy.deepcopy(receipt)

    def consistency_check(self):
        if self.data.get('version') != VERSION:
            raise ValueError('WORLD_RULESET_VERSION_MISMATCH')
        if set(self.data['players']) != set(self.data['metadata']) or set(self.data['players']) != set(self.data['ranking']['players']):
            raise ValueError('world roster/metadata/ranking identity mismatch')
        for pid, state in self.data['players'].items():
            if state['id'] != pid:
                raise ValueError('player state identity mismatch')
            Training.load_state(Training.dump_state(state))
            Card.validate(self.card(pid))
        primary = self.data['players'][self.data['main_player_id']]
        main_clock = primary['month'] * 2 + primary['training_release']['phase']
        if any(s['month'] * 2 + s['training_release']['phase'] > main_clock for s in self.data['players'].values()):
            raise ValueError('NPC state contains future phase information')
        phase_start = date.fromisoformat(_period(self.data['base_date'], primary['month'], primary['training_release']['phase']))
        phase_end = date(phase_start.year, phase_start.month, 15 if primary['training_release']['phase'] == 0
                         else dates.monthrange(phase_start.year, phase_start.month)[1])
        if not phase_start <= date.fromisoformat(self.data['current_date']) <= phase_end:
            raise ValueError('world date and half-month clock disagree')
        for mid, match in self.data['matches'].items():
            Game.verify_log(match)
            if mid != match['match_id'] or match['world_id'] != self.data['world_id'] or not set(match['participant_ids']) <= set(self.data['players']):
                raise ValueError('match identity/world mismatch')
        if set(self.data['matches']) != set(self.data['match_meta']):
            raise ValueError('match metadata missing')
        for mid, meta in self.data['match_meta'].items():
            participants = self.data['matches'][mid]['participant_ids']
            if set(meta.get('participant_clocks', {})) != set(participants):
                raise ValueError('match phase evidence missing')
            clock = meta.get('world_clock', {})
            if type(clock.get('month')) is not int or clock['month'] < 0 or type(clock.get('phase')) is not int or clock['phase'] not in (0, 1):
                raise ValueError('invalid match evidence clock')
            period_start = date.fromisoformat(_period(self.data['base_date'], clock['month'], clock['phase']))
            period_end = date(period_start.year, period_start.month, 15 if clock['phase'] == 0 else
                              dates.monthrange(period_start.year, period_start.month)[1])
            if not period_start <= date.fromisoformat(meta['date']) <= period_end:
                raise ValueError('match date and evidence phase disagree')
            for pid, actor_clock in meta['participant_clocks'].items():
                actor = self.data['players'][pid]
                if actor_clock != clock or meta['participant_months'].get(pid) != clock['month']:
                    raise ValueError('match participants were not contemporaneous')
                if (clock['month'], clock['phase']) > (actor['month'], actor['training_release']['phase']):
                    raise ValueError('match contains future information for a participant')
        formal_matches = {mid for mid, meta in self.data['match_meta'].items() if meta['ranking_settled']}
        if formal_matches != set(self.data['ranking']['matches']):
            raise ValueError('match and Elo settlement ledgers disagree')
        for title in self.data['titles']:
            event = self.data['events'].get(title['event_id'], {})
            if event.get('type') != 'completed_tournament' or event.get('winner') != title['player_id']:
                raise ValueError('title is not backed by a completed event')
        for pid, ranking in self.data['ranking']['players'].items():
            for entry in ranking['results'] + ranking['youth_points'] + ranking['team_points']:
                event = self.data['events'].get(entry['event_id'], {})
                if event.get('finishes', {}).get(pid) != entry['finish']:
                    raise ValueError('S-PTS result is not backed by a completed bracket')
        if not Area.validate_calendar(self.data['calendar'])['valid']:
            raise ValueError('calendar no longer valid')
        Card.RankingBook.from_snapshot(self.data['ranking'])
        return dict(valid=True, ruleset=VERSION, players=len(self.data['players']), matches=len(self.data['matches']),
            phase_clock='TWO_PER_MONTH', current_date=self.data['current_date'],
            complete_roster=self.data['complete_roster'],
            calendar_refresh_required=self.data['calendar']['year'] != date.fromisoformat(self.data['current_date']).year)

    def dump(self):
        self.consistency_check()
        # Preserve insertion order: the legacy biology RNG iterates ordered fields.
        payload = json.loads(json.dumps(self.data, ensure_ascii=False, allow_nan=False))
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        return json.dumps(dict(format=VERSION, sha256=hashlib.sha256(encoded.encode()).hexdigest(),
                               payload=payload), ensure_ascii=False, indent=2, allow_nan=False)

    @classmethod
    def load(cls, serialized):
        wrapper = json.loads(serialized)
        if wrapper.get('format') != VERSION:
            raise ValueError('legacy/unknown checkpoint needs an explicit migration; never reset silently')
        data = wrapper['payload']
        encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        if hashlib.sha256(encoded.encode()).hexdigest() != wrapper['sha256']:
            raise ValueError('WORLD_CHECKPOINT_CHECKSUM_MISMATCH')
        for pid, state in data['players'].items():
            data['players'][pid] = Training.load_state(json.dumps(state, ensure_ascii=False, allow_nan=False))
        result = cls(data)
        result.consistency_check()
        return result
