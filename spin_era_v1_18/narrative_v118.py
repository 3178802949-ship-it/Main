"""Evidence-bound Chinese narration; style guidance never becomes match fact.

This module performs no game, training or ranking settlement. Hashes establish
content integrity, not authorship or a claim that simulated events are history.
"""
from __future__ import annotations

import copy
from datetime import date
import hashlib
import math
import random
import re

from common import canonical_json

VERSION = 'V1.1.7-COMPREHENSIVE-NARRATIVE-1'
MATCH_RULESETS = frozenset(('V1.1.7-CANDIDATE-1', 'V1.1.7-COMPREHENSIVE-1'))
HISTORY_LIMIT = 12
RESULT_TEMPLATES = (
    '{a}与{b}的本场模拟以{score}结束，胜者是{winner}。',
    '本次对抗已结算：{winner}赢下比赛，双方局数为{score}。',
    '{winner}取得本场胜利；赛果记录为{a} {score} {b}。',
    '结果账本记下了{winner}的胜场，{a}和{b}的局数是{score}。',
    '这场模拟的最终结果已经确定：{winner}获胜，局数{score}。',
    '本场对抗告一段落，{winner}胜出；双方局数定格为{score}。',
    '赛果收据显示，{a}对{b}打出{score}，获胜一方为{winner}。',
    '从结算结果看，胜利归于{winner}，两人的局数为{score}。',
)
FAMILY_ZH = dict(serve='发球', attack='进攻', open='起板', counter='反击',
                 flip='挑打或拧拉', slow_loop='控制弧圈', chop='削球',
                 push='搓摆控制', block='挡球', lob='放高球')


def _hash(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _seed(seed):
    if type(seed) is not int:
        raise ValueError('integer narration seed required')
    return random.Random(int.from_bytes(hashlib.sha256(f'{VERSION}:{seed}'.encode()).digest()[:8], 'big'))


def _finite(value, label, minimum=None):
    if type(value) not in (int, float) or not math.isfinite(value) or minimum is not None and value < minimum:
        raise ValueError(f'invalid {label}')


def _verify_match(value):
    if not isinstance(value, dict) or value.get('ruleset') not in MATCH_RULESETS:
        raise ValueError('supported bound V1.1.7/V1.1.7 综合版 match required')
    proposed = copy.deepcopy(value)
    expected = proposed.pop('log_sha256', None)
    if expected != _hash(proposed):
        raise ValueError('MATCH_LOG_HASH_MISMATCH')
    ids, games, won = value.get('participant_ids'), value.get('games'), value.get('games_won')
    if not isinstance(ids, list) or len(ids) != 2 or len(set(ids)) != 2 or any(not isinstance(x, str) or not x for x in ids):
        raise ValueError('two distinct participant identities required')
    if type(value.get('winner')) is not int or value['winner'] not in (0, 1):
        raise ValueError('invalid match winner')
    if not isinstance(games, list) or not 1 <= len(games) <= 7 or not isinstance(won, list) or len(won) != 2 or any(type(n) is not int or n < 0 for n in won):
        raise ValueError('invalid game totals')
    target = won[value['winner']]
    if target not in (2, 3, 4):
        raise ValueError('complete BO3/BO5/BO7 result required')
    counts = [0, 0]
    for gi, game in enumerate(games):
        score, winner = game.get('score'), game.get('winner')
        if not isinstance(score, list) or len(score) != 2 or any(type(n) is not int or n < 0 for n in score):
            raise ValueError('invalid game score')
        if type(winner) is not int or winner not in (0, 1):
            raise ValueError('invalid game winner')
        high, low = score[winner], score[1-winner]
        if not ((high == 11 and low <= 9) or (high >= 12 and high - low == 2)):
            raise ValueError('illegal 11-point/two-clear game')
        counts[winner] += 1
        if max(counts) >= target and gi != len(games) - 1:
            raise ValueError('match continued after its winning target was reached')
    if counts != won or won[value['winner']] <= won[1-value['winner']]:
        raise ValueError('game and match winners disagree')
    if 'points' in value and (type(value['points']) is not int or value['points'] != sum(sum(g['score']) for g in games)):
        raise ValueError('point total disagrees with game scores')
    if 'mean_strokes' in value:
        _finite(value['mean_strokes'], 'mean strokes', 0)
    if value.get('mode') == 'summary' and any('points' in g for g in games):
        raise ValueError('aggregate receipt must not embed point chronology')
    return True


def _resolve(source, path):
    if not isinstance(path, str) or not path.startswith('$'):
        raise ValueError('JSON evidence path required')
    tokens = re.findall(r'\.([^\.\[\]]+)|\[(\d+)\]', path[1:])
    if ''.join('.' + name if name else '[' + index + ']' for name, index in tokens) != path[1:]:
        raise ValueError('invalid evidence path')
    value = source
    for name, index in tokens:
        value = value[name] if name else value[int(index)]
    return value


class _Builder:
    def __init__(self):
        self.sources, self.source_hashes, self.facts, self.evidence, self.sentences = {}, {}, [], {}, []

    def source(self, key, value):
        self.sources[key] = value
        self.source_hashes[key] = _hash(value)

    def fact(self, key, source, path, *, kind=None):
        ref = f'{source}:{path}'
        self.evidence[ref] = dict(source=source, source_sha256=self.source_hashes[source], path=path)
        value = copy.deepcopy(_resolve(self.sources[source], path))
        self.facts.append(dict(id=key, kind=kind or key, value=value, evidence_refs=[ref]))
        return value

    def sentence(self, text, *fact_ids):
        self.sentences.append(dict(text=text, fact_ids=list(fact_ids)))

    def result(self, *, scope, warnings=(), **extra):
        return dict(version=VERSION, text=''.join(s['text'] for s in self.sentences),
            sentences=self.sentences, facts=self.facts, evidence=self.evidence,
            narrative_scope=scope, warnings=list(warnings),
            integrity_limit='CONTENT_HASH_AND_SCHEMA_CHECKS_NOT_AUTHOR_AUTHENTICATION', **extra)


def _history(history, rng):
    history = copy.deepcopy(history or {})
    recent = history.get('recent_templates', [])
    if not isinstance(recent, list) or any(type(x) is not int or not 0 <= x < len(RESULT_TEMPLATES) for x in recent):
        raise ValueError('invalid bounded narration history')
    choices = [i for i in range(len(RESULT_TEMPLATES)) if i not in recent[-3:]]
    selected = rng.choice(choices)
    return selected, dict(version=VERSION, recent_templates=(recent + [selected])[-HISTORY_LIMIT:])


def preview_profile(card, *, as_of_year, as_of_date=None):
    """Narrator-only preferences and labelled cues, separate from event facts."""
    if type(as_of_year) is not int:
        raise ValueError('explicit observation year required')
    from Card import v118 as Card
    view = Card.narrative_view(card, as_of_year=as_of_year, as_of_date=as_of_date)
    return dict(visibility='NARRATOR_ONLY', guidance=view,
                use_limit='PREFERENCES_AND_LABELLED_CUES_NOT_MATCH_CAUSAL_EVIDENCE')


def _observation(as_of_year, as_of_date, era=None):
    if as_of_date is None and isinstance(era, dict) and isinstance(era.get('as_of'), str):
        candidate = date.fromisoformat(era['as_of'])
        if as_of_year is None or as_of_year == candidate.year:
            as_of_date = candidate.isoformat()
    if as_of_date is not None:
        parsed = date.fromisoformat(as_of_date)
        if as_of_year is not None and (type(as_of_year) is not int or parsed.year != as_of_year):
            raise ValueError('observation year/date disagree')
        as_of_year = parsed.year
    if as_of_year is not None and type(as_of_year) is not int:
        raise ValueError('integer observation year required')
    return as_of_year, as_of_date


def _era(builder, era, as_of_year, warnings, as_of_date=None):
    if era is None:
        return
    if type(as_of_year) is not int:
        warnings.append('ERA_WITHHELD_WITHOUT_OBSERVATION_YEAR')
        return
    context = era.get('era', era)
    if not isinstance(context, dict):
        raise ValueError('era context must contain an era object')
    if as_of_date is not None and era.get('as_of') and date.fromisoformat(era['as_of']) > date.fromisoformat(as_of_date):
        warnings.append('ERA_CONTEXT_OUTSIDE_OBSERVATION_DATE_WITHHELD')
        return
    start = context.get('start_year', context.get('year', as_of_year))
    end = context.get('end_year_exclusive', as_of_year + 1)
    future = context.get('as_of_year', context.get('year', start))
    if any(type(x) is not int for x in (start, end, future)) or not start <= as_of_year < end or future > as_of_year:
        warnings.append('ERA_CONTEXT_OUTSIDE_OBSERVATION_DATE_WITHHELD')
        return
    theme = context.get('theme_zh')
    if not isinstance(theme, str) or not theme:
        warnings.append('ERA_THEME_UNAVAILABLE')
        return
    builder.source('era', era)
    builder.fact('era_theme', 'era', '$.era.theme_zh' if 'era' in era else '$.theme_zh', kind='DESIGN_CONTEXT_NOT_HISTORICAL_PROOF')
    builder.sentence(f'本世界采用的时代主题为“{theme}”。', 'era_theme')


def render_match(log, cards=None, *, seed=118, era=None, detail_artifact=None,
                 as_of_year=None, as_of_date=None, history=None):
    """Narrate a verified score receipt; full detail requires the exact artifact."""
    _verify_match(log)
    as_of_year, as_of_date = _observation(as_of_year, as_of_date, era)
    rng, out, warnings = _seed(seed), _Builder(), []
    out.source('match', log)
    ids = out.fact('participants', 'match', '$.participant_ids')
    winner = out.fact('winner', 'match', '$.winner')
    won = out.fact('games_won', 'match', '$.games_won')
    names, profile_guidance, name_facts = list(ids), [], []
    if cards is not None:
        if not isinstance(cards, (list, tuple)) or len(cards) != 2 or [c.get('player_id') for c in cards] != ids:
            raise ValueError('narrative cards must match log participant order')
        out.source('cards', list(cards))
        for i, card in enumerate(cards):
            if isinstance(card.get('name_zh'), str) and card['name_zh']:
                key = f'display_name_{i}'
                names[i] = out.fact(key, 'cards', f'$[{i}].name_zh', kind='CALLER_PROVIDED_IDENTITY_LABEL')
                name_facts.append(key)
            if as_of_year is not None:
                profile_guidance.append(preview_profile(card, as_of_year=as_of_year, as_of_date=as_of_date))
        if as_of_year is None:
            warnings.append('PROFILE_GUIDANCE_WITHHELD_WITHOUT_OBSERVATION_YEAR')
    if names[0] == names[1]:
        names = [f'{names[i]}[{"AB"[i]}:{ids[i]}]' for i in (0, 1)]
    template, next_history = _history(history, rng)
    out.sentence(RESULT_TEMPLATES[template].format(a=names[0], b=names[1],
        winner=names[winner], score=f'{won[0]}:{won[1]}'), 'participants', 'winner', 'games_won', *name_facts)
    if 'mean_strokes' in log:
        estimated = log.get('mode') == 'summary' and log.get('source_mode') != 'full'
        mean = out.fact('mean_strokes', 'match', '$.mean_strokes', kind='ESTIMATED_AGGREGATE' if estimated else 'RECORDED_AGGREGATE')
        out.sentence(f'{"聚合估计" if estimated else "记录汇总"}平均每分{mean:.2f}板。', 'mean_strokes')
    family = log.get('action_family_distribution', {})
    if not isinstance(family, dict) or any(type(n) is not int or n < 0 for n in family.values()):
        raise ValueError('invalid action-family summary')
    candidates = {k: n for k, n in family.items() if k != 'serve' and n > 0}
    if candidates:
        estimated = log.get('mode') == 'summary' and log.get('source_mode') != 'full'
        out.fact('action_families', 'match', '$.action_family_distribution', kind='ESTIMATED_AGGREGATE' if estimated else 'RECORDED_AGGREGATE')
        common = sorted(candidates, key=lambda k: (-candidates[k], k))[0]
        label = FAMILY_ZH.get(common, common)
        out.sentence(f'在{"聚合抽样列出" if estimated else "已记录"}的非发球动作家族中，{label}是使用最多的家族之一。', 'action_families')
    trajectory, source_key = None, 'match'
    if detail_artifact is not None:
        _verify_match(detail_artifact)
        if log.get('full_log_sha256') != detail_artifact['log_sha256']:
            raise ValueError('FULL_ARTIFACT_HASH_OR_REFERENCE_MISMATCH')
        for key in ('world_id', 'match_id', 'participant_ids', 'seed', 'ruleset', 'winner', 'games_won'):
            if log.get(key) != detail_artifact.get(key):
                raise ValueError('FULL_ARTIFACT_IDENTITY_MISMATCH')
        trajectory, source_key = detail_artifact, 'detail'
        out.source(source_key, trajectory)
    elif log.get('mode') == 'full':
        trajectory = log
    has_detail = trajectory is not None and trajectory.get('mode') == 'full' and any(
        isinstance(g.get('points'), list) and g['points'] for g in trajectory['games'])
    if has_detail:
        choices = [(gi, pi, si) for gi, game in enumerate(trajectory['games'])
            for pi, point in enumerate(game.get('points', [])) for si, shot in enumerate(point.get('shots', []))
            if shot.get('player') in (0, 1) and shot.get('action') not in (None, 'serve', 'unreached')]
        if choices:
            gi, pi, si = rng.choice(choices)
            path = f'$.games[{gi}].points[{pi}].shots[{si}]'
            shot = out.fact('executed_shot', source_key, path, kind='EXECUTED_SHOT')
            before_path = f'$.games[{gi}].points[{pi}].score_before'
            before = out.fact('shot_score_before', source_key, before_path)
            technique = shot.get('technique_label', shot['action'])
            out.sentence(f'逐板记录中，第{gi+1}局局分{before[0]}:{before[1]}时，'
                         f'{names[shot["player"]]}使用了{technique}。', 'executed_shot', 'shot_score_before', *name_facts)
        scope = 'EXECUTED_SHOTS_ONLY'
    else:
        scope = 'AGGREGATE_ONLY'
        warnings.append('NO_SHOT_CHRONOLOGY_AVAILABLE_OR_AUTHORIZED')
        if log.get('source_mode') == 'full' or log.get('mode') == 'full':
            warnings.append('FULL_ARTIFACT_NOT_ATTACHED_RESULT_AND_TRENDS_ONLY')
        if 'LIGHT' in log.get('engine', ''):
            warnings.append('EXPOSURE_MOVEMENT_AND_RALLIES_ARE_AGGREGATE_ESTIMATES')
    _era(out, era, as_of_year, warnings, as_of_date)
    return out.result(scope=scope, warnings=warnings, history=next_history,
        template_id=template, profile_guidance=profile_guidance,
        participant_display_labels=names,
        fictional_atmosphere=dict(visibility='OPTIONAL_FICTION_NOT_EVENT_FACT', text='',
            guidance='可以另外描写明确标注为虚构的场馆氛围，不补造私下对话或内心动机。'))


def render_training(receipt, *, seed=118, era=None, as_of_year=None, as_of_date=None, expected_sha256=None):
    """Describe the supplied settlement; never settle or manufacture rewards."""
    _seed(seed)
    as_of_year, as_of_date = _observation(as_of_year, as_of_date, era)
    if not isinstance(receipt, dict):
        raise ValueError('training receipt object required')
    if expected_sha256 is not None and _hash(receipt) != expected_sha256:
        raise ValueError('TRAINING_RECEIPT_HASH_MISMATCH')
    out, warnings = _Builder(), []
    out.source('training', receipt)
    nested = isinstance(receipt.get('receipt'), dict)
    core, prefix = (receipt['receipt'], '$.receipt') if nested else (receipt, '$')
    if core.get('mode') not in ('train', 'rest'):
        raise ValueError('settled training/rest mode required')
    mode = out.fact('mode', 'training', prefix + '.mode')
    out.sentence('本阶段已按休整结算。' if mode == 'rest' else '本阶段训练已完成结算。', 'mode')
    if all(k in core for k in ('CA_before', 'CA_after')):
        a = out.fact('CA_before', 'training', prefix + '.CA_before')
        b = out.fact('CA_after', 'training', prefix + '.CA_after')
        _finite(a, 'CA before', 0); _finite(b, 'CA after', 0)
        out.sentence(f'回执中的有效CA由{a}变为{b}。', 'CA_before', 'CA_after')
    changes_key = 'skill_changes' if 'skill_changes' in core else 'child_changes' if 'child_changes' in core else None
    if changes_key:
        changes = out.fact('skill_changes', 'training', prefix + '.' + changes_key)
        if not isinstance(changes, (dict, list)):
            raise ValueError('technical changes must be a path map or recorded change list')
        if isinstance(changes, list) and any(not isinstance(row, dict) or not {'path', 'old', 'new'} <= set(row) for row in changes):
            raise ValueError('invalid technical change row')
        if changes:
            out.sentence(f'技术变化明细列出了{len(changes)}个子项，具体增量以回执为准。', 'skill_changes')
    if 'PA_after' in core:
        pa = out.fact('PA_after', 'training', prefix + '.PA_after')
        _finite(pa, 'PA after', 0)
        out.sentence(f'本次结算后的PA估值为{pa}。', 'PA_after')
    if nested and isinstance(receipt.get('world_settlement'), dict):
        summary = receipt['world_settlement']
        if 'receipt_sha256' in summary and summary['receipt_sha256'] != _hash(core):
            raise ValueError('WORLD_TRAINING_RECEIPT_BINDING_MISMATCH')
        if 'fatigue_after' in summary:
            fatigue = out.fact('fatigue_after', 'training', '$.world_settlement.fatigue_after')
            _finite(fatigue, 'fatigue', 0)
            out.sentence(f'阶段结束时疲劳为{fatigue:.2f}。', 'fatigue_after')
    if expected_sha256 is None:
        warnings.append('CALLER_SUPPLIED_RECEIPT_CONTENT_HASH_IS_NOT_WORLD_AUTHENTICATION')
    _era(out, era, as_of_year, warnings, as_of_date)
    return out.result(scope='SETTLED_RECEIPT_ONLY', warnings=warnings,
        settlement_performed=False, reward_policy='NO_REWARD_OR_ABILITY_AWARDED_BY_NARRATION')


def verify_evidence(narration, sources):
    """Read-only evidence audit using original input documents supplied by caller."""
    facts = {f['id']: f for f in narration['facts']}
    if len(facts) != len(narration['facts']):
        raise ValueError('duplicate narrative fact identity')
    hashes = {key: _hash(value) for key, value in sources.items()}
    for fact in facts.values():
        refs = fact.get('evidence_refs', [])
        if len(refs) != 1:
            raise ValueError('each fact needs one exact source reference')
        evidence = narration['evidence'][refs[0]]
        source = sources[evidence['source']]
        if hashes[evidence['source']] != evidence['source_sha256'] or canonical_json(_resolve(source, evidence['path'])) != canonical_json(fact['value']):
            raise ValueError('NARRATIVE_EVIDENCE_MISMATCH')
    if any(not s.get('fact_ids') or not set(s['fact_ids']) <= set(facts) for s in narration['sentences']):
        raise ValueError('unreferenced narrative sentence')
    if narration['text'] != ''.join(s['text'] for s in narration['sentences']):
        raise ValueError('narrative text and sentence ledger disagree')
    return True
