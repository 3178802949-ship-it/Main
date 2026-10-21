"""Complete character cards and independent, transactional ranking ledgers.

Archived numeric assessments stay immutable. Added development fields are
explicit ASSESSMENT inputs, not newly established facts about real athletes.
"""
from __future__ import annotations

import copy
from dataclasses import asdict
from datetime import date
import hashlib
import json
import math

from common import ROOT, SCHEMA, canonical_json
from card_training_v112 import P, compute_card, physical_weights
import career_v114 as legacy
import career_v116 as career
import ranking_v112 as ranking

VERSION = 'V1.1.6-INTEGRATED-CARD'
PATHS = tuple(f'{g}.{k}' for g, sub in SCHEMA['subskill_weights_pct'].items() for k in sub)
ASIAN_NATIONS = {'中国', '中国台北', '中国香港', '印度', '日本', '韩国'}
AFRICAN_NATIONS = {'埃及', '尼日利亚'}
EUROPEAN_NATIONS = {'丹麦', '俄罗斯', '克罗地亚', '奥地利', '希腊', '德国', '捷克',
    '斯洛文尼亚', '比利时', '法国', '瑞典', '白俄罗斯', '罗马尼亚', '葡萄牙', '西班牙'}


def _finite(value, name, low=None, high=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if low is not None and value < low or high is not None and value > high:
        raise ValueError(f'{name} out of bounds')
    return value


def _identity(card):
    player_id = card.get('player_id', card.get('id'))
    if not isinstance(player_id, str) or not player_id.strip():
        raise ValueError('card needs a nonempty player_id')
    if card.get('id', player_id) != player_id:
        raise ValueError('conflicting player_id and state id')
    return player_id


def _traits(card):
    if not isinstance(card, dict):
        raise ValueError('card must be an object')
    _identity(card)
    children = card.get('children')
    expected = SCHEMA['subskill_weights_pct']
    if not isinstance(children, dict) or set(children) != set(expected):
        raise ValueError('children must contain the exact nine technical groups')
    for group, schema in expected.items():
        if not isinstance(children[group], dict) or set(children[group]) != set(schema):
            raise ValueError(f'incomplete subskills in {group}')
        for key, value in children[group].items():
            _finite(value, f'{group}.{key}', 0, 150)
    if not isinstance(card.get('P6'), dict) or set(card['P6']) != set(P):
        raise ValueError('P6 must contain all six body attributes')
    for key, value in card['P6'].items():
        _finite(value, key, 0, 150)
    _finite(card.get('PA'), 'PA', 0, 200)


def _development_valid(card, profile):
    if not isinstance(profile, dict):
        raise ValueError('development_profile must be an object')
    if set(profile.get('body_max', {})) != set(P):
        raise ValueError('body_max must contain all P6')
    for key, value in profile['body_max'].items():
        _finite(value, f'body_max.{key}', card['P6'][key], 150)
    for field in ('talent', 'neuromotor'):
        if set(profile.get(field, {})) != set(PATHS):
            raise ValueError(f'{field} must contain all 43 paths')
        for path, value in profile[field].items():
            _finite(value, f'{field}.{path}')
    _finite(profile.get('mental'), 'mental')
    if (not isinstance(profile.get('focus'), list) or len(set(profile['focus'])) != len(profile['focus'])
            or not set(profile['focus']) <= set(PATHS)):
        raise ValueError('focus must contain distinct valid paths')
    _finite(profile.get('body_maturation_rate', .02), 'body_maturation_rate', .001, .04)


def _fraction(*parts):
    h = hashlib.sha256('|'.join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], 'big') / 2 ** 64


def _inferred_development(card):
    """Infer compatible lower bounds from observed skills, never from PA.

    Physical hard caps remain binding; observed legacy exceptions are recorded
    separately, rather than hidden by increasing P or adding cap bonuses.
    """
    age = card.get('age_approx', card.get('age', 25))
    _finite(age, 'age', 0, 100)
    room = 8 if age < 20 else 4 if age < 25 else 2 if age < 32 else 0
    body_max = {key: min(150, value + room) for key, value in card['P6'].items()}
    cognition = max(sum(card['children'][g].values()) / len(card['children'][g]) for g in ('read', 'stable'))
    mental = round(max(4., min(24., 5 + .9 * (cognition - 135))), 4)
    group_strength = {g: sum(sub.values()) / len(sub) for g, sub in card['children'].items()}
    ranked = sorted(PATHS, key=lambda p: (
        -(card['children'][p.split('.')[0]][p.split('.')[1]] - group_strength[p.split('.')[0]]), p))
    focus = ranked[:7]
    neural, talents = {}, {}
    pid, year = _identity(card), card.get('year', 'unknown')
    for path in PATHS:
        group, key = path.split('.')
        neural[path] = round(1 + (1.2 if path in focus else 0) + _fraction(pid, year, path, 'neural'), 4)
        mix = sum(card['P6'][p] * w for p, w in physical_weights(path).items())
        alpha = .12 if group in ('read', 'stable') else .71 if key in ('power', 'start', 'arrival') else .52 if key in ('continuity', 'defense', 'spin', 'flick') else .40
        base = 126 + alpha * (mix - 110) + (mental if group in ('read', 'stable') else 0)
        if key not in ('power', 'start', 'arrival') and group not in ('read', 'stable'):
            base += .78 * neural[path]
        observed = card['children'][group][key]
        target = min(150, observed + (2 if age < 25 else 1))
        # A compatibility estimate with a small independent residual, no PA gate.
        talents[path] = round(max(2 + 4 * _fraction(pid, year, path, 'talent'), (target - base) / .36), 4)
    return dict(body_max=body_max, talent=talents, neuromotor=neural, mental=mental,
                focus=focus, body_maturation_rate=.02,
                classification='ASSESSMENT', method='OBSERVED_SKILL_COMPATIBILITY_NOT_LATENT_POTENTIAL_CERTIFICATION')


def _region(nation):
    if nation in ASIAN_NATIONS:
        return 'Asia'
    if nation in AFRICAN_NATIONS:
        return 'Africa'
    if nation == '巴西':
        return 'Americas'
    if nation in EUROPEAN_NATIONS:
        return 'Europe'
    return 'UNVERIFIED'


def recompute(state_or_card):
    """Recalculate G9/CA while preserving metadata and all current subskill values."""
    result = copy.deepcopy(state_or_card)
    _traits(result)
    result['player_id'] = _identity(result)
    calc = compute_card(result, SCHEMA)
    result.update(G9=calc['G9'], G_composite=calc['G_aggregate'],
                  P_composite=calc['P_aggregate'], CA=calc['CA_calculated'],
                  CA_calculated=calc['CA_calculated'])
    result.pop('CA_effective', None)
    result['ca_semantics'] = 'CURRENT_G43_P6_OUTPUT_ONLY_NOT_CLIPPED_BY_PA'
    if all(k in result for k in ('P_max', 'talent', 'neuromotor', 'mental', 'focus')):
        profile = copy.deepcopy(result.get('development_profile', {}))
        profile.update(body_max=copy.deepcopy(result['P_max']), talent=copy.deepcopy(result['talent']),
            neuromotor=copy.deepcopy(result['neuromotor']), mental=result['mental'],
            focus=copy.deepcopy(result['focus']), body_maturation_rate=result.get('body_maturation_rate', .02),
            classification='SIMULATED_STATE')
        result['development_profile'] = profile
    return result


def normalize(profile, *, development_profile=None):
    """Return a complete, JSON-portable card. Never mutate the input archive."""
    card = recompute(profile)
    pid = card['player_id']
    if development_profile is None:
        development_profile = card.get('development_profile')
    if development_profile is None and all(k in card for k in ('P_max', 'talent', 'neuromotor', 'mental', 'focus')):
        development_profile = dict(body_max=card['P_max'], talent=card['talent'],
            neuromotor=card['neuromotor'], mental=card['mental'], focus=card['focus'],
            body_maturation_rate=card.get('body_maturation_rate', .02), classification='SIMULATED_STATE')
    inferred = development_profile is None
    card['development_profile'] = copy.deepcopy(development_profile or _inferred_development(card))
    _development_valid(card, card['development_profile'])
    year = card.get('year', 'starter')
    card.setdefault('preset_id', f'{pid}@{year}')
    card.setdefault('name_zh', pid)
    card.setdefault('nation', card.get('nation_prototype', 'UNVERIFIED'))
    card.setdefault('region', _region(card['nation']))
    card.setdefault('region_classification', 'ASSESSMENT')
    card.setdefault('source_prototype', 'SYNTHETIC' if card.get('origin') == 'SYNTHETIC' else 'UNVERIFIED')
    card.setdefault('source_story_gender', card.get('gender_in_story', 'UNSPECIFIED'))
    card.setdefault('story_gender', card.get('gender_in_story', 'UNSPECIFIED'))
    card.setdefault('classification', 'ASSESSMENT')
    card.setdefault('style', 'modern_chopper' if '削' in str(card.get('role', '')) else 'attacker')
    card.setdefault('tendencies', {})
    if 'growth' in card:
        legacy_growth = card.pop('growth')
        if 'legacy_growth_reference' in card and card['legacy_growth_reference'] != legacy_growth:
            raise ValueError('conflicting legacy growth references')
        card['legacy_growth_reference'] = copy.deepcopy(legacy_growth)
    card['growth_contract'] = dict(authority='Training', schedule='TWO_PHASE_CATEGORY_TRAINING',
                                   legacy_lazy_growth_active=False)
    card.setdefault('pa_range', [max(0, card['PA'] - 4), min(200, card['PA'] + 4)])
    focus = set(card['development_profile']['focus'])
    if 'learning_factor' not in card:
        card['learning_factor'] = {p: round((.88 + .24 * _fraction(pid, year, p, 'learning')) * (1.08 if p in focus else 1), 4) for p in PATHS}
    if 'style_preference' not in card:
        card['style_preference'] = {p: round((.85 + .30 * _fraction(pid, year, p, 'style')) * (1.2 if p in focus else 1), 4) for p in PATHS}
    state = dict(P6=card['P6'], talent=card['development_profile']['talent'],
                 neuromotor=card['development_profile']['neuromotor'],
                 mental=card['development_profile']['mental'], cap_bonus={})
    exceptions = []
    for path in PATHS:
        group, key = path.split('.')
        value, cap = card['children'][group][key], legacy.soft_cap(state, path)
        if value > cap:
            exceptions.append(dict(path=path, observed=value, current_cap=cap,
                policy='PRESERVE_OBSERVED_VALUE_NO_TRAINING_DOWNCLIP_NO_CAP_BYPASS'))
    card['grandfathered_over_cap'] = exceptions
    card.setdefault('historical_reference', dict(
        champion_history=copy.deepcopy(card.get('champion_history_as_of_snapshot', [])),
        classification='READ_ONLY_SOURCE_REFERENCE_NOT_SIMULATED_TITLES'))
    card.setdefault('simulated_career', dict(titles=[], matches=[], classification='SIMULATED'))
    card.setdefault('ranking_state', dict(adult_elo=None, youth_elo=None, S_PTS=None,
        scope='UNSET_NO_LEDGER', world_ranking_status='UNAVAILABLE_WITHOUT_DECLARED_COMPLETE_POOL'))
    card.setdefault('provenance', {})
    card['provenance'].update(normalization_version=VERSION,
        numeric_status='SIMULATED_STATE_REAGGREGATED' if 'P_max' in card else 'ORIGINAL_SUBSKILLS_AND_P6_PRESERVED_REAGGREGATED')
    card['provenance'].setdefault('development_status', 'ASSESSMENT' if inferred else 'EXPLICIT_OR_SIMULATED_INPUT')
    card['provenance'].setdefault('original_profile_sha256', hashlib.sha256(canonical_json(profile).encode()).hexdigest())
    validate(card)
    return card


def validate(card):
    _traits(card)
    calc = compute_card(card, SCHEMA)
    if 'G9' in card and card['G9'] != calc['G9']:
        raise ValueError('stored G9 does not match all 43 subskills')
    if 'CA' in card and card['CA'] != calc['CA_calculated']:
        raise ValueError('stored CA does not match G43/P6 aggregation')
    if 'CA_calculated' in card and card['CA_calculated'] != calc['CA_calculated']:
        raise ValueError('stored CA_calculated is stale')
    if 'development_profile' in card:
        _development_valid(card, card['development_profile'])
    for field in ('learning_factor', 'style_preference'):
        if field in card:
            if set(card[field]) != set(PATHS):
                raise ValueError(f'{field} must cover all 43 paths')
            for path, value in card[field].items():
                _finite(value, f'{field}.{path}', .01, 10)
    if 'pa_range' in card:
        bounds = card['pa_range']
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError('pa_range needs two bounds')
        _finite(bounds[0], 'pa_range lower', 0, card['PA'])
        _finite(bounds[1], 'pa_range upper', card['PA'], 200)
    try:
        canonical_json(card)
    except (TypeError, ValueError) as error:
        raise ValueError('card must be finite portable JSON') from error
    return True


def make_ma18():
    profiles = json.loads((ROOT / 'data/original/spin_era_players_archive_2000_2026_v12.json').read_text())['profiles']
    base = legacy.age18_card(profiles, SCHEMA, 'ma_long', (2004, 2008), 2006, [195, 200])
    state = career.start(base, seed=1162006, curve='foundation_builder')
    base.update(name_zh='马龙式18岁测试卡', nation_prototype='中国', source_prototype='real_mens_player',
                age_approx=18, birth_year=1988, year=2006, snapshot_date='2006-01-01',
                classification='SIMULATED', story_gender='UNSPECIFIED',
                role='战术理解与技术补齐的合成起点',
                learning_factor=state['learning_factor'], style_preference=state['style_preference'])
    dp = dict(body_max=state['P_max'], talent=state['talent'], neuromotor=state['neuromotor'],
              mental=state['mental'], focus=state['focus'], body_maturation_rate=state['body_maturation_rate'],
              classification='LEGACY_SYNTHETIC_REGRESSION_FIXTURE_NOT_HISTORICAL_POTENTIAL')
    return normalize(base, development_profile=dp)


def build_presets():
    source = ROOT / 'data/original/spin_era_players_archive_2000_2026_v12.json'
    profiles = json.loads(source.read_text())['profiles']
    output = [normalize(p) for p in profiles]
    identities = [(p['player_id'], p['year']) for p in output]
    if len(set(identities)) != len(identities):
        raise ValueError('duplicate preset identity')
    document = dict(version=VERSION, classification='ASSESSMENT', profiles=output,
                    starters=dict(ma18=make_ma18()))
    (ROOT / 'data/presets_normalized.json').write_text(json.dumps(document, ensure_ascii=False, indent=2))
    report = dict(version=VERSION, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        profiles=len(output), numeric_subskill_changes=0, numeric_P6_changes=0,
        CA_recomputed_consistent=sum(p['CA'] == q['CA'] for p, q in zip(profiles, output)),
        independently_completed_development_profiles=len(output),
        grandfathered_profiles=[dict(player_id=p['player_id'], year=p['year'], issues=p['grandfathered_over_cap'])
                                  for p in output if p['grandfathered_over_cap']],
        policy='STRUCTURAL_AND_RULE_COMPATIBILITY_OPTIMIZATION_NOT_REAL_ABILITY_RECERTIFICATION',
        historical_titles_copied_into_simulated_career=0,
        legacy_growth_references_preserved=sum('legacy_growth_reference' in p for p in output),
        active_legacy_lazy_growth=0,
        active_growth_authority='Training/TWO_PHASE_CATEGORY_TRAINING',
        gender_policy='PRESERVE_SOURCE_STORY_GENDER_SEPARATE_FROM_REAL_MENS_PROTOTYPE',
        start_age_range=[min(p['age_approx'] for p in output), max(p['age_approx'] for p in output)])
    (ROOT / 'reports/CARD_MIGRATION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return document


def get_preset(player_id, year):
    target = ROOT / 'data/presets_normalized.json'
    if not target.exists():
        raise ValueError('normalized presets not built; run Card.build_presets()')
    profiles = json.loads(target.read_text())['profiles']
    candidates = [p for p in profiles if p['player_id'] == player_id and p['year'] == year]
    if len(candidates) != 1:
        raise ValueError('no unique exact-year preset; future snapshots are not backfilled')
    return copy.deepcopy(candidates[0])


def _date(value):
    if not isinstance(value, str):
        raise ValueError('date must be YYYY-MM-DD')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError('date must be YYYY-MM-DD') from error
    if parsed.isoformat() != value:
        raise ValueError('date must be YYYY-MM-DD')
    return value


def _event_id(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('event/match id must be nonempty')
    return value


class RankingBook:
    """Adult/youth Elo and event S-PTS, with explicit roster completeness."""
    def __init__(self):
        self._players = {}
        self._matches = {}
        self._event_catalog = {}

    def register_player(self, player_id, elo=1500, youth_elo=1500):
        _event_id(player_id)
        if player_id in self._players:
            raise ValueError('player already registered')
        _finite(elo, 'elo', 0, 4000)
        _finite(youth_elo, 'youth_elo', 0, 4000)
        player = ranking.Rating(player_id, elo=float(elo), youth_elo=float(youth_elo))
        self._players[player_id] = asdict(player)
        return copy.deepcopy(self._players[player_id])

    def settle_match(self, match_id, a_id, b_id, winner_id, date, kind='adult_singles', importance=1):
        _event_id(match_id)
        _date(date)
        if match_id in self._matches:
            raise ValueError('duplicate match id')
        if a_id == b_id or a_id not in self._players or b_id not in self._players:
            raise ValueError('two distinct registered players required')
        if winner_id not in (a_id, b_id) or kind not in ('adult_singles', 'youth_singles'):
            raise ValueError('invalid winner or match ledger')
        _finite(importance, 'importance', .5, 1.5)
        for pid in (a_id, b_id):
            if self._players[pid]['last_date'] and date < self._players[pid]['last_date']:
                raise ValueError('backdated rating settlement requires a full chronological replay')
        a, b = ranking.Rating(**copy.deepcopy(self._players[a_id])), ranking.Rating(**copy.deepcopy(self._players[b_id]))
        result = ranking.settle_singles(a, b, winner_id, date, importance=importance, kind=kind)
        result.update(match_id=match_id, classification='SIMULATED')
        self._players[a_id], self._players[b_id] = asdict(a), asdict(b)
        self._matches[match_id] = copy.deepcopy(result)
        return copy.deepcopy(result)

    def record_event(self, player_id, event_id, date, level, finish, kind='adult_singles', qualifier_wins=0):
        _event_id(event_id)
        _date(date)
        if player_id not in self._players:
            raise ValueError('unregistered player')
        if kind not in ('adult_singles', 'youth_singles', 'team'):
            raise ValueError('unknown event ledger')
        if level not in ranking.LEVEL or finish not in ranking.FINISH:
            raise ValueError('unknown event level or finish')
        if type(qualifier_wins) is not int or not 0 <= qualifier_wins <= 128:
            raise ValueError('invalid qualifier wins')
        identity = dict(date=date, level=level, kind=kind)
        if event_id in self._event_catalog and self._event_catalog[event_id] != identity:
            raise ValueError('conflicting event identity')
        player = ranking.Rating(**copy.deepcopy(self._players[player_id]))
        receipt = ranking.record_result(player, event_id, date, level, finish,
                                         qualifier_wins=qualifier_wins, kind=kind)
        receipt['qualifier_wins'] = qualifier_wins
        self._players[player_id] = asdict(player)
        self._event_catalog[event_id] = identity
        return copy.deepcopy(receipt)

    def world_ranking(self, asof, eligible_ids, complete_pool=False):
        _date(asof)
        if type(complete_pool) is not bool:
            raise ValueError('complete_pool must be an explicit boolean')
        if not isinstance(eligible_ids, (list, tuple)) or not eligible_ids or len(set(eligible_ids)) != len(eligible_ids):
            raise ValueError('a distinct nonempty eligible roster is required')
        if not set(eligible_ids) <= set(self._players):
            raise ValueError('eligible roster contains unregistered players')
        players = [ranking.Rating(**copy.deepcopy(self._players[pid])) for pid in eligible_ids]
        # A historical ranking query cannot use Elo earned in a later match.
        historical = {p.name: p for p in players}
        for match in self._matches.values():
            if match['kind'] == 'adult_singles' and match['match_date'] > asof:
                a, b = match['players']
                if a in historical:
                    historical[a].elo -= match['elo_delta_A']
                if b in historical:
                    historical[b].elo += match['elo_delta_A']
        ordering = ranking.leaderboard(players, asof)
        rows = [dict(player_id=pid, S_PTS=pts, elo=elo,
                     **({'world_rank': rank} if complete_pool else {'sample_rank': rank}))
                for rank, pid, pts, elo in ordering]
        return dict(asof=asof, scope='DECLARED_COMPLETE_POOL' if complete_pool else 'SAMPLE_ONLY',
                    complete_pool=complete_pool, roster_size=len(players), standings=rows,
                    points_system='INTERNAL_S_PTS_NOT_OFFICIAL_HISTORICAL_ITTF')

    def snapshot(self):
        return copy.deepcopy(dict(version=VERSION, players=self._players,
                                  matches=self._matches, event_catalog=self._event_catalog))

    @classmethod
    def from_snapshot(cls, snapshot):
        data = copy.deepcopy(snapshot)
        if data.get('version') != VERSION:
            raise ValueError('unsupported ranking snapshot version')
        canonical_json(data)
        result = cls()
        for pid, value in data.get('players', {}).items():
            _event_id(pid)
            player = ranking.Rating(**value)
            if player.name != pid:
                raise ValueError('ranking player identity mismatch')
            _finite(player.elo, 'elo', 0, 4000)
            _finite(player.youth_elo, 'youth_elo', 0, 4000)
            for count in (player.match_count, player.youth_match_count):
                if type(count) is not int or count < 0:
                    raise ValueError('invalid rating match count')
            if player.last_date:
                _date(player.last_date)
            event_ids = set()
            for events, kind in ((player.results, 'adult_singles'), (player.youth_points, 'youth_singles'), (player.team_points, 'team')):
                if not isinstance(events, list):
                    raise ValueError('event ledger must be a list')
                for event in events:
                    eid = _event_id(event.get('event_id'))
                    if eid in event_ids or event.get('kind') != kind:
                        raise ValueError('duplicate or cross-ledger event')
                    event_ids.add(eid)
                    _date(event.get('date'))
                    if event.get('level') not in ranking.LEVEL or event.get('finish') not in ranking.FINISH:
                        raise ValueError('unsupported restored event')
                    wins = event.get('qualifier_wins', 0)
                    if type(wins) is not int or not 0 <= wins <= 128:
                        raise ValueError('invalid restored qualifier wins')
                    expected = ranking.event_points(event['level'], event['finish'], qualifier_wins=wins)
                    if event.get('points') != expected:
                        raise ValueError('restored event points do not match placement')
                    identity = dict(date=event['date'], level=event['level'], kind=kind)
                    if data.get('event_catalog', {}).get(eid) != identity:
                        raise ValueError('restored event catalog identity mismatch')
            result._players[pid] = asdict(player)
        for mid, match in data.get('matches', {}).items():
            _event_id(mid)
            if match.get('match_id') != mid:
                raise ValueError('restored match identity mismatch')
            players = match.get('players', [])
            if (not isinstance(players, list) or len(players) != 2 or len(set(players)) != 2
                    or not set(players) <= set(result._players) or match.get('winner') not in players
                    or match.get('kind') not in ('adult_singles', 'youth_singles')):
                raise ValueError('invalid restored match')
            _date(match.get('match_date'))
            _finite(match.get('elo_delta_A'), 'restored Elo delta')
        result._matches = copy.deepcopy(data.get('matches', {}))
        result._event_catalog = copy.deepcopy(data.get('event_catalog', {}))
        return result

