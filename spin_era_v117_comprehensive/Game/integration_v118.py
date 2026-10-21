"""Bounded match receipts and auditable full/aggregate technical exposure."""
from collections import Counter
import copy
import hashlib
import math

from common import SCHEMA, canonical_json

RULESET = 'V1.1.7-COMPREHENSIVE-1'
PATHS = frozenset(f'{g}.{k}' for g, sub in SCHEMA['subskill_weights_pct'].items() for k in sub)
SERVE_COMPONENTS = {f'serve.{k}': .30 * w / 100
                    for k, w in SCHEMA['subskill_weights_pct']['serve'].items()}
SERVE_COMPONENTS['serve.spin'] += .08
SERVE_COMPONENTS['serve.placement'] += .09


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _validate_exposures(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('two participant exposure records required')
    for row in value:
        if not isinstance(row, dict):
            raise ValueError('invalid exposure record')
        usage, pressure = row.get('usage', {}), row.get('pressure', {})
        if not isinstance(usage, dict) or not isinstance(pressure, dict):
            raise ValueError('exposure counts must be objects')
        if not set(usage) <= PATHS or not set(pressure) <= set(usage):
            raise ValueError('unregistered technical exposure path')
        if any(type(n) is not int or not 0 <= n <= 100000 for n in usage.values()):
            raise ValueError('exposure usage must be bounded nonnegative integers')
        if any(type(n) is not int or not 0 <= n <= usage[p] for p, n in pressure.items()):
            raise ValueError('pressure cannot exceed actual exposure')


def finalize(result, request):
    """Normalize new-engine evidence without altering the winner or random draws."""
    if request['detail_level'] == 'full':
        usage, pressure = [Counter(), Counter()], [Counter(), Counter()]
        contacts, moves, attacks = [0, 0], [0., 0.], [0, 0]
        for gi, game in enumerate(result['games']):
            for pi, point in enumerate(game.get('points', [])):
                for si, shot in enumerate(point.get('shots', [])):
                    actor = shot.get('player')
                    if actor not in (0, 1):
                        continue
                    # An unsuccessful interception still costs movement. A serve
                    # is an actual contact and can support a serving review.
                    movement = shot.get('movement', {})
                    moves[actor] += movement.get('distance_m', 0.) + shot.get('recovery_distance_m', 0.)
                    if shot.get('action') == 'unreached':
                        continue
                    components = SERVE_COMPONENTS if shot.get('action') == 'serve' else shot.get('technique_components')
                    if not components:
                        components = {shot.get('technique_path'): 1.}
                    if not set(components) <= PATHS or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in components.values()):
                        raise ValueError('invalid full-contact technique components')
                    total = sum(components.values())
                    draw = int.from_bytes(hashlib.sha256(canonical_json(
                        [request['seed'], 'exposure', actor, gi, pi, si]).encode()).digest()[:8], 'big') / 2**64
                    subtotal, selected = 0., next(iter(components))
                    for path, weight in sorted(components.items()):
                        subtotal += weight / total
                        if draw < subtotal:
                            selected = path
                            break
                    usage[actor][selected] += 1
                    if shot.get('reach') in ('limited', 'bad') or shot.get('fault_prob', 0) >= .2:
                        pressure[actor][selected] += 1
                    contacts[actor] += 1
                    attacks[actor] += shot.get('action_family') in ('attack', 'open', 'counter', 'flip', 'slow_loop')
        result['exposure_by_player'] = [dict(usage=dict(usage[i]), pressure=dict(pressure[i])) for i in (0, 1)]
        result['exposure_method'] = 'ONE_PATH_PER_EXECUTED_CONTACT_WEIGHTED_COMPONENTS'
        result['exposure_scope'] = 'ALL_EXECUTED_CONTACTS_INCLUDING_SERVE_EXCLUDING_UNREACHED'
        result['workload'] = dict(estimated=False, source='EXECUTED_CONTACTS_AND_ALL_MOVEMENT',
            per_player=[dict(contacts=contacts[i], movement_m=round(moves[i], 5), active_attacks=attacks[i],
                effort=round(contacts[i] * .08 + moves[i] * .18 + attacks[i] * .03, 5)) for i in (0, 1)])
        result.update(mode='full', narrative_scope='EXECUTED_SHOTS_ONLY')
    else:
        result.update(mode='summary', narrative_scope='AGGREGATE_ONLY')
        if any('points' in game for game in result['games']):
            raise ValueError('light engine must not emit fabricated shot logs')
    _validate_exposures(result['exposure_by_player'])
    workload = result.get('workload', result.get('fatigue_cost_evidence', {}))
    rows = workload.get('per_player')
    if rows is None:
        rows = [dict(contacts=0, movement_m=0., effort=0.) for _ in (0, 1)]
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError('two workload records required')
    for row in rows:
        for key in ('contacts', 'movement_m', 'effort'):
            if type(row.get(key)) not in (int, float) or not math.isfinite(row[key]) or row[key] < 0:
                raise ValueError('invalid workload evidence')
    result['fatigue_cost_evidence'] = dict(per_player=copy.deepcopy(rows),
        estimated=result['mode'] == 'summary', model='CONTACTS_MOVEMENT_AND_ATTACK_EFFORT_V118')
    result['ruleset'] = RULESET
    return result


def compact_log(match):
    """Return a separately hashed score/usage receipt, without shot trajectories."""
    from Game import v118 as Game
    Game.verify_log(match)
    if match.get('ruleset') != RULESET:
        raise ValueError('compact receipts are an explicit V1.1.7 综合版 feature')
    if match.get('compact_receipt'):
        return copy.deepcopy(match)
    fields = ('ruleset', 'release_game_version', 'classification', 'world_id', 'match_id',
        'participant_ids', 'input_cards_sha256', 'seed', 'winner', 'games_won', 'points',
        'total_strokes', 'mean_strokes', 'exposure_by_player', 'exposure_method', 'exposure_scope',
        'fatigue_cost_evidence', 'actions', 'action_family_distribution', 'family_usage',
        'tactical_plan_usage', 'specialist_plan_distribution',
        'outcome_summary', 'rally_histogram', 'rally_length_distribution', 'metadata_limits', 'match_form',
        'per_player_actions', 'target_lane_usage', 'pressure_method', 'exposure_provenance',
        'between_game_checks', 'engine', 'mechanics_source_sha256', 'style_preference_audit')
    result = {key: copy.deepcopy(match[key]) for key in fields if key in match}
    result['games'] = [{key: copy.deepcopy(game[key]) for key in ('score', 'winner', 'points_count') if key in game}
                       for game in match['games']]
    result.update(mode='summary', narrative_scope='AGGREGATE_ONLY', source_mode=match['mode'],
                  compact_receipt=True, source_log_sha256=match['log_sha256'])
    if match['mode'] == 'full':
        result['full_log_sha256'] = match['log_sha256']
    result['log_sha256'] = _digest(result)
    return result


def review_event(state, match, player_id, review_quality=.85):
    from Game import v118 as Game
    Game.verify_log(match)
    if match.get('ruleset') != RULESET or player_id != state.get('id') or player_id not in match['participant_ids']:
        raise ValueError('new-rule review participant mismatch')
    _validate_exposures(match['exposure_by_player'])
    if type(review_quality) not in (int, float) or not math.isfinite(review_quality) or not 0 <= review_quality <= 1:
        raise ValueError('invalid review quality')
    index = match['participant_ids'].index(player_id)
    row = match['exposure_by_player'][index]
    eligible = [p for p, count in row['usage'].items() if count >= 8]
    if not eligible:
        raise ValueError('no adequately logged technical exposure')
    paths = sorted(eligible, key=lambda p: (-row['pressure'].get(p, 0), -row['usage'][p], p))[:3]
    usage = {p: row['usage'][p] for p in paths}
    pressure = {p: row['pressure'].get(p, 0) for p in paths}
    challenge = .55 + .45 * sum(pressure.values()) / sum(usage.values())
    return dict(id=f"review:{match['match_id']}:{index}", month=state['month'], kind='match_review',
        source='MATCH_LOG', evidence_ref=f"sha256:{match['log_sha256']}:{index}",
        match_id=match['match_id'], match_seed=match['seed'], classification='SIMULATED',
        paths=paths, usage=usage, pressure=pressure, challenge=challenge, review_quality=review_quality,
        won=match['winner'] == index, world_id=match['world_id'], participant_id=player_id,
        bound_match_sha256=match['log_sha256'], exposure_method=match['exposure_method'],
        simulation_detail=match.get('source_mode', match['mode']))
