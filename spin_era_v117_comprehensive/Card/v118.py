"""Observer-facing preferences and source-qualified narrative personality.

Preferences describe desired ways of playing, never proficiency. Public cards
do not expose narrator-only cues or future development parameters. The original
Card implementation remains byte-identical and owns ability/ranking arithmetic.
"""
from __future__ import annotations

import copy
from collections import Counter
from datetime import date
import hashlib
import json
import math

import Card as baseline
from common import ROOT, canonical_json

VERSION = 'V1.1.7-COMPREHENSIVE-CARD-1'
STYLE_VERSION = 'V1.1.7-COMPREHENSIVE-STYLE-1'
PERSONALITY_VERSION = 'V1.1.7-COMPREHENSIVE-PERSONALITY-1'
AXES = ('forehand_use', 'backhand_use', 'short_game', 'first_three', 'rally',
        'away_table', 'topspin_preference', 'backspin_control', 'spin_variation',
        'initiative', 'counterattack', 'risk')
PATHS = baseline.PATHS
RankingBook = baseline.RankingBook

# These are intentionally re-exported without changing frozen aggregation or
# ledger rules. New game/world entry points opt in to this separate module.
recompute = baseline.recompute
build_presets = baseline.build_presets


def _library():
    return json.loads((ROOT / 'data/player_profiles_v118.json').read_text(encoding='utf-8'))


def _clamp(v):
    return round(max(0., min(1., float(v))), 4)


def _fraction(*parts):
    raw = hashlib.sha256('|'.join(map(str, parts)).encode()).digest()
    return int.from_bytes(raw[:8], 'big') / 2**64


def _year(card):
    value = card.get('year')
    if value is None and card.get('snapshot_date'):
        value = date.fromisoformat(card['snapshot_date']).year
    if value is not None and (type(value) is not int or not 1900 <= value <= 2100):
        raise ValueError('style snapshot year must be an explicit integer')
    return value


def _default_traits(player_id, seed=118):
    # These are writing choices for a fictional simulation, not psychological
    # conclusions about the named real prototype.
    pools = (('简洁交流', '先听后说', '清楚表达', '温和幽默'),
             ('耐心积累', '重视复盘', '偏好有序准备', '乐于尝试'),
             ('尊重合作', '愿意交流经验', '偏好安静整理', '重视清楚约定'))
    return [pool[min(len(pool)-1, int(_fraction(seed, player_id, i) * len(pool)))]
            for i, pool in enumerate(pools)]


def _infer_style(card):
    t = card.get('tendencies', {})
    if not isinstance(t, dict):
        raise ValueError('tendencies must be an object')
    values = {}
    for key in ('initiative', 'close_table', 'bh_pressure', 'placement', 'unusual', 'risk'):
        value = t.get(key, 50)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f'preference source {key} must be in 0..100')
        values[key] = value / 100
    role = str(card.get('role', ''))
    chopper = card.get('style') == 'modern_chopper' or '削球' in role
    close, initiative, risk = (values[k] for k in ('close_table', 'initiative', 'risk'))
    placement, unusual = values['placement'], values['unusual']
    bh = _clamp(.25 + .50 * values['bh_pressure'] + (.08 if '横打' in role or '反手' in role else 0.)
                - (.08 if '正手主导' in role or '正手压迫' in role else 0.))
    short = _clamp(.15 + .65 * close + .15 * placement + (.08 if '台内' in role or '细腻' in role else 0.))
    axes = dict(forehand_use=_clamp(1-bh), backhand_use=bh, short_game=short,
        first_three=_clamp(.10 + .35 * initiative + .40 * close + .15 * risk + (.10 if '前三板' in role else 0.)),
        rally=_clamp(.45 + .25 * (1-risk) + .10 * (1-close) + (.15 if '相持' in role or '连续' in role else 0.)),
        away_table=_clamp(.15 + .50 * (1-close) + (.25 if chopper or '中远台' in role else 0.)),
        topspin_preference=_clamp(.55 + .20 * initiative + (.10 if '旋转' in role or '两面' in role else 0.) - (.35 if chopper else 0.)),
        backspin_control=_clamp(.20 + .45 * short + (.25 if chopper else 0.)),
        spin_variation=_clamp(.20 + .55 * unusual + .20 * short), initiative=initiative,
        counterattack=_clamp(.25 + .40 * (1-initiative) + .20 * unusual + (.15 if chopper else 0.)), risk=risk)
    source_pid = card.get('source_person_id', card['player_id'].removesuffix('_age18'))
    year = _year(card)
    priors = _library()['players'].get(source_pid, {}).get('curated_style_priors', [])
    eligible = [p for p in priors if year is not None and p['effective_from'] <= year <= p['effective_through']]
    curated = max(eligible, key=lambda p: p['effective_from']) if eligible else None
    if curated:
        if curated.get('classification') != 'CURATED_GAME_DESIGN_PRIOR' or not set(curated['axes']) <= set(AXES):
            raise ValueError('invalid curated style design prior')
        for key, value in curated['axes'].items():
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('invalid curated style axis')
            axes[key] = float(value)
        bh, risk = axes['backhand_use'], axes['risk']
    phase = max(('short_game', 'first_three', 'rally', 'away_table'), key=lambda k: axes[k])
    names = dict(short_game='台内组织偏好', first_three='前三板抢先偏好', rally='连续相持偏好', away_table='离台周旋偏好')
    broad = curated['class_label'] if curated else '削球与反攻组织' if chopper else names[phase]
    side = '正手组织偏好' if bh <= .43 else '反手组织偏好' if bh >= .57 else '两面调配偏好'
    spin = '下旋控制偏好' if axes['backspin_control'] > axes['topspin_preference'] else '上旋衔接偏好'
    tempo = '控制风险偏好' if risk <= .38 else '主动试探偏好' if risk >= .62 else '择机加速偏好'
    methods = dict(short_game='先通过台内控制争取后续主动', first_three='争取在发接发和起板阶段建立优势',
                   rally='愿意延长连续对抗并从衔接中寻找机会', away_table='愿意用纵深与回合变化组织周旋')
    result = dict(version=STYLE_VERSION, axes=axes, class_label=broad,
        labels=[broad, side, spin, tempo], preferred_methods=[methods[phase],
            '更常用反手组织来回' if bh >= .57 else '更常用正手组织来回' if bh <= .43 else '按局面在两面之间调配',
            '用控制与变化等待反攻窗口' if chopper else '根据来球调整主动与控制的比例'],
        provenance=dict(classification='MODELLED_FROM_SNAPSHOT_ASSESSMENT',
            source_fields=['tendencies', 'role', 'style'], source_snapshot_year=_year(card),
            method='OBSERVABLE_PREFERENCE_MAPPING_V118_1',
            research_document='docs/V118_RESEARCH_ZH.md',
            parameter_status='GAME_DESIGN_NOT_EMPIRICALLY_FITTED',
            ability_independent=True, future_titles_not_used=True),
        confidence='MODELLED_NOT_HISTORICALLY_CERTIFIED', as_of_year=_year(card),
        semantics='PREFERENCE_NOT_SKILL_OR_AUTOMATIC_ACTION')
    if curated:
        result['provenance'].update(classification='CURATED_GAME_DESIGN_PRIOR',
            design_prior_id=curated['id'], effective_from=curated['effective_from'],
            effective_through=curated['effective_through'],
            interpretation_limit=curated['interpretation_limit'])
    return result


def _personality(card, seed):
    pid = card['player_id']
    source_pid = card.get('source_person_id', pid.removesuffix('_age18'))
    row = _library()['players'].get(source_pid, {})
    declared = card.get('narrative_personality')
    if declared is not None:
        if not isinstance(declared, list) or not 1 <= len(declared) <= 6 or any(not isinstance(x, str) or not x.strip() or len(x) > 60 for x in declared):
            raise ValueError('narrative_personality needs 1..6 short fictional/user-declared traits')
        traits, basis = list(declared), 'USER_DECLARED_FICTION'
    else:
        traits = copy.deepcopy(row.get('simulation_traits') or _default_traits(pid, seed))
        basis = 'SIMULATED_NARRATIVE_DEFAULT'
    return dict(version=PERSONALITY_VERSION, subject_player_id=pid, visibility='NARRATOR_ONLY', basis=basis,
        simulation_traits=traits, public_cues=copy.deepcopy(row.get('public_cues', [])),
        provenance=dict(source_person_id=source_pid, default_status='FICTIONAL_WRITING_CHOICES_NOT_REAL_PERSONALITY_ASSESSMENT'),
        use_limit='NARRATIVE_REFERENCE_ONLY_NOT_OBSERVED_PRIVATE_CHARACTER',
        not_match_modifiers=True, not_a_psychological_diagnosis=True)


def _validate_style(style):
    if not isinstance(style, dict) or style.get('version') != STYLE_VERSION or set(style.get('axes', {})) != set(AXES):
        raise ValueError('complete V1.1.7 综合版 preference axes required')
    for key, value in style['axes'].items():
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f'preference axis {key} must be finite in 0..1')
    if not isinstance(style.get('labels'), list) or not 2 <= len(style['labels']) <= 4 or any(not isinstance(x, str) or not x for x in style['labels']):
        raise ValueError('2..4 observer labels required')
    if not isinstance(style.get('preferred_methods'), list) or not style['preferred_methods']:
        raise ValueError('preference descriptions required')


def prepare(card, seed=118):
    """Attach preference/personality metadata without changing numeric traits."""
    if type(seed) is not int:
        raise ValueError('integer narrative seed required')
    baseline.validate(card)
    out = copy.deepcopy(card)
    if 'style_profile' not in out:
        out['style_profile'] = _infer_style(out)
    _validate_style(out['style_profile'])
    if ('personality_profile' not in out or isinstance(out['personality_profile'], dict)
            and out['personality_profile'].get('subject_player_id') != out['player_id']):
        out['personality_profile'] = _personality(out, seed)
    personality = out['personality_profile']
    if not isinstance(personality, dict) or personality.get('version') != PERSONALITY_VERSION or personality.get('visibility') != 'NARRATOR_ONLY':
        raise ValueError('narrator-only V1.1.7 综合版 personality required')
    if personality.get('not_match_modifiers') is not True:
        raise ValueError('narrative personality cannot change match attributes')
    traits = personality.get('simulation_traits')
    if (not isinstance(traits, list) or not 1 <= len(traits) <= 6
            or any(not isinstance(x, str) or not x.strip() or len(x) > 60 for x in traits)):
        raise ValueError('personality simulation defaults required')
    if personality.get('basis') not in ('SIMULATED_NARRATIVE_DEFAULT', 'USER_DECLARED_FICTION'):
        raise ValueError('personality default must identify its fictional basis')
    if not isinstance(personality.get('public_cues', []), list) or any(not isinstance(x, dict) for x in personality.get('public_cues', [])):
        raise ValueError('public personality cues must be a list')
    canonical_json(out)
    return out


def normalize(profile, *, development_profile=None, seed=118):
    return prepare(baseline.normalize(profile, development_profile=development_profile), seed=seed)


def validate(card):
    baseline.validate(card)
    if 'style_profile' in card:
        _validate_style(card['style_profile'])
    if 'personality_profile' in card:
        prepare(card)
    return True


def get_preset(*args, **kwargs):
    return prepare(baseline.get_preset(*args, **kwargs))


def make_ma18():
    return prepare(baseline.make_ma18())


HIDDEN_FIELDS = frozenset(('personality_profile', 'narrative_personality', 'personality_guidance',
    'career117_profile', 'career118_profile', 'career_v117', 'career_v118',
    'development_profile', 'P_max', 'talent', 'neuromotor', 'mental', 'focus',
    'latent_target', 'latent_technical_caps', 'reachable_envelope', 'historical_reference',
    'champion_history_as_of_snapshot', 'legacy_growth_reference', 'technical_identity'))


def _public(value):
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items()
            if key not in HIDDEN_FIELDS and not any(token in key.lower() for token in ('private', 'hidden', 'latent', 'personality'))}
    if isinstance(value, list):
        return [_public(item) for item in value]
    return copy.deepcopy(value)


def public_view(card):
    """A complete observer card, with narrative/latent internals removed."""
    prepared = prepare(card)
    out = _public(prepared)
    if 'status_tags' in out:
        out['status_tags'] = [x for x in out['status_tags']
                              if not isinstance(x, str) or not ('champion' in x.lower() or 'prototype' in x.lower())]
    out['observer_contract'] = dict(style='PREFERENCE_NOT_PROFICIENCY',
        personality_visibility='NARRATOR_ONLY', future_development_parameters='HIDDEN')
    return out


def _source_date(cue):
    raw = cue.get('source_date') or cue.get('publication_date')
    year = cue.get('source_year', cue.get('publication_year'))
    if raw:
        try:
            result = date.fromisoformat(raw)
        except (TypeError, ValueError):
            return None
        if year is not None and (type(year) is not int or year != result.year):
            return None
        return result
    return date(year, 12, 31) if type(year) is int and 1900 <= year <= 2100 else None


def narrative_view(card, as_of_year=None, *, as_of_date=None):
    """Source-bounded writing guidance; never a private-character fact claim."""
    prepared = prepare(card)
    if as_of_date is not None:
        cutoff = date.fromisoformat(as_of_date) if isinstance(as_of_date, str) else as_of_date
        if not isinstance(cutoff, date) or as_of_year is not None and cutoff.year != as_of_year:
            raise ValueError('consistent narrative date/year required')
        year, precision = cutoff.year, 'EXACT_DATE'
    else:
        year = _year(prepared) if as_of_year is None else as_of_year
        if type(year) is not int or not 1900 <= year <= 2100:
            raise ValueError('explicit narrative year required')
        cutoff, precision = date(year, 12, 31), 'YEAR_END'
    if _year(prepared) is not None and year < _year(prepared):
        raise ValueError('future card snapshot cannot narrate an earlier world')
    if prepared.get('snapshot_date'):
        try:
            snapshot = date.fromisoformat(prepared['snapshot_date'])
        except (TypeError, ValueError) as error:
            raise ValueError('valid card snapshot date required for narration') from error
        if snapshot > cutoff:
            raise ValueError('future card snapshot date cannot narrate an earlier world')
    personality = prepared['personality_profile']
    cues = []
    for cue in personality.get('public_cues', []):
        source_date = _source_date(cue)
        if (source_date is not None and source_date <= cutoff and cue.get('source_url')
                and cue.get('source_id') and cue.get('basis') in ('PUBLIC_SELF_DESCRIPTION', 'PUBLIC_PRESENTATION')
                and cue.get('verification_status') in ('VERIFIED_PUBLIC_PRIMARY_SOURCE', 'VERIFIED_PUBLIC_TRANSCRIPT')):
            value = copy.deepcopy(cue)
            value.update(available_from=source_date.isoformat(), classification='PUBLIC_SOURCE_LIMITED_CUE')
            cues.append(value)
    basis = ('PUBLIC_PRESENTATION_CUES_AND_SIMULATED_DEFAULTS' if cues else personality['basis'])
    guidance = dict(visibility='NARRATOR_ONLY', basis=basis, public_cues=cues,
        simulation_traits=copy.deepcopy(personality['simulation_traits']),
        use_limit=personality['use_limit'], not_match_modifiers=True,
        not_a_psychological_diagnosis=True,
        caution='公开表达只供有限参考；模拟默认词不是现实私人人格事实。')
    return dict(player_id=prepared['player_id'], name_zh=prepared.get('name_zh', prepared['player_id']),
        as_of_year=year, as_of_date=cutoff.isoformat(), temporal_precision=precision,
        style_profile=copy.deepcopy(prepared['style_profile']), personality_guidance=guidance)


def audit_library(seed=118):
    presets = json.loads((ROOT / 'data/presets_normalized.json').read_text())['profiles']
    library = _library()
    rows, preserved, axis_profiles, classes, curated_count = [], 0, set(), Counter(), 0
    numeric = ('children', 'P6', 'G9', 'CA', 'PA')
    for card in presets:
        value = prepare(card, seed)
        same = all(value[key] == card[key] for key in numeric)
        preserved += int(same)
        axis_profiles.add(tuple(value['style_profile']['axes'][key] for key in AXES))
        classes[value['style_profile']['class_label']] += 1
        curated_count += int(value['style_profile']['provenance']['classification'] == 'CURATED_GAME_DESIGN_PRIOR')
        rows.append(dict(player_id=card['player_id'], year=card['year'], numeric_preserved=same,
            labels=value['style_profile']['labels'], confidence=value['style_profile']['confidence']))
    return dict(version=VERSION, status='OBSERVER_PROFILE_AUDIT_PASSED' if preserved == len(presets) else 'FAILED',
        snapshot_count=len(presets), player_count=len({x['player_id'] for x in presets}),
        library_player_count=len(library['players']), snapshots_preserving_numeric_traits=preserved,
        unique_axis_profiles=len(axis_profiles), class_distribution=dict(classes),
        snapshots_using_curated_design_prior=curated_count,
        curated_player_design_priors=sum(bool(x.get('curated_style_priors')) for x in library['players'].values()),
        individuality_limit='Shared base archetypes remain; unique preference vectors are not individually measured athlete profiles.',
        public_personality_policy='NEVER_EXPOSED',
        personality_sources='PUBLIC_CUES_WHERE_AVAILABLE_OTHERWISE_EXPLICIT_SIMULATION_DEFAULTS',
        results=rows)
