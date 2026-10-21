"""Audited match boundary. Legacy callbacks execute in an isolated interpreter."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import subprocess
import sys

from common import ROOT, SCHEMA, canonical_json
from card_training_v112 import compute_card

VERSION = 'V1.1.6-INTEGRATED-GAME'
LEGACY_RULESET = VERSION
PATCH_RULESET = 'V1.1.6-HGR-CANDIDATE-1'
V117_RULESET = 'V1.1.7-CANDIDATE-1'


def _validate_card(card, *, performance_only=False):
    if not isinstance(card, dict) or not isinstance(card.get('player_id'), str) or not card['player_id']:
        raise ValueError('match card requires player_id')
    if set(card.get('children', {})) != set(SCHEMA['core_order']):
        raise ValueError('match card G9 categories mismatch')
    for group, weights in SCHEMA['subskill_weights_pct'].items():
        if set(card['children'][group]) != set(weights):
            raise ValueError('match card subskills mismatch')
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 150 for v in card['children'][group].values()):
            raise ValueError('invalid technical value')
    if set(card.get('P6', {})) != set(SCHEMA['body_weights_pct']):
        raise ValueError('P6 mismatch')
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 150 for v in card['P6'].values()):
        raise ValueError('invalid body value')
    # The frozen aggregator echoes PA even though CA/G use only current G43/P6.
    # New match snapshots deliberately omit scouting and career bookkeeping.
    calculated = compute_card(dict(card, PA=0) if performance_only else card, SCHEMA)
    if card.get('G9') != calculated['G9'] or card.get('CA') != calculated['CA_calculated']:
        raise ValueError('stale card aggregates: recompute through Card')


def play_match(cards, seed, match_id, *, world_id='standalone-sandbox', fatigue=(25, 25), max_games=7, ruleset=None, detail_level=None):
    """Return a bound immutable match log. This does not itself settle rankings.

    Two participants, seed, world identity and match identity are recorded. Every
    call uses a fresh Python process, so legacy monkey patches are not shared.
    """
    ruleset = LEGACY_RULESET if ruleset is None else ruleset
    if ruleset not in (LEGACY_RULESET, PATCH_RULESET, V117_RULESET):
        raise ValueError('unsupported match ruleset')
    if ruleset == V117_RULESET:
        detail_level = 'summary' if detail_level is None else detail_level
        if detail_level not in ('full', 'summary'):
            raise ValueError('detail_level must be full or summary')
    elif detail_level is not None:
        raise ValueError('detail modes are an explicit V1.1.7 feature')
    if not isinstance(cards, (list, tuple)) or len(cards) != 2:
        raise ValueError('exactly two match cards required')
    for card in cards:
        _validate_card(card, performance_only=ruleset == V117_RULESET)
    ids = [c['player_id'] for c in cards]
    if len(set(ids)) != 2:
        raise ValueError('participants must have distinct identities')
    if type(seed) is not int or max_games not in (3, 5, 7) or type(max_games) is not int:
        raise ValueError('invalid match seed or format')
    if (ruleset == PATCH_RULESET or ruleset == V117_RULESET and detail_level == 'full') and max_games != 7:
        raise ValueError('HGR candidate currently supports BO7 only')
    if any(not isinstance(x, str) or not x for x in (match_id, world_id)):
        raise ValueError('match/world identity required')
    if len(fatigue) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 100 for v in fatigue):
        raise ValueError('invalid match fatigue')
    request = dict(cards=copy.deepcopy(list(cards)), seed=seed, fatigue=list(fatigue), max_games=max_games)
    if ruleset in (PATCH_RULESET, V117_RULESET):
        from Game.geometry import normalize_hand
        from specialist_rubber_v116 import rubber_for
        for card in cards:
            normalize_hand(card)
            for wing in ('fh', 'bh'):
                rubber_for(card, wing)
        request['ruleset'] = ruleset
        if ruleset == V117_RULESET:
            request['detail_level'] = detail_level
    process = subprocess.run([sys.executable, '-m', 'Game.worker'], input=canonical_json(request),
                             text=True, capture_output=True, cwd=ROOT, timeout=60)
    if process.returncode:
        raise RuntimeError(f'isolated match failed: {process.stderr[-1500:]}')
    result = json.loads(process.stdout)
    if ruleset == V117_RULESET:
        from .integration_v117 import finalize
        result = finalize(result, request)
    result.update(release_game_version=VERSION, classification='SIMULATED', world_id=world_id,
                  match_id=match_id, participant_ids=ids,
                  input_cards_sha256=hashlib.sha256(canonical_json(request['cards']).encode()).hexdigest(),
                  isolated_process=True)
    if ruleset in (PATCH_RULESET, V117_RULESET):
        result['release_game_version'] = ruleset
        result['ruleset'] = ruleset
    result['log_sha256'] = hashlib.sha256(canonical_json(result).encode()).hexdigest()
    return result


def verify_log(match):
    if match.get('ruleset', LEGACY_RULESET) not in (LEGACY_RULESET, PATCH_RULESET, V117_RULESET):
        raise ValueError('unsupported logged match ruleset')
    proposed = copy.deepcopy(match)
    expected = proposed.pop('log_sha256', None)
    if expected != hashlib.sha256(canonical_json(proposed).encode()).hexdigest():
        raise ValueError('MATCH_LOG_HASH_MISMATCH')
    return True


def review_event(state, match, player_id, *, review_quality=.85):
    """Bind legacy technical exposure to the actual participant in this world."""
    if match.get('ruleset') == V117_RULESET:
        from .integration_v117 import review_event as review_v117
        return review_v117(state, match, player_id, review_quality)
    import career_v116 as career
    verify_log(match)
    if player_id != state.get('id') or player_id not in match['participant_ids']:
        raise ValueError('review participant identity mismatch')
    index = match['participant_ids'].index(player_id)
    result = career.event_from_match(state, match, index, match['match_id'], review_quality)
    result['world_id'] = match['world_id']
    result['participant_id'] = player_id
    result['bound_match_sha256'] = match['log_sha256']
    return result


def compact_log(match):
    from .integration_v117 import compact_log as compact_v117
    return compact_v117(match)

