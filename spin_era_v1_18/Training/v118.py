"""New two-phase development with finite workload, age and fatigue on all gains."""
from __future__ import annotations

from collections import Counter
import copy
import math

from common import SCHEMA
import career_v116 as old
import career_v118 as career
from card_training_v112 import P, compute_card

VERSION = career.TRAINING_VERSION
GROUPS = tuple(SCHEMA['core_order'])


def initialize(card, seed=1, curve='balanced_progress', development_profile=None, start_age=None, config=None):
    if type(seed) is not int or curve not in career.CURVES:
        raise ValueError('integer seed and known growth prior required')
    strategy = config.get('strategy', career.DEFAULT_CONFIG) if isinstance(config, dict) else config or career.DEFAULT_CONFIG
    source = career.prepare_card(card, seed=seed, strategy=strategy)
    profile = source['development_profile']
    state = old.start(source, seed=seed, curve=curve, development_profile=profile)
    for key in ('learning_factor', 'style_preference'):
        if key in source:
            if set(source[key]) != set(career.PATHS) or any(career.finite(v, key, .01, 10) <= 0 for v in source[key].values()):
                raise ValueError('complete finite learning factors required')
            state[key] = copy.deepcopy(source[key])
    age = source.get('model_start_age', source.get('age_approx', source.get('age', 18))) if start_age is None else start_age
    career.finite(age, 'start_age', 10, 60)
    state['start_age'], state['age_offset'] = age, age - 18
    data = career.CURVES[curve]
    peak = career.clamp(career.rng_for(seed, 'peak', curve).gauss(data['peak'], data['sd']), 25.8, 30.8)
    p = source['career118_profile']
    state['career_v118'] = dict(p, initial_children={f'{g}.{k}': v for g, sub in source['children'].items() for k, v in sub.items()},
        peak_age=peak, maturity_mid=data['maturity'], activity_rate=data['rate'], body_loss_rate=data['bodyloss'],
        physiological_P=copy.deepcopy(source['P6']), age_loss_P=dict.fromkeys(P, 0.), formal_evidence=0,
        temporary_P_deficit=dict.fromkeys(P, 0.), temporary_recovery_start=dict.fromkeys(P, 0),
        potential_damage_total=0,
        year_start_CA=compute_card(source, SCHEMA)['CA_calculated'])
    # Preserve a late-career snapshot exactly while conditioning its future
    # trainable body room on the years already spent beyond its sampled peak.
    elapsed = max(0., age - peak)
    for key in P:
        vulnerability = dict(speed=1.25, burst=1.30, strength=.78, stamina=.90, agility=1.12, flexibility=.83)[key]
        prior_loss = (.35 * elapsed + .28 * elapsed ** 2.12 / 2.12) * vulnerability * data['bodyloss']
        state['career_v118']['age_loss_P'][key] = min(prior_loss, max(0, state['P_max'][key] - source['P6'][key]))
    state['career_v118']['initial_age_conditioning'] = 'OBSERVED_BODY_PRESERVED_WITH_AGE_CONDITIONED_TRAINABLE_ROOM'
    state['activity_rate'] = data['rate']
    state['version'] = career.VERSION
    state['peak_age'], state['decline_age'] = peak, peak
    state['training_release'] = dict(version=VERSION, phase=0, month=0, settled_phase_ids=[],
        settled_general=[], phase_log=[], monthly_aging=[], receipts_archived=0)
    state['card_metadata'] = {k: copy.deepcopy(source[k]) for k in ('name_zh', 'classification', 'origin', 'year') if k in source}
    return state


def _validate(state, plan, event_id):
    release = state.get('training_release', {})
    if release.get('version') != VERSION or release.get('month') != state['month']:
        raise ValueError('V1.1.7 综合版 training state required')
    if not isinstance(event_id, str) or not event_id or event_id in state['event_registry']:
        raise ValueError('DUPLICATE_OR_INVALID_TRAINING_EVENT')
    if not isinstance(plan, dict) or type(plan.get('month')) is not int or type(plan.get('phase')) is not int or (plan['month'], plan['phase']) != (state['month'], release['phase']):
        raise ValueError('PLAN_OUT_OF_SEQUENCE')
    if plan.get('mode', 'train') not in ('train', 'rest'):
        raise ValueError('invalid training mode')
    for key in ('training_fraction', 'recovery_fraction'):
        career.finite(plan.get(key, 1.), key, 0, 1)
    if plan.get('mode') == 'rest':
        if plan.get('technical') or plan.get('body'):
            raise ValueError('rest cannot contain training drills')
        return
    if plan['phase'] == 1 and state['month'] < state.get('rehab_until', 0):
        raise ValueError('REHABILITATION_PHASE_ONE_MUST_REST')
    technical = plan.get('technical')
    if not isinstance(technical, list) or len(technical) != 2:
        raise ValueError('choose two technical categories')
    groups = []
    for item in technical:
        if not isinstance(item, dict) or item.get('group') not in GROUPS:
            raise ValueError('invalid category')
        groups.append(item['group'])
        if 'specialize' in item:
            subs = item['specialize']
            if not isinstance(subs, list) or len(subs) != 2 or len(set(subs)) != 2 or not set(subs) <= set(SCHEMA['subskill_weights_pct'][item['group']]):
                raise ValueError('choose two distinct legal subskills')
    if len(set(groups)) != 2 or plan.get('body') not in P:
        raise ValueError('distinct technical categories and one body group required')


def _selected(state, selection, phase):
    group = selection['group']
    if 'specialize' in selection:
        return [f'{group}.{x}' for x in selection['specialize']]
    rng = career.rng_for(state['seed'], 'selection', state['month'], phase, group)
    pool = list(SCHEMA['subskill_weights_pct'][group])
    chosen = []
    for _ in range(2):
        weights = [SCHEMA['subskill_weights_pct'][group][k] * max(.1, career.soft_cap(state, f'{group}.{k}') - state['children'][group][k]) for k in pool]
        k = rng.choices(pool, weights=weights)[0]
        chosen.append(f'{group}.{k}')
        pool.remove(k)
    return chosen


def _exchange(state, path):
    g, k = path.split('.')
    cap = career.soft_cap(state, path)
    while state['children'][g][k] + 1 <= cap + 1e-8:
        v = state['children'][g][k]
        cost, permits = old.legacy.xp_cost(v), old.legacy.permits(v)
        if state['xp'][path] + 1e-8 < cost or state['permits'][path] < permits:
            break
        state['xp'][path] -= cost
        state['permits'][path] -= permits
        state['audit']['XP_SPENT'] += cost
        state['audit']['PERMITS_SPENT'] += permits
        state['children'][g][k] += 1
        state['annual_gained'][path] += 1


def _train(state, path, roll, age, env, phase, slot, efficiency, general=False):
    g, k = path.split('.')
    v = state['children'][g][k]
    cap = career.soft_cap(state, path)
    aptitude = state['learning_factor'][path]
    adjusted = int(career.clamp(roll - round(career.clamp((aptitude - 1) * 11, -2, 2)), 1, 100))
    r = career.rng_for(state['seed'], 'growth', state['month'], phase, slot, path, general)
    quality = .65 * env['coaching'] + .35 * env['partners']
    age_factor = career.learning_age_factor(state, age)
    effort = efficiency * age_factor * state['activity_rate']
    direct_effort = effort * career.clamp(quality / 2.0, .4, 1.25)
    raw_direct = 0
    raw_permits = 0
    exceptional = adjusted <= (3 if general else 10)
    if general:
        base_xp = 3.2 if exceptional else 2.0
        if exceptional and v < 120:
            raw_direct = 1
        if v >= 128:
            raw_permits = 2 if exceptional else int(r.random() < min(.35, .18 * max(0., quality - .6)))
    else:
        base_xp = 5 if adjusted <= 10 else 6 if adjusted <= 20 else 9 if adjusted <= 50 else 6
        if adjusted <= 10 and v < 128:
            raw_direct = r.randint(2, 4) if v < 120 else r.randint(1, 2)
        elif adjusted <= 20 and v < 118:
            raw_direct = 1
        if v >= 128:
            raw_permits = 3 if adjusted <= 3 else 2 if adjusted <= 20 else 1 if adjusted <= 50 else int(r.random() < .10 * max(0., quality - 1))
    direct = min(career.stochastic_round(raw_direct * direct_effort, r), max(0, math.floor(cap - v)))
    permit = career.stochastic_round(raw_permits * direct_effort, r)
    window = max((w['multiplier'] for w in state['windows'] if path in w['paths'] and w['start'] <= state['month'] < w['end']), default=1.)
    awarded = base_xp * old.pa_xp_mult(state['PA']) * aptitude * quality * effort * career.CONFIGS[state['career_v118']['strategy']]['xp_scale']
    if not general:
        awarded *= window
    before_xp = state['xp'][path]
    state['children'][g][k] += direct
    state['annual_gained'][path] += direct
    state['xp'][path] += awarded
    state['permits'][path] += permit
    state['audit']['PERMITS_AWARDED'] += permit
    state['audit']['DIRECT_TECHNICAL_GAIN'] += direct
    if efficiency > 0:
        _exchange(state, path)
    state['audit']['GENERAL_EXCELLENCE' if general else 'FOCUSED_EXCELLENCE'] += int(exceptional)
    state['audit']['XP_GENERAL' if general else 'XP_FOCUS'] += awarded
    return dict(type='general_technical' if general else 'focused_technical', path=path, group=g,
        roll=roll, adjusted=adjusted, exceptional=exceptional, age_factor=age_factor, efficiency=efficiency,
        direct_factor=direct_effort, raw_direct=raw_direct, direct_applied=direct, permit_awarded=permit,
        xp_awarded=awarded, xp_before=before_xp, xp_balance=state['xp'][path], permit_balance=state['permits'][path],
        window_multiplier=window if not general else 1., cap=cap, old=v, new=state['children'][g][k])


def _body(state, key, roll, age, env, efficiency, general=False):
    old_value = state['P6'][key]
    base = 4 if roll <= 5 else 2 if roll <= 20 else 1 if roll <= 60 else .3
    awarded = base * (0.25 if general else 3.0) * old.pa_xp_mult(state['PA']) * state['activity_rate'] * env['sports_science'] * efficiency * career.body_learning_factor(state, age)
    cost = 8 + .30 * max(0, old_value - 108) + .06 * max(0, old_value - 129) ** 2
    balance = state['P_xp'][key] + awarded
    state['P_xp'][key] = min(cost, balance)
    state['audit']['P_XP_AWARDED'] += awarded
    state['audit']['P_XP_EXPIRED_AT_BANK_CAP'] += max(0., balance - cost)
    ceiling = career.physical_ceiling(state, key)
    if efficiency > 0 and state['P_xp'][key] >= cost and state['career_v118']['physiological_P'][key] + 1 <= ceiling:
        state['P_xp'][key] -= cost
        state['audit']['P_XP_SPENT'] += cost
        state['career_v118']['physiological_P'][key] += 1
        state['P6'][key] = round(state['career_v118']['physiological_P'][key], 4)
    return dict(type='general_body' if general else 'focused_body', path=key, roll=roll,
        old=old_value, new=state['P6'][key], xp_awarded=awarded, xp_balance=state['P_xp'][key],
        age_factor=career.body_learning_factor(state, age), efficiency=efficiency, physical_ceiling=ceiling,
        xp_bank_cap=cost)


def _settle(state, plan, env, event_id, events, record):
    _validate(state, plan, event_id)
    release = state['training_release']
    month, phase = state['month'], plan['phase']
    age = state['start_age'] + (month + phase / 2) / 12
    for event in events:
        if event.get('id') == event_id:
            raise ValueError('development and phase event identities must differ')
        career.register_event(state, event)
    before = career.performance_card(state)
    if phase == 0:
        career.age_and_body(state, age, env, month)
    fatigue = state['fatigue']
    fraction = plan.get('training_fraction', 1.)
    recovery_fraction = plan.get('recovery_fraction', 1.)
    efficiency = career.fatigue_factor(fatigue) * fraction
    focused, general, body = [], [], []
    cost = 0.
    if plan.get('mode', 'train') == 'train':
        for category_index, selection in enumerate(plan['technical']):
            for sub_index, path in enumerate(_selected(state, selection, phase)):
                slot = category_index * 2 + sub_index
                roll = career.rng_for(state['seed'], 'focus', month, phase, slot).randint(1, 100)
                entry = _train(state, path, roll, age, env, phase, slot, efficiency)
                entry['specialized'] = 'specialize' in selection
                focused.append(entry)
        chosen = {x['group'] for x in plan['technical']}
        for group in GROUPS:
            if group in chosen:
                continue
            r = career.rng_for(state['seed'], 'general', month, phase, group)
            pool = list(SCHEMA['subskill_weights_pct'][group])
            path = group + '.' + r.choices(pool, weights=[SCHEMA['subskill_weights_pct'][group][k] for k in pool])[0]
            general.append(_train(state, path, r.randint(1, 100), age, env, phase, group, efficiency, True))
        for slot in range(2):
            roll = career.rng_for(state['seed'], 'body-focus', month, phase, slot).randint(1, 100)
            body.append(_body(state, plan['body'], roll, age, env, efficiency))
        for key in P:
            if key != plan['body']:
                roll = career.rng_for(state['seed'], 'body-general', month, phase, key).randint(1, 100)
                body.append(_body(state, key, roll, age, env, efficiency, True))
        cost = (14 + 2 * sum('specialize' in s for s in plan['technical'])) * fraction
        recovery = 14 * env['recovery'] * recovery_fraction
    else:
        recovery = 22 * env['recovery'] * recovery_fraction
    state['fatigue'] = career.clamp(fatigue + cost - recovery, 0, 100)
    state['event_registry'][event_id] = dict(id=event_id, month=month, phase=phase, kind='training_phase')
    release['settled_phase_ids'].append(event_id)
    release['last_mode'] = plan.get('mode', 'train')
    if phase == 1:
        state['month'] += 1
        release.update(month=state['month'], phase=0)
        if state['month'] % 12 == 0:
            current_age = state['start_age'] + state['month'] / 12
            career.revise_pa(state, current_age)
            current = career.performance_card(state)
            state['yearly'].append(dict(age=current_age, CA=current['CA'], learned_CA=current['learned_CA'],
                PA=state['PA'], pa_range=list(state['pa_range']), G9=current['G9'], P6=dict(state['P6']),
                remaining_body_envelope=current['remaining_body_envelope'],
                latent_target=state['career_v118']['latent_target'],
                potential_damage_total=state['career_v118']['potential_damage_total'],
                children=copy.deepcopy(state['children']), effective_children=current['children'],
                fatigue=state['fatigue'], injuries=state['injuries'], support_limited=len(current['body_limitations'])))
    else:
        release['phase'] = 1
    after = career.performance_card(state)
    receipt = dict(version=VERSION, id=event_id, month=month, phase=phase, age=age, mode=plan.get('mode', 'train'),
        plan=copy.deepcopy(plan), classification='SIMULATED', focused=focused, general=general, body=body,
        budget=dict(focused_technical=len(focused), general_technical=len(general),
                    focused_body=sum(x['type'] == 'focused_body' for x in body), general_body=sum(x['type'] == 'general_body' for x in body)),
        fatigue=dict(before=fatigue, cost=cost, recovery=recovery, after=state['fatigue'], efficiency=efficiency,
                     training_fraction=fraction, recovery_fraction=recovery_fraction),
        CA_before=before['CA'], CA_after=after['CA'], learned_CA=after['learned_CA'], PA_after=state['PA'],
        month_after=state['month'], phase_after=release['phase'],
        skill_changes=[dict(path=e['path'], old=e['old'], new=e['new']) for e in focused + general if e['new'] != e['old']],
        body_changes=[dict(path=e['path'], old=e['old'], new=e['new']) for e in body if e['new'] != e['old']])
    if record:
        release['phase_log'].append(receipt)
        if len(release['phase_log']) > 24:
            release['phase_log'].pop(0)
            release['receipts_archived'] += 1
    else:
        release['receipts_archived'] += 1
    return receipt


def settle_phase(state, plan, env, event_id, events=(), record=True):
    env = old.environment('club', **env)
    proposed = copy.deepcopy(state)
    receipt = _settle(proposed, plan, env, event_id, list(events), record)
    state.clear()
    state.update(proposed)
    return receipt


def settle_month(state, phases, env, event_id_prefix, events=(), record=True):
    if not isinstance(phases, list) or len(phases) != 2 or state['training_release']['phase'] != 0:
        raise ValueError('two sequential phases from phase zero required')
    proposed = copy.deepcopy(state)
    receipts = [_settle(proposed, p, old.environment('club', **env), f'{event_id_prefix}:phase{i}', list(events) if i == 0 else [], record) for i, p in enumerate(phases)]
    state.clear(); state.update(proposed)
    return receipts


dump_state = career.dump_state
load_state = career.load_state
performance_card = career.performance_card
prepare_card = career.prepare_card

