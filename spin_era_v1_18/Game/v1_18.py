"""Versioned match boundary: card preferences are separate from ability."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
import sys

from common import ROOT, canonical_json
import Game as legacy_boundary
from Game import preferences_v118 as preferences

VERSION = RULESET = V1_18_RULESET = 'V1.18-1'

MATCH_FIELDS = ('player_id', 'children', 'P6', 'G9', 'CA', 'body_limitations', 'ca_semantics',
    'style', 'hand', 'handedness', 'rubbers', 'rubber', 'fh_rubber', 'bh_rubber',
    'rubber_fh', 'rubber_bh', 'equipment', 'experimental_anti_spin', 'tactical_family', 'tactical_plan')


def match_card(card):
    """Project only current performance and declared match-relevant preferences.

    Narrative personality, PA, titles, learning factors and private provenance
    are not sent to the engine or included in the match-input hash.
    """
    if not isinstance(card, dict):
        raise ValueError('a match card is required')
    legacy_boundary._validate_card(card, performance_only=True)
    axes = preferences.axes_of(card)
    value = {key: copy.deepcopy(card[key]) for key in MATCH_FIELDS if key in card}
    if card.get('style_profile') is not None:
        value['style_profile'] = dict(version=preferences.STYLE_VERSION, axes=axes)
    return value


def play_match(cards, seed, match_id, *, world_id='standalone-v118-sandbox', fatigue=(25, 25),
               max_games=7, best_of=None, ruleset=RULESET, detail_level='summary', anti_shutout=False, first_server=0, physical_fatigue=True):
    if best_of is not None:
        if max_games != 7 and max_games != best_of: raise ValueError('conflicting format arguments')
        max_games = best_of
    if type(anti_shutout) is not bool or type(physical_fatigue) is not bool or type(first_server) is not int or first_server not in (0,1):
        raise ValueError('explicit boolean patch and first_server 0/1 required')
    if detail_level == 'full' and anti_shutout:
        raise ValueError('anti-shutout is a summary-only experiment; no hidden mode switch')
    if ruleset != RULESET or detail_level not in ('full', 'summary'):
        raise ValueError('explicit V1.1.7 综合版 ruleset and full/summary mode required')
    if not isinstance(cards, (list, tuple)) or len(cards) != 2:
        raise ValueError('exactly two match cards required')
    current = [match_card(card) for card in cards]
    ids = [card['player_id'] for card in current]
    if len(set(ids)) != 2:
        raise ValueError('participants must have distinct identities')
    if type(seed) is not int or type(max_games) is not int or max_games not in (3, 5, 7):
        raise ValueError('integer match seed and BO3/BO5/BO7 required')
    if any(not isinstance(value, str) or not value for value in (match_id, world_id)):
        raise ValueError('match/world identity required')
    if not isinstance(fatigue, (list, tuple)) or len(fatigue) != 2 or any(
            type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 100 for v in fatigue):
        raise ValueError('two finite match fatigue values in 0..100 required')
    from Game.geometry import normalize_hand
    from specialist_rubber_v116 import rubber_for
    for card in current:
        normalize_hand(card)
        for wing in ('fh', 'bh'):
            rubber_for(card, wing)
    request = dict(cards=current, seed=seed, fatigue=list(fatigue), max_games=max_games,
                   ruleset=RULESET, detail_level=detail_level, anti_shutout=anti_shutout, first_server=first_server,physical_fatigue=physical_fatigue)
    process = subprocess.run([sys.executable, '-m', 'Game.worker_v1_18'], input=canonical_json(request),
        text=True, capture_output=True, cwd=ROOT, timeout=60)
    if process.returncode:
        raise RuntimeError(f'isolated V1.1.7 综合版 match failed: {process.stderr[-1500:]}')
    result = json.loads(process.stdout)
    from Game.integration_v1_18 import finalize
    result = finalize(result, request)
    result['input_card_snapshots'] = copy.deepcopy(current)
    result['request_context'] = dict(fatigue=list(fatigue), best_of=max_games, anti_shutout=anti_shutout, first_server=first_server,physical_fatigue=physical_fatigue)
    result.update(release_game_version=RULESET, classification='SIMULATED', world_id=world_id,
        match_id=match_id, participant_ids=ids,
        input_cards_sha256=hashlib.sha256(canonical_json(current).encode()).hexdigest(),
        isolated_process=True, ruleset=RULESET)
    result['log_sha256'] = hashlib.sha256(canonical_json(result).encode()).hexdigest()
    return result


def verify_log(match):
    if not isinstance(match, dict) or match.get('ruleset') != RULESET:
        raise ValueError('explicit V1.1.7 综合版 match log required')
    value = copy.deepcopy(match)
    expected = value.pop('log_sha256', None)
    if expected != hashlib.sha256(canonical_json(value).encode()).hexdigest():
        raise ValueError('MATCH_LOG_HASH_MISMATCH')
    from Game.formats_v1_18 import validate_result
    ids=match.get('participant_ids')
    if not isinstance(ids,list) or len(ids)!=2 or len(set(ids))!=2 or any(not isinstance(p,str) or not p for p in ids):raise ValueError('two distinct participant identities required')
    if not all(isinstance(match.get(k),str) and match[k] for k in ('world_id','match_id')):raise ValueError('match/world identity required')
    validate_result(match)
    return True


def compact_log(match):
    from Game.integration_v1_18 import compact_log as implementation
    return implementation(match)


def review_event(state, match, player_id, *, review_quality=.85):
    from Game.integration_v1_18 import review_event as implementation
    return implementation(state, match, player_id, review_quality)


def replay(log):
    verify_log(log)
    if log.get('classification')=='ARCHIVED_LEGACY_RESULT' or 'input_card_snapshots' not in log:
        raise ValueError('ARCHIVE_INPUT_SNAPSHOT_UNAVAILABLE_NO_REROLL')
    c=log['request_context']
    fresh=play_match(log['input_card_snapshots'],log['seed'],log['match_id'],world_id=log['world_id'],
        fatigue=c['fatigue'],best_of=log['best_of'],detail_level=log.get('source_mode',log['mode']),
        anti_shutout=c['anti_shutout'],first_server=c['first_server'],physical_fatigue=c.get('physical_fatigue',True))
    expected=log.get('source_log_sha256',log['log_sha256'])
    if fresh['log_sha256']!=expected:raise ValueError('MATCH_REPLAY_DIFFERS_FROM_SOURCE')
    return dict(valid=True,source_log_sha256=expected,no_settlement_performed=True)
