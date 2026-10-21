"""Predeclared, paired old/new BO7 regression; no historical winner targets.

Each pairing receives the same cards and the same consecutive seeds in both
rulesets. Equipment supplied here is an experimental assumption, not an edit to
the source archive. Xu's requested 2013 context explicitly uses the unchanged
2012 prior snapshot because no certified 2013 snapshot exists in this archive.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Card
import Game
from common import canonical_json

PATCH_RULESET = 'V1.1.6-HGR-CANDIDATE-1'
BASE_SEED = 11616000
CASE_NAMES = ('schlager2003_joo2003', 'xu2013_context_joo2003', 'ma2016_fan2024', 'equal_right_left')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def numeric_traits(card):
    """Primitive ability fields the experiment is forbidden to tune."""
    return {key: copy.deepcopy(card[key]) for key in ('children', 'P6', 'PA')}


def _equipped(card, hand, fh='inverted', bh='inverted'):
    result = copy.deepcopy(card)
    before = numeric_traits(result)
    result['hand'] = hand
    result['rubbers'] = dict(fh=fh, bh=bh)
    result['simulation_equipment_assumption'] = dict(
        classification='EXPERIMENTAL_INPUT_NOT_CERTIFIED_HISTORICAL_EQUIPMENT',
        source='Predeclared HGR regression fixture; archive does not specify hand/rubbers.',
        hand=hand, rubbers=dict(fh=fh, bh=bh))
    assert numeric_traits(result) == before
    return result


def fixtures():
    """Return independent legal match cards plus explicit provenance diagnostics."""
    raw = json.loads((ROOT / 'data/original/spin_era_v016_schlager2003_joo2003_cards.json').read_text())
    experimental = {}
    diagnostics = []
    for key, label, nation, age, style in (
            ('schlager', '施拉格2003独立实验卡', '奥地利', 31, 'attacker'),
            ('joo', '朱世赫2003独立削球实验卡', '韩国', 23, 'modern_chopper')):
        source = copy.deepcopy(raw[key])
        source.update(player_id=f'{key}_2003_experimental', name_zh=label, nation_prototype=nation,
            year=2003, age_approx=age, style=style, classification='ASSESSMENT',
            source_prototype='EXPERIMENTAL_NOT_CERTIFIED_ANNUAL_SNAPSHOT')
        normalized = Card.normalize(source)
        assert numeric_traits(source) == numeric_traits(normalized)
        diagnostics.append(dict(player_id=normalized['player_id'], original_stored_CA=source['CA'],
            computed_CA=normalized['CA'], stored_G9_consistent=source['G9'] == normalized['G9'],
            original_source_numeric_digest=hashlib.sha256(canonical_json({k: source[k] for k in ('children', 'P6', 'G9', 'CA', 'PA')}).encode()).hexdigest(),
            normalized_numeric_digest=hashlib.sha256(canonical_json({k: normalized[k] for k in ('children', 'P6', 'G9', 'CA', 'PA')}).encode()).hexdigest(),
            raw_43_subskills_and_P6_preserved=True,
            note='Derived aggregates use the existing frozen formula in both old and new runs; no child/P6 tuning.'))
        experimental[key] = normalized
    try:
        xu = Card.get_preset('xu_xin', 2013)
        xu_selection = dict(mode='EXACT_SNAPSHOT', source_year=2013, context_year=2013)
    except ValueError:
        xu = Card.get_preset('xu_xin', 2012)
        xu_selection = dict(mode='PRIOR_BASELINE_NOT_GROWN', source_year=2012, context_year=2013,
            note='No 2013 snapshot supplied. 2012 numeric values retained; no interpolation or growth settlement.')
    xu = copy.deepcopy(xu)
    xu['benchmark_context'] = copy.deepcopy(xu_selection)
    left_control = Card.make_ma18()
    left_control['player_id'] = 'equal_left_experimental'
    left_control['name_zh'] = '同值左手实验控制卡'
    right_control = copy.deepcopy(left_control)
    right_control['player_id'] = 'equal_right_experimental'
    right_control['name_zh'] = '同值右手实验控制卡'
    cards = dict(
        schlager2003_joo2003=[_equipped(experimental['schlager'], 'right'),
            _equipped(experimental['joo'], 'right', bh='long_pips')],
        xu2013_context_joo2003=[_equipped(xu, 'left'),
            _equipped(experimental['joo'], 'right', bh='long_pips')],
        ma2016_fan2024=[_equipped(Card.get_preset('ma_long', 2016), 'right'),
            _equipped(Card.get_preset('fan_zhendong', 2024), 'right')],
        equal_right_left=[_equipped(right_control, 'right'), _equipped(left_control, 'left')])
    labels = dict(schlager2003_joo2003='施拉格2003／朱世赫2003实验卡',
        xu2013_context_joo2003='许昕2013情境（2012旧快照基线）／朱世赫2003实验卡',
        ma2016_fan2024='马龙2016／樊振东2024：普通反胶进攻对照',
        equal_right_left='相同能力右手／左手：实验几何控制')
    for item in diagnostics:
        card = next(card for pair in cards.values() for card in pair if card['player_id'] == item['player_id'])
        item['normalized_match_digest'] = hashlib.sha256(canonical_json(card).encode()).hexdigest()
    return dict(cards=cards, labels=labels, source_diagnostics=diagnostics, xu_selection=xu_selection)


def seed_plan(count):
    if type(count) is not int or count < 1:
        raise ValueError('seed count must be a positive integer')
    return {name: list(range(BASE_SEED + index * 1000, BASE_SEED + index * 1000 + count))
            for index, name in enumerate(CASE_NAMES)}


def _quality(shot):
    value = shot.get('out_quality', shot.get('quality'))
    return value if type(value) in (int, float) and math.isfinite(value) else None


def _side(shot):
    side = shot.get('stroke_side')
    if side in ('fh', 'bh'):
        return side
    action = shot.get('action', '')
    if action.startswith(('fh_', 'bh_')):
        return action[:2]
    if _is_chop(shot) and shot.get('input_target') in ('fh', 'bh'):
        return shot['input_target']
    return 'unknown'


def _is_chop(shot):
    return shot.get('action_family') in ('chop', 'specialist_chop') or shot.get('action') in (
        'chop', 'chop_transition', 'fh_chop', 'bh_chop', 'fh_specialist_chop', 'bh_specialist_chop') or (
        '_lp_chop' in shot.get('action', ''))


def _is_attack(shot):
    family = shot.get('action_family', '')
    action = shot.get('action', '')
    return family in ('attack', 'open', 'counter', 'loop', 'counterattack', 'punch', 'flick', 'flip') or any(
        token in action for token in ('attack', 'counter', 'open', 'flip', 'loop', 'punch', 'flick', 'drive'))


def _number(mapping, *keys):
    for key in keys:
        value = mapping.get(key)
        if type(value) in (int, float) and math.isfinite(value):
            return value
    return None


def _series(values):
    if not values:
        return dict(n=0, mean=None, minimum=None, maximum=None)
    return dict(n=len(values), mean=round(statistics.mean(values), 5),
                minimum=round(min(values), 5), maximum=round(max(values), 5))


def summarize_logs(logs, cards):
    """Summarize observed log fields; absent legacy geometry stays unavailable.

    Counterattack and loop-chop errors are event-sequence classifications, not
    claims that a real match was caused by a psychological or spin-reading error.
    """
    actions, reaches, scorelines, reasons, tactics, lines = (Counter() for _ in range(6))
    chop_quality, quality_by_reach, successful_chop_quality = defaultdict(list), defaultdict(list), defaultdict(list)
    chop_counts, chop_returns, loop_chop_errors = Counter(), Counter(), Counter()
    chop_errors, errors_by_reach, chop_direct_winners = Counter(), Counter(), Counter()
    attacks_after_chop, direct_winners_after_chop = Counter(), Counter()
    attack_winners, counterattacks, counterattack_winners = Counter(), Counter(), Counter()
    chopper_attacks, counterattack_sides, counterattack_winner_sides = Counter(), Counter(), Counter()
    distances, loads, strengths, recognition_risks = [], [], [], []
    by_player = {str(i): dict(actions=Counter(), reaches=Counter(), chop_side=Counter()) for i in (0, 1)}
    rallies, game_winners = [], Counter()
    explicit_spin_misread, movement_count, geometry_count, technique_count = 0, 0, 0, 0
    recognized_spin_samples = 0
    for match in logs:
        rallies.extend(match['rallies'])
        scorelines['-'.join(map(str, match['games_won']))] += 1
        for game in match['games']:
            game_winners[str(game['winner'])] += 1
            for point in game.get('points', []):
                reasons[point.get('reason', 'unknown')] += 1
                previous_chop = {0: False, 1: False}
                shots = point.get('shots', [])
                for index, shot in enumerate(shots):
                    player = shot.get('player')
                    if player not in (0, 1):
                        continue
                    ps = str(player)
                    action, reach = shot.get('action', 'unknown'), shot.get('reach')
                    actions[action] += 1
                    by_player[ps]['actions'][action] += 1
                    if reach in ('good', 'limited', 'bad', 'miss'):
                        reaches[reach] += 1
                        by_player[ps]['reaches'][reach] += 1
                        if shot.get('return_state') == 'direct_point_lost':
                            errors_by_reach[reach] += 1
                    quality = _quality(shot)
                    if quality is not None and reach in ('good', 'limited', 'bad'):
                        quality_by_reach[reach].append(quality)
                    if shot.get('technique_path'):
                        technique_count += 1
                    movement = shot.get('movement') or {}
                    geometry = shot.get('geometry') or {}
                    movement = movement if isinstance(movement, dict) else {}
                    geometry = geometry if isinstance(geometry, dict) else {}
                    if isinstance(movement, dict) and movement:
                        movement_count += 1
                    if isinstance(geometry, dict) and geometry:
                        geometry_count += 1
                    distance = _number(movement, 'distance_m', 'distance')
                    if distance is None:
                        distance = _number(geometry, 'distance_m', 'movement_distance_m')
                    if distance is not None:
                        distances.append(distance)
                    load = _number(movement, 'load_after', 'movement_load', 'load', 'rally_load')
                    if load is not None:
                        loads.append(load)
                    line = geometry.get('line_category', geometry.get('line_type', shot.get('line_category')))
                    if line:
                        lines[str(line)] += 1
                    tactic = shot.get('tactical_intent', shot.get('tactic'))
                    if isinstance(tactic, str):
                        tactics[tactic] += 1
                    target_policy = shot.get('targeting')
                    if isinstance(target_policy, dict) and target_policy.get('intent'):
                        tactics[str(target_policy['intent'])] += 1
                    strength = _number(shot, 'spin_strength')
                    if strength is not None:
                        strengths.append(strength)
                    risk = _number(shot, 'recognition_risk')
                    if risk is not None:
                        recognition_risks.append(risk)
                    recognition = shot.get('spin_recognition', shot.get('spin_reading'))
                    if recognition is not None:
                        recognized_spin_samples += 1
                        if isinstance(recognition, dict) and recognition.get('misread') is True:
                            explicit_spin_misread += 1
                    if _is_chop(shot):
                        side = _side(shot)
                        label = f'{ps}:{side}'
                        chop_counts[label] += 1
                        by_player[ps]['chop_side'][side] += 1
                        previous_chop[player] = True
                        chop_returns[f'{label}:{shot.get("return_state", "unknown")}'] += 1
                        if quality is not None:
                            chop_quality[f'{label}:{reach}'].append(quality)
                            if shot.get('return_state') != 'direct_point_lost':
                                successful_chop_quality[f'{label}:{reach}'].append(quality)
                        if shot.get('return_state') == 'direct_point_lost':
                            chop_errors[f'{label}:{reach}'] += 1
                    is_last = index == len(shots) - 1
                    is_winner = is_last and point.get('reason') == 'winner' and point.get('winner') == player
                    if is_winner and _is_chop(shot):
                        chop_direct_winners[ps] += 1
                    if _is_attack(shot):
                        if is_winner:
                            attack_winners[ps] += 1
                        if cards[player].get('style') == 'modern_chopper':
                            chopper_attacks[ps] += 1
                            if previous_chop[player]:
                                counterattacks[ps] += 1
                                counterattack_sides[f'{ps}:{_side(shot)}'] += 1
                                if is_winner:
                                    counterattack_winners[ps] += 1
                                    counterattack_winner_sides[f'{ps}:{_side(shot)}'] += 1
                        if index:
                            previous = shots[index - 1]
                            if _is_chop(previous) and previous.get('player') != player:
                                attacks_after_chop[ps] += 1
                                if is_winner:
                                    direct_winners_after_chop[ps] += 1
                                if is_last and shot.get('return_state') == 'direct_point_lost':
                                    loop_chop_errors[ps] += 1
    wins_a = sum(log['winner'] == 0 for log in logs)
    total_shots = sum(actions.values())
    total_reach = sum(reaches.values())
    per_player = {key: {field: dict(value) for field, value in item.items()} for key, item in by_player.items()}
    return dict(matches=len(logs), wins_A=wins_a, wins_B=len(logs) - wins_a,
        scoreline_distribution=dict(scorelines), total_games_by_winner=dict(game_winners),
        rally_length_distribution=dict(Counter(rallies)),
        rallies=len(rallies), mean_strokes=round(statistics.mean(rallies), 5) if rallies else None,
        median_strokes=statistics.median(rallies) if rallies else None,
        P_strokes_ge20=round(sum(v >= 20 for v in rallies) / len(rallies), 6) if rallies else None,
        actions=dict(actions), reaches=dict(reaches), reach_proportions={k: round(v / total_reach, 6) for k, v in reaches.items()} if total_reach else {},
        point_reasons=dict(reasons), chop_usage_by_player_and_side=dict(chop_counts),
        errors_by_reach=dict(errors_by_reach),
        failure_proportions_by_reach={k: round(errors_by_reach[k] / v, 6) for k, v in reaches.items()},
        chop_return_states=dict(chop_returns), chop_quality_by_player_side_reach={k: _series(v) for k, v in sorted(chop_quality.items())},
        successful_chop_quality_by_player_side_reach={k: _series(v) for k, v in sorted(successful_chop_quality.items())},
        chop_errors_by_player_side_reach=dict(chop_errors), chop_direct_winners_by_player=dict(chop_direct_winners),
        shot_quality_by_reach={k: _series(v) for k, v in sorted(quality_by_reach.items())},
        attacking_attempts_immediately_after_chop_by_player=dict(attacks_after_chop),
        attacking_direct_winners_immediately_after_chop_by_player=dict(direct_winners_after_chop),
        loop_chop_error_attempts_by_player=dict(loop_chop_errors),
        chopper_counterattack_attempts_by_player=dict(counterattacks),
        chopper_counterattack_direct_winners_by_player=dict(counterattack_winners),
        chopper_counterattack_attempts_by_player_side=dict(counterattack_sides),
        chopper_counterattack_direct_winners_by_player_side=dict(counterattack_winner_sides),
        chopper_active_attacks_by_player=dict(chopper_attacks),
        attacking_direct_winners_by_player=dict(attack_winners),
        line_categories=dict(lines), target_tactics=dict(tactics),
        movement_distance_m=_series(distances), movement_load=_series(loads),
        spin_strength=_series(strengths), recognition_risk=_series(recognition_risks), per_player=per_player,
        coverage=dict(shots=total_shots, movement_fields=movement_count, geometry_fields=geometry_count,
            technique_path_fields=technique_count, spin_recognition_fields=recognized_spin_samples,
            recognition_risk_fields=len(recognition_risks),
            explicit_spin_misread_events=explicit_spin_misread if recognized_spin_samples else None),
        classification_notes=[
            'Legacy movement/geometry/recognition absence is UNAVAILABLE, not a zero physical effect.',
            'Counterattack = chopper attacking after at least one own chop earlier in the same point.',
            'Chop quality is attempted-contact quality including contact errors; successful-return quality is separately reported.',
            'Loop-chop error = attacking shot lost directly immediately after an opponent chop; not proof of mental misread.'])


def _compact(log):
    return {key: copy.deepcopy(log[key]) for key in ('seed', 'match_id', 'winner', 'games_won',
        'points', 'total_strokes', 'mean_strokes', 'log_sha256', 'input_cards_sha256')}


def run(count=32, workers=4, output=None):
    if type(workers) is not int or workers < 1:
        raise ValueError('workers must be a positive integer')
    plan, inputs = seed_plan(count), fixtures()
    output = Path(output) if output else ROOT / 'reports/hgr_patch'
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('regression output is not empty; preserve earlier evidence and use a fresh directory')
    before = canonical_json(inputs['cards'])
    manifest = dict(classification='SIMULATED_MATCHED_SEED_REGRESSION_NOT_HISTORICAL_WIN_RATE',
        baseline_ruleset='V1.1.6-INTEGRATED-GAME', patch_ruleset=PATCH_RULESET, seeds_per_pair=count,
        pairings=list(CASE_NAMES), total_matches=8 * count, selection='CONSECUTIVE_PREDECLARED_SEEDS_NO_WIN_RATE_TARGET',
        seed_plan=plan, fixtures=inputs,
        fixture_sha256=hashlib.sha256(before.encode()).hexdigest(),
        source_sha256={str(p.relative_to(ROOT)): sha256(p) for p in sorted(
            list((ROOT / 'Game').glob('*.py')) + list((ROOT / 'runtime').glob('*.py')) + [Path(__file__)])},
        data_sha256={str(p.relative_to(ROOT)): sha256(p) for p in (ROOT / 'data').rglob('*.json')})
    (output / 'PREDECLARED_PLAN.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    tasks = [(name, seed, variant) for name in CASE_NAMES for seed in plan[name] for variant in ('old', 'new')]
    batches = {name: {variant: [] for variant in ('old', 'new')} for name in CASE_NAMES}
    compact = {name: {variant: [] for variant in ('old', 'new')} for name in CASE_NAMES}

    def execute(task):
        name, seed, variant = task
        options = dict(world_id='benchmark-hgr-cross-year-sandbox')
        if variant == 'new':
            options['ruleset'] = PATCH_RULESET
        log = Game.play_match(inputs['cards'][name], seed, f'hgr:{name}:{seed}', **options)
        Game.verify_log(log)
        if max(log['games_won']) != 4:
            raise AssertionError('not a completed BO7')
        return name, seed, variant, log

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, (name, seed, variant, log) in enumerate(pool.map(execute, tasks), 1):
            # Summaries are per-match here, so full logs do not accumulate in RAM.
            batches[name][variant].append(summarize_logs([log], inputs['cards'][name]))
            compact[name][variant].append(_compact(log))
            if seed == plan[name][0]:
                (output / f'{name}_{variant}_sample.json').write_text(json.dumps(log, ensure_ascii=False, indent=2))
            if index % 16 == 0 or index == len(tasks):
                print(f'{index}/{len(tasks)} paired BO7 executed', flush=True)
    assert canonical_json(inputs['cards']) == before
    summaries = {name: {variant: merge_summaries(batches[name][variant]) for variant in ('old', 'new')}
                 for name in CASE_NAMES}
    changes = {}
    for name in CASE_NAMES:
        a, b = compact[name]['old'], compact[name]['new']
        assert [m['seed'] for m in a] == [m['seed'] for m in b] == plan[name]
        assert all(x['input_cards_sha256'] == y['input_cards_sha256'] for x, y in zip(a, b))
        changes[name] = dict(paired_seeds=count, same_input_cards=True,
            winner_changed=sum(x['winner'] != y['winner'] for x, y in zip(a, b)),
            wins_A_delta=summaries[name]['new']['wins_A'] - summaries[name]['old']['wins_A'],
            mean_strokes_delta=round(summaries[name]['new']['mean_strokes'] - summaries[name]['old']['mean_strokes'], 5))
    report = dict(version=PATCH_RULESET, classification=manifest['classification'], total_matches=len(tasks),
        seeds_per_pair=count, seed_plan=plan, fixture_sha256=manifest['fixture_sha256'],
        source_sha256=manifest['source_sha256'], source_diagnostics=inputs['source_diagnostics'],
        xu_selection=inputs['xu_selection'], numeric_inputs_unchanged=True,
        same_seed_and_card_pairing_verified=True, summary=summaries, paired_changes=changes, matches=compact,
        samples='One complete executed log per pair and ruleset; all remaining runs have compact IDs/hashes/seeds.',
        limitations=['Experimental equipment is an explicit fixture assumption, not certified historical gear.',
            'Xu 2013 context uses the unchanged 2012 prior baseline when no 2013 archive exists.',
            'Finite regression samples measure behavior changes, not real historical win probabilities.',
            'No seed or numeric input is selected to match a historical score.'])
    (output / 'REGRESSION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    lines = ['# 左右手、胶皮与削球补丁｜固定种子回归', '',
        f'实际执行{len(tasks)}场BO7；每组{count}个连续固定种子，旧／新规则使用相同输入。', '',
        '| 实验组 | 旧A:B | 新A:B | 旧平均板数 | 新平均板数 | 新≥20板 |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name in CASE_NAMES:
        old, new = summaries[name]['old'], summaries[name]['new']
        lines.append(f'| {inputs["labels"][name]} | {old["wins_A"]}:{old["wins_B"]} | {new["wins_A"]}:{new["wins_B"]} | '
            f'{old["mean_strokes"]:.3f} | {new["mean_strokes"]:.3f} | {new["P_strokes_ge20"]:.2%} |')
    lines += ['', '详细局分、到位、正反手削球质量、移动、旋转及反攻统计见REGRESSION.json。', '',
        '许昕2013组明确采用2012旧快照基线，不是认证2013年度能力。装备/持拍手是预先声明的实验配置。',
        '朱世赫原实验卡存在旧聚合值不一致；沿用既有冻结公式重算，并在新旧两侧使用同一合法卡，所有43子值和P6保留。',
        '历史胜率不作为目标；零散胜场差异不能证明某项机制已完成现实校准。']
    (output / 'REGRESSION_REPORT_ZH.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({name: {v: {k: summaries[name][v][k] for k in ('wins_A', 'wins_B', 'mean_strokes')}
                            for v in ('old', 'new')} for name in CASE_NAMES}, ensure_ascii=False, indent=2))
    return report


def merge_summaries(items):
    """Combine per-match sufficient statistics without inventing missing fields."""
    if not items:
        raise ValueError('no match summaries')
    total_matches = sum(v['matches'] for v in items)
    result = copy.deepcopy(items[0])
    additive = ('matches', 'wins_A', 'wins_B', 'rallies')
    counters = ('scoreline_distribution', 'total_games_by_winner', 'rally_length_distribution', 'actions', 'reaches', 'point_reasons',
        'chop_usage_by_player_and_side', 'chop_return_states', 'loop_chop_error_attempts_by_player',
        'errors_by_reach', 'chop_errors_by_player_side_reach', 'chop_direct_winners_by_player',
        'attacking_attempts_immediately_after_chop_by_player', 'attacking_direct_winners_immediately_after_chop_by_player',
        'chopper_counterattack_attempts_by_player', 'chopper_counterattack_direct_winners_by_player',
        'chopper_counterattack_attempts_by_player_side', 'chopper_counterattack_direct_winners_by_player_side',
        'chopper_active_attacks_by_player',
        'attacking_direct_winners_by_player', 'line_categories', 'target_tactics')
    for key in additive:
        result[key] = sum(v[key] for v in items)
    for key in counters:
        combined = Counter()
        for row in items:
            combined.update(row[key])
        result[key] = dict(combined)
    total_rallies = result['rallies']
    histogram = result['rally_length_distribution']
    result['mean_strokes'] = round(sum(length * count for length, count in histogram.items()) / total_rallies, 5) if total_rallies else None
    result['P_strokes_ge20'] = round(sum(count for length, count in histogram.items() if length >= 20) / total_rallies, 6) if total_rallies else None
    if total_rallies:
        median_indices = {(total_rallies - 1) // 2, total_rallies // 2}
        cumulative, median_values = 0, []
        for length, count in sorted(histogram.items()):
            median_values.extend(length for index in median_indices if cumulative <= index < cumulative + count)
            cumulative += count
        result['median_strokes'] = statistics.mean(median_values)
    else:
        result['median_strokes'] = None
    reach_total = sum(result['reaches'].values())
    result['reach_proportions'] = {k: round(v / reach_total, 6) for k, v in result['reaches'].items()} if reach_total else {}
    result['failure_proportions_by_reach'] = {k: round(result['errors_by_reach'].get(k, 0) / v, 6) for k, v in result['reaches'].items()}
    for key in ('chop_quality_by_player_side_reach', 'successful_chop_quality_by_player_side_reach', 'shot_quality_by_reach'):
        labels = {label for row in items for label in row[key]}
        result[key] = {label: merge_series([row[key][label] for row in items if label in row[key]]) for label in sorted(labels)}
    for key in ('movement_distance_m', 'movement_load', 'spin_strength', 'recognition_risk'):
        result[key] = merge_series([row[key] for row in items])
    for ps in ('0', '1'):
        for field in ('actions', 'reaches', 'chop_side'):
            combined = Counter()
            for row in items:
                combined.update(row['per_player'][ps][field])
            result['per_player'][ps][field] = dict(combined)
    for key in result['coverage']:
        values = [row['coverage'][key] for row in items]
        result['coverage'][key] = sum(v for v in values if v is not None) if any(v is not None for v in values) else None
    assert result['matches'] == total_matches
    return result


def merge_series(series):
    available = [item for item in series if item['n']]
    if not available:
        return _series([])
    n = sum(item['n'] for item in available)
    return dict(n=n, mean=round(sum(item['n'] * item['mean'] for item in available) / n, 5),
        minimum=min(item['minimum'] for item in available), maximum=max(item['maximum'] for item in available))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=int, default=32)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/hgr_patch')
    args = parser.parse_args()
    run(args.seeds, args.workers, args.output)


if __name__ == '__main__':
    main()
