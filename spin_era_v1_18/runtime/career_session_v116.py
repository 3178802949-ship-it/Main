"""Optional, player-directed monthly training for the V1.1.6 trial branch.

The calibrated career_v116 engine is unchanged. This adapter replaces automatic
focused drill selection with an explicit plan, reusing its budgets, rolls, costs,
physical limits, maintenance, injury capacity and annual appraisal. It does not
make the previous long-career calibration apply to this new planning branch.
"""
from __future__ import annotations

import copy
import json

import career_v116 as career
from card_training_v112 import P, compute_card

SESSION_PATCH_VERSION = 'V1.1.6-PLAYER-PLAN-TRIAL'


def recommend_plan(state, env, theme='tactical_repair'):
    """Diagnose training priorities with imperfect self-understanding.

    Existing self_read/choice lower bounded diagnostic noise; coaches compensate
    partially. They do not multiply XP, grant levels or expose latent soft caps.
    A recommendation is editable by the player, not a mandatory training order.
    """
    env = career.environment('club', **env)
    if theme not in ('tactical_repair', 'balanced'):
        raise ValueError('unsupported training theme')
    awareness = state['children']['read']['self_read']
    choice = state['children']['read']['choice']
    cognitive_score = .6 * awareness + .4 * choice
    individual = career.clamp((cognitive_score - 90) / 60, 0, 1)
    coach = career.clamp((env['coaching'] - 1) / 3.2, 0, 1)
    assisted = individual + .45 * coach * (1 - individual)
    noise_bound = 8 - 6 * assisted
    paths = sorted(state['xp'])
    observations = []
    for path in paths:
        group, key = path.split('.')
        current = state['children'][group][key]
        draw = career.rng_for(state['seed'], 'diagnosis', state['month'], path).uniform(-1, 1)
        noise = draw * noise_bound
        observations.append(dict(path=path, current=current, reference=125,
                                 diagnostic_noise=noise,
                                 perceived_gap=125 - current + noise))
    ranked = sorted(observations, key=lambda o: (-o['perceived_gap'], o['path']))
    if theme == 'tactical_repair':
        backhand = [o['path'] for o in ranked if o['path'].startswith('bh.')]
        if len(backhand) < 2:
            raise ValueError('tactical repair needs at least two backhand skills')
        phases = [dict(technical=['read.self_read', backhand[0]], body='agility'),
                  dict(technical=['read.choice', backhand[1]], body='stamina')]
    else:
        targets = [o['path'] for o in ranked[:4]]
        body = sorted(P, key=lambda k: (state['P6'][k], k))
        phases = [dict(technical=targets[:2], body=body[0]),
                  dict(technical=targets[2:], body=body[1])]
    return dict(month=state['month'], theme=theme, phases=phases,
                recommendation_audit=dict(self_read=awareness, choice=choice,
                    cognitive_score=cognitive_score, individual_accuracy=individual,
                    coach_compensation=assisted - individual,
                    diagnostic_noise_bound=noise_bound, observations=observations,
                    note='Reference 125 is a training-planning heuristic, not a skill cap or CA target.'))


def _validate_plan(state, plan):
    if not isinstance(plan, dict) or type(plan.get('month')) is not int or plan['month'] != state['month']:
        raise ValueError('plan must belong to the current month')
    phases = plan.get('phases')
    if not isinstance(phases, list) or len(phases) != 2:
        raise ValueError('plan must contain two training phases')
    for phase in phases:
        if not isinstance(phase, dict):
            raise ValueError('invalid training phase')
        paths = phase.get('technical')
        if (not isinstance(paths, list) or len(paths) != 2
                or any(not isinstance(p, str) or p not in state['xp'] for p in paths)
                or len(set(paths)) != 2):
            raise ValueError('each phase needs two distinct valid technical targets')
        if phase.get('body') not in P:
            raise ValueError('each phase needs one valid body target')
    try:
        json.dumps(plan, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError('plan metadata must be portable JSON') from error
    prefix = f"{state['month']}:"
    if any(slot.startswith(prefix) for slot in state['settled_drills']):
        raise ValueError('MONTH_ALREADY_PARTIALLY_TRAINED')
    if any(entry['month'] == state['month'] for entry in state.get('session_log', [])):
        raise ValueError('MONTH_ALREADY_SETTLED')


def advance_month(state, schema, env, plan, events=(), record=True):
    """Commit a whole player-directed month only after every operation succeeds.

    Healthy capacity is 8 technical rolls, 4 body rolls and 12 maintenance paths.
    A rehabilitation month executes only the first planned phase. The same RNG
    channel keys as the base engine are used; extra cognition never changes the
    training D100 itself. Only the chosen targets differ.
    """
    env = career.environment('club', **env)
    _validate_plan(state, plan)
    proposed = copy.deepcopy(state)
    month = proposed['month']
    age = 18 + month / 12
    before = compute_card(proposed, schema)
    initial_children = copy.deepcopy(proposed['children'])
    initial_body = dict(proposed['P6'])
    initial_audit = proposed['audit'].copy()
    for event in events:
        career.register_event(proposed, event)
    career.age_and_body(proposed, age, env, month)
    capacity = 1 if month < proposed.get('rehab_until', 0) else 2
    completed = []
    for phase_index, phase in enumerate(plan['phases'][:capacity]):
        technical = []
        for index, path in enumerate(phase['technical']):
            for roll_index in range(2):
                roll = career.rng_for(proposed['seed'], 'technical', month, phase_index,
                                      index, roll_index).randint(1, 100)
                technical.append(career.train(proposed, path, roll, age, env, month,
                    phase_index, index * 2 + roll_index, record))
        body_rng = career.rng_for(proposed['seed'], 'body', month, phase_index)
        # Preserve base-engine D100 alignment after its automatic key selection.
        body_rng.choices(P, weights=[1.2, 1.2, 1, 1.05, 1.1, .9])
        key = phase['body']
        body = []
        for _ in range(2):
            roll = body_rng.randint(1, 100)
            old, old_xp = proposed['P6'][key], proposed['P_xp'][key]
            career.body_training(proposed, key, roll, age, env)
            body.append(dict(path=key, roll=roll, old=old, new=proposed['P6'][key],
                             xp_before=old_xp, xp_balance=proposed['P_xp'][key],
                             body_ceiling=proposed['P_max'][key]))
        completed.append(dict(phase=phase_index, technical=technical, body=body))
    career.maintenance(proposed, age, env, month, adaptive=True, consolidation=True, record=record)
    proposed['month'] += 1
    if proposed['month'] % 12 == 0:
        career.revise_pa(proposed, 18 + proposed['month'] // 12, schema, proposed['month'] // 12)
        result = compute_card(proposed, schema)
        proposed['yearly'].append(dict(age=18 + proposed['month'] // 12,
            CA=result['CA_calculated'], PA=proposed['PA'], G9=result['G9'],
            G_aggregate=result['G_aggregate'], P_aggregate=result['P_aggregate'],
            P6=dict(proposed['P6']), environment=dict(env), injuries=proposed['injuries']))
    result = compute_card(proposed, schema)
    skill_changes = [dict(path=f'{g}.{k}', old=initial_children[g][k], new=value)
        for g, sub in proposed['children'].items() for k, value in sub.items()
        if value != initial_children[g][k]]
    body_changes = [dict(path=p, old=initial_body[p], new=proposed['P6'][p])
                    for p in P if proposed['P6'][p] != initial_body[p]]
    settlement = dict(month=month, classification='SIMULATED',
        plan=copy.deepcopy(plan), environment=dict(env), completed_phases=capacity,
        phases=completed, CA_before=before['CA_calculated'], CA_after=result['CA_calculated'],
        skill_changes=skill_changes, body_changes=body_changes,
        audit_delta={key: proposed['audit'][key] - initial_audit[key]
                     for key in proposed['audit'] if proposed['audit'][key] != initial_audit[key]})
    proposed.setdefault('session_log', []).append(settlement)
    proposed['session_patch_version'] = SESSION_PATCH_VERSION
    state.clear()
    state.update(proposed)
    return settlement
