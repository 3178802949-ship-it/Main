"""Two auditable training settlements per month, with category-level choices.

This release changes training allocation and general-training excellence. Previous
career calibration is historical evidence, not validation of these new budgets.
Public mutations are transactional; call these APIs instead of mixing runtime
run_month/train helpers into the same saved career.
"""
from __future__ import annotations

import copy
import json
import math

from common import SCHEMA
import career_v116 as career
from card_training_v112 import P, compute_card

VERSION = 'V1.1.6-MODULAR-TRAINING-1'
GROUPS = tuple(SCHEMA['core_order'])
GENERAL_EXCELLENCE_D100 = 3


def initialize(card, seed=1, curve='balanced_progress', development_profile=None, start_age=None):
    if type(seed) is not int:
        raise ValueError('seed must be an integer')
    if start_age is None:
        start_age = card.get('age_approx', card.get('age', 18))
    if type(start_age) not in (int, float) or not math.isfinite(start_age) or not 10 <= start_age <= 60:
        raise ValueError('start_age must be between 10 and 60')
    source = copy.deepcopy(card)
    source.setdefault('pa_range', [max(0, source['PA'] - 4), min(200, source['PA'] + 4)])
    source.setdefault('CA', compute_card(source, SCHEMA)['CA_calculated'])
    profile = development_profile if development_profile is not None else source.get('development_profile')
    state = career.start(source, seed=seed, curve=curve, development_profile=profile)
    for key in ('learning_factor', 'style_preference'):
        if key in source:
            values = source[key]
            if (not isinstance(values, dict) or set(values) != set(state['xp']) or
                    any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values.values())):
                raise ValueError(f'{key} must contain all 43 finite positive factors')
            state[key] = copy.deepcopy(values)
    state['start_age'] = start_age
    state['age_offset'] = start_age - 18
    state['training_release'] = dict(version=VERSION, phase=0, month=0, settled_phase_ids=[],
                                     settled_general=[], phase_log=[], monthly_aging=[])
    state['card_metadata'] = {k: copy.deepcopy(source[k]) for k in (
        'name_zh', 'classification', 'origin', 'snapshot_date', 'year', 'nation_prototype') if k in source}
    return state


def _release(state):
    release = state.get('training_release')
    if not isinstance(release, dict) or release.get('version') != VERSION:
        raise ValueError('state must be initialized or migrated by Training.initialize')
    if release.get('phase') not in (0, 1) or release.get('month') != state['month']:
        raise ValueError('TRAINING_CLOCK_MISMATCH')
    if not math.isfinite(state['fatigue']) or not 0 <= state['fatigue'] <= 100:
        raise ValueError('invalid fatigue')
    return release


def _validate_plan(state, plan, event_id):
    release = _release(state)
    if not isinstance(event_id, str) or not event_id:
        raise ValueError('settlement needs a nonempty event_id')
    if event_id in release['settled_phase_ids'] or event_id in state['event_registry']:
        raise ValueError('DUPLICATE_TRAINING_EVENT')
    if not isinstance(plan, dict) or type(plan.get('month')) is not int or type(plan.get('phase')) is not int:
        raise ValueError('plan needs integer month and phase')
    if plan['month'] != state['month'] or plan['phase'] != release['phase']:
        raise ValueError('PLAN_OUT_OF_SEQUENCE')
    try:
        json.dumps(plan, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError('plan must be portable finite JSON') from error
    phase = plan['phase']
    expected_slots = {f"{state['month']}:0:{i}" for i in range(4)} if phase else set()
    actual_slots = {v for v in state['settled_drills'] if v.startswith(f"{state['month']}:")}
    # Rest phase zero produces no slots. Any other current-month slots mean a
    # runtime helper has been mixed into this public ledger.
    previous_rest = phase == 1 and release.get('last_mode') == 'rest'
    if actual_slots != (set() if previous_rest else expected_slots):
        raise ValueError('MIXED_OR_PARTIALLY_EXECUTED_TRAINING')
    mode = plan.get('mode', 'train')
    if mode not in ('train', 'rest'):
        raise ValueError('unknown training mode')
    if mode == 'rest':
        if plan.get('technical') or plan.get('body'):
            raise ValueError('rest phases cannot also contain drills')
        return
    if phase == 1 and state['month'] < state.get('rehab_until', 0):
        raise ValueError('REHABILITATION_PHASE_ONE_MUST_REST')
    technical = plan.get('technical')
    if not isinstance(technical, list) or len(technical) != 2:
        raise ValueError('choose exactly two technical categories')
    chosen = []
    for selection in technical:
        if not isinstance(selection, dict) or selection.get('group') not in GROUPS:
            raise ValueError('invalid technical category')
        group = selection['group']
        chosen.append(group)
        if 'specialize' in selection:
            subs = selection['specialize']
            if (not isinstance(subs, list) or len(subs) != 2 or
                    any(type(s) is not str or s not in SCHEMA['subskill_weights_pct'][group] for s in subs) or
                    len(set(subs)) != 2):
                raise ValueError('specialization needs two distinct child names in its category')
    if len(set(chosen)) != 2:
        raise ValueError('technical categories must differ')
    if plan.get('body') not in P:
        raise ValueError('choose one physical category')


def _category_paths(state, selection, phase):
    group = selection['group']
    if 'specialize' in selection:
        return [f'{group}.{s}' for s in selection['specialize']]
    pool = list(SCHEMA['subskill_weights_pct'][group])
    r = career.rng_for(state['seed'], 'release-category', state['month'], phase, group)
    selected = []
    for _ in range(2):
        child = r.choices(pool, weights=[SCHEMA['subskill_weights_pct'][group][k] for k in pool])[0]
        selected.append(f'{group}.{child}')
        pool.remove(child)
    return selected


def _general_technical(state, path, roll, age, env, phase, fatigue_factor, record=True):
    group, child = path.split('.')
    old = state['children'][group][child]
    cap = career.soft_cap(state, path)
    before_xp, before_permits = state['xp'][path], state['permits'][path]
    exceptional = roll <= GENERAL_EXCELLENCE_D100
    quality = .65 * env['coaching'] + .35 * env['partners']
    factors = dict(pa=career.pa_xp_mult(state['PA']), aptitude=state['learning_factor'][path],
                   activity=state['activity_rate'], age=career.learning_age_factor(state, age),
                   environment=quality, fatigue=fatigue_factor)
    base_xp = .9 if exceptional else .35
    awarded = base_xp * math.prod(factors.values())
    direct = int(exceptional and old < 120 and old < cap)
    excellence_permit = int(exceptional and old >= 128 and old < cap)
    # Preserve the existing high-quality coaching route. A new general-training
    # excellence roll supplements that route; it does not replace or stack with
    # it. Practice already banked is required before coaching can consolidate it.
    coach_probability = min(.33, .16 * max(0, quality - 1))
    coach_threshold = math.floor(100 * coach_probability)
    coach_eligible = (not exceptional and old >= 128 and old < cap and
                      before_xp + awarded >= .5 * career.legacy.xp_cost(old))
    coach_roll = (career.rng_for(state['seed'], 'release-coach-correction',
                  state['month'], phase, path).randint(1, 100) if coach_eligible else None)
    coach_permit = int(coach_eligible and coach_roll <= coach_threshold)
    permit = excellence_permit + coach_permit
    state['children'][group][child] += direct
    state['annual_gained'][path] += direct
    state['xp'][path] += awarded
    state['permits'][path] += permit
    career.exchange(state, path)
    state['audit']['GENERAL_TECHNICAL_ROLLS'] += 1
    state['audit']['GENERAL_XP'] += awarded
    state['audit']['GENERAL_EXCELLENCE'] += int(exceptional)
    state['audit']['GENERAL_EXCELLENCE_PERMITS'] += excellence_permit
    state['audit']['GENERAL_EXCELLENCE_DIRECT'] += direct
    state['audit']['GENERAL_COACH_CORRECTION_ROLLS'] += int(coach_eligible)
    state['audit']['GENERAL_COACH_CORRECTION_PERMITS'] += coach_permit
    state['audit']['COACHED_CONSOLIDATION_PERMITS'] += coach_permit
    entry = dict(type='general_technical', month=state['month'], phase=phase, path=path,
        roll=roll, adjusted=roll, exceptional=exceptional, base_xp=base_xp, factors=factors,
        excellence_permit=excellence_permit, coach_roll=coach_roll,
        coach_probability=coach_probability, coach_effective_probability=coach_threshold / 100,
        coach_threshold=coach_threshold, coach_eligible=coach_eligible, coach_permit=coach_permit,
        old=old, new=state['children'][group][child], cap=cap, direct_applied=direct,
        xp_awarded=awarded, xp_before=before_xp, xp_balance=state['xp'][path],
        permit_awarded=permit, permits_before=before_permits, permit_balance=state['permits'][path])
    if record:
        state['training_log'].append(entry)
    state['training_release']['settled_general'].append(f"{state['month']}:{phase}:{path}")
    return entry


def _body(state, key, roll, env, phase, fatigue_factor, general=False, record=True):
    old, old_xp = state['P6'][key], state['P_xp'][key]
    dose = .2 if general else 1.0
    base_xp = 4 if roll <= 5 else 2 if roll <= 20 else 1 if roll <= 60 else 0
    awarded = (dose * base_xp * career.pa_xp_mult(state['PA']) *
               state['activity_rate'] * env['sports_science'] * fatigue_factor)
    cost = 8 + .30 * max(0, old - 108) + .06 * max(0, old - 129) ** 2
    if general:
        state['P_xp'][key] += awarded
        if state['P_xp'][key] >= cost and old + 1 <= state['P_max'][key]:
            state['P_xp'][key] -= cost
            state['P6'][key] += 1
            state['audit']['P_GENERAL_GROWTH'] += 1
        state['audit']['P_GENERAL_ROLLS'] += 1
    else:
        # Keep the existing focused-body exchange implementation authoritative.
        original_activity = state['activity_rate']
        try:
            state['activity_rate'] = original_activity * fatigue_factor
            age = state['start_age'] + (state['month'] + phase / 2) / 12
            career.body_training(state, key, roll, age, env)
        finally:
            state['activity_rate'] = original_activity
    entry = dict(type='general_body' if general else 'focused_body', month=state['month'],
        phase=phase, path=key, roll=roll, exceptional=roll <= GENERAL_EXCELLENCE_D100,
        dose=dose, fatigue_multiplier=fatigue_factor, old=old, new=state['P6'][key],
        cap=state['P_max'][key], xp_awarded=awarded, xp_before=old_xp,
        xp_balance=state['P_xp'][key], cost=cost)
    if record:
        state['training_log'].append(entry)
    return entry


def _settle(proposed, plan, env, event_id, events, record=True):
    _validate_plan(proposed, plan, event_id)
    release = proposed['training_release']
    month, phase = proposed['month'], plan['phase']
    age = proposed['start_age'] + (month + phase / 2) / 12
    for event in events:
        if event.get('id') == event_id:
            raise ValueError('learning evidence and settlement IDs must differ')
        career.register_event(proposed, event)
    before = compute_card(proposed, SCHEMA)
    before_children = copy.deepcopy(proposed['children'])
    before_body = dict(proposed['P6'])
    # Physiology advances once per month even when both phases are rest.
    if phase == 0:
        career.age_and_body(proposed, age, env, month)
        release['monthly_aging'].append(dict(month=month, age=age))
    fatigue_before = proposed['fatigue']
    fatigue_factor = career.clamp(1 - .005 * max(0, fatigue_before - 35), .55, 1)
    focused, general, bodies = [], [], []
    mode = plan.get('mode', 'train')
    cost = 0
    if mode == 'train':
        original_activity = proposed['activity_rate']
        for category_index, selection in enumerate(plan['technical']):
            for sub_index, path in enumerate(_category_paths(proposed, selection, phase)):
                slot = category_index * 2 + sub_index
                roll = career.rng_for(proposed['seed'], 'release-focus', month, phase, slot).randint(1, 100)
                proposed['activity_rate'] = original_activity * fatigue_factor
                entry = career.train(proposed, path, roll, age, env, month, phase, slot, record)
                proposed['activity_rate'] = original_activity
                entry.update(type='focused_technical', group=selection['group'],
                    specialized='specialize' in selection, fatigue_multiplier=fatigue_factor,
                    activity_unfatigued=original_activity)
                focused.append(entry)
        for slot in range(2):
            roll = career.rng_for(proposed['seed'], 'release-focus-body', month, phase, slot).randint(1, 100)
            bodies.append(_body(proposed, plan['body'], roll, env, phase, fatigue_factor, record=record))
        selected_groups = {s['group'] for s in plan['technical']}
        for group in GROUPS:
            if group in selected_groups:
                continue
            pool = list(SCHEMA['subskill_weights_pct'][group])
            r = career.rng_for(proposed['seed'], 'release-general', month, phase, group)
            child = r.choices(pool, weights=[SCHEMA['subskill_weights_pct'][group][k] for k in pool])[0]
            roll = r.randint(1, 100)
            general.append(_general_technical(proposed, f'{group}.{child}', roll, age, env, phase, fatigue_factor, record))
        for key in P:
            if key == plan['body']:
                continue
            roll = career.rng_for(proposed['seed'], 'release-general-body', month, phase, key).randint(1, 100)
            bodies.append(_body(proposed, key, roll, env, phase, fatigue_factor, general=True, record=record))
        cost = 15 + 3 * sum('specialize' in s for s in plan['technical'])
        recovery = 14 * env['recovery']
    else:
        recovery = 22 * env['recovery']
    unclamped_peak = fatigue_before + cost
    peak_fatigue = min(100, unclamped_peak)
    # Do not discard workload above 100 before subtracting recovery: doing so
    # would make excessive training paradoxically recover a tired athlete.
    proposed['fatigue'] = career.clamp(unclamped_peak - recovery, 0, 100)
    receipt = dict(version=VERSION, id=event_id, month=month, phase=phase,
        age=age, mode=mode, classification='SIMULATED', plan=copy.deepcopy(plan),
        environment=dict(env), focused=focused, general=general, body=bodies,
        fatigue=dict(before=fatigue_before, cost=cost, peak=peak_fatigue,
                     unclamped_peak=unclamped_peak, overload=max(0, unclamped_peak - 100),
                     recovery=recovery, after=proposed['fatigue'], efficiency=fatigue_factor),
        budget=dict(focused_technical=len(focused), general_technical=len(general),
                    focused_body=sum(b['type'] == 'focused_body' for b in bodies),
                    general_body=sum(b['type'] == 'general_body' for b in bodies)),
        CA_before=before['CA_calculated'], PA_before=proposed['PA'])
    release['settled_phase_ids'].append(event_id)
    proposed['event_registry'][event_id] = dict(id=event_id, kind='training_phase', month=month, phase=phase)
    release['last_mode'] = mode
    if phase == 1:
        proposed['month'] += 1
        release['month'] = proposed['month']
        release['phase'] = 0
        if proposed['month'] % 12 == 0:
            current_age = proposed['start_age'] + proposed['month'] / 12
            career.revise_pa(proposed, current_age, SCHEMA, proposed['month'] // 12)
            result = compute_card(proposed, SCHEMA)
            proposed['yearly'].append(dict(age=current_age, CA=result['CA_calculated'],
                PA=proposed['PA'], G9=result['G9'], P6=dict(proposed['P6']),
                G_aggregate=result['G_aggregate'], P_aggregate=result['P_aggregate'],
                fatigue=proposed['fatigue'], injuries=proposed['injuries']))
    else:
        release['phase'] = 1
    result = compute_card(proposed, SCHEMA)
    receipt.update(CA_after=result['CA_calculated'], PA_after=proposed['PA'],
        month_after=proposed['month'], phase_after=release['phase'],
        skill_changes=[dict(path=f'{g}.{k}', old=v, new=proposed['children'][g][k])
            for g, subs in before_children.items() for k, v in subs.items() if proposed['children'][g][k] != v],
        body_changes=[dict(path=p, old=v, new=proposed['P6'][p]) for p, v in before_body.items()
                      if proposed['P6'][p] != v])
    release['phase_log'].append(receipt if record else {k: copy.deepcopy(receipt[k]) for k in (
        'id', 'month', 'phase', 'age', 'mode', 'budget', 'fatigue', 'CA_before', 'CA_after', 'PA_after')})
    return receipt


def settle_phase(state, plan, env, event_id, events=(), record=True):
    env = career.environment('club', **env)
    proposed = copy.deepcopy(state)
    receipt = _settle(proposed, plan, env, event_id, list(events), record)
    state.clear()
    state.update(proposed)
    return copy.deepcopy(receipt)


def settle_month(state, phases, env, event_id_prefix, events=(), record=True):
    if not isinstance(phases, list) or len(phases) != 2:
        raise ValueError('a month needs exactly two plans')
    if _release(state)['phase'] != 0:
        raise ValueError('month settlement must start before phase zero')
    if not isinstance(event_id_prefix, str) or not event_id_prefix:
        raise ValueError('event_id_prefix must be nonempty')
    env = career.environment('club', **env)
    proposed = copy.deepcopy(state)
    receipts = []
    for index, plan in enumerate(phases):
        receipts.append(_settle(proposed, plan, env, f'{event_id_prefix}:phase{index}', list(events) if index == 0 else [], record))
    state.clear()
    state.update(proposed)
    return copy.deepcopy(receipts)


def dump_state(state):
    _release(state)
    return career.dump_state(state)


def load_state(serialized):
    state = career.load_state(serialized)
    _release(state)
    return state


__all__ = ['VERSION', 'GROUPS', 'initialize', 'settle_phase', 'settle_month', 'dump_state', 'load_state']
