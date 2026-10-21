"""V1.1.7 综合版 latent development, bounded appraisal and physical support.

PA calibrates an estimated future *profile*, never current ability. The current
43 values, P6, and the frozen CA aggregation stay untouched by preparation.
Learned technique and today's body-supported execution are separate views.
All coefficients are transparent game-design candidates, not sports science.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
import math

from common import SCHEMA
import career_v116 as old
import career_v114 as legacy
from card_training_v112 import P, compute_card, physical_weights

VERSION = 'V1.1.7-COMPREHENSIVE-1'
TRAINING_VERSION = 'V1.1.7-COMPREHENSIVE-TRAINING-1'
PATHS = tuple(f'{g}.{k}' for g, sub in SCHEMA['subskill_weights_pct'].items() for k in sub)
CURVES = {
    'early_accelerator': dict(peak=26.8, sd=.55, rate=1.10, maturity=20.1, bodyloss=1.08),
    'foundation_builder': dict(peak=28.8, sd=.60, rate=1.02, maturity=21.2, bodyloss=.95),
    'balanced_progress': dict(peak=28.0, sd=.65, rate=1.05, maturity=20.6, bodyloss=1.),
    'late_breakthrough': dict(peak=29.5, sd=.55, rate=1.00, maturity=21.5, bodyloss=.98),
    'skill_specialist': dict(peak=28.2, sd=.65, rate=1.03, maturity=20.8, bodyloss=1.03),
}
CONFIGS = {
    'xp_only': dict(repair_profile=False, xp_scale=1.65, events=False),
    'profile_training': dict(repair_profile=True, xp_scale=1.65, events=False),
    'bounded_opportunities': dict(repair_profile=True, xp_scale=1.65, events=True),
}
DEFAULT_CONFIG = 'bounded_opportunities'


def rng_for(seed, *parts):
    return old.rng_for(seed, 'v117', *parts)


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def finite(value, name, lo=None, hi=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if lo is not None and value < lo or hi is not None and value > hi:
        raise ValueError(f'{name} out of bounds')
    return float(value)


def _traits(card):
    for group, sub in SCHEMA['subskill_weights_pct'].items():
        if set(card.get('children', {}).get(group, {})) != set(sub):
            raise ValueError('complete 43 technical attributes required')
        for key, value in card['children'][group].items():
            finite(value, f'{group}.{key}', 0, 150)
    if set(card.get('P6', {})) != set(P):
        raise ValueError('complete P6 required')
    for key, value in card['P6'].items():
        finite(value, key, 0, 150)
    finite(card.get('PA'), 'PA', 0, 200)


def _mix(body, path):
    return sum(body[k] * w for k, w in physical_weights(path).items())


def _alpha(path):
    group, key = path.split('.')
    return .14 if group in ('read', 'stable') else .82 if key in ('power', 'start', 'arrival') else .62 if key in ('spin', 'continuity', 'defense', 'flick') else .48


def _hard_cap(body, path):
    key = path.split('.')[1]
    if key == 'power':
        return min(150., 126 + .90 * max(0, body['strength'] - 112) + .15 * max(0, body['burst'] - 112))
    if key in ('start', 'arrival'):
        return min(150., 127 + .92 * max(0, body['speed'] - 112) + .15 * max(0, body['burst'] - 112))
    return 150.


def _profile_envelope(card, body_max, caps):
    value = dict(card, P6=body_max,
                 children={g: {k: caps[f'{g}.{k}'] for k in sub} for g, sub in card['children'].items()})
    return compute_card(value, SCHEMA)['CA_calculated']


def prepare_card(card, seed=1, strategy=DEFAULT_CONFIG, *, retrospective_discount=True):
    """Return a modelled future profile without changing current 43/P6/CA.

    A historical retrospective PA is not knowledge a young scout necessarily
    possessed. Its small initial public discount is labelled, and can be disabled
    for an explicitly declared original-player estimate. The latent target is an
    estimate of structural room, not an automatic outcome or current match bonus.
    """
    if type(seed) is not int or strategy not in CONFIGS:
        raise ValueError('known strategy and integer seed required')
    _traits(card)
    out = copy.deepcopy(card)
    if 'career117_profile' in out or 'career_v117' in out:
        raise ValueError('LEGACY_PREPARED_STATE_REQUIRES_EXPLICIT_MIGRATION_OR_ORIGINAL_CARD')
    if out.get('career118_profile', {}).get('version') == VERSION:
        if out['career118_profile'].get('strategy') != strategy:
            raise ValueError('PREPARED_PROFILE_STRATEGY_MISMATCH: branch from the original card')
        return out
    age = finite(out.get('model_start_age', out.get('age_approx', out.get('age', 18))), 'age', 10, 60)
    raw_pa = float(out['PA'])
    current = compute_card(out, SCHEMA)
    body_mean = sum(out['P6'][k] * SCHEMA['body_weights_pct'][k] / 100 for k in P)
    source_target = clamp(raw_pa + rng_for(seed, out.get('player_id'), 'latent').choice((-1, 0, 0, 0, 1)), current['CA_calculated'], 200)
    discount = 0
    if retrospective_discount and out.get('classification') == 'ASSESSMENT' and age < 20:
        discount = min(8, round((20 - age) * 1.5))
    public_pa = int(clamp(raw_pa - discount, current['CA_calculated'], 200))
    out['PA'] = public_pa
    out['pa_range'] = [max(0, public_pa - 3), min(200, public_pa + 3)]
    configuration = CONFIGS[strategy]
    if not configuration['repair_profile']:
        profile = copy.deepcopy(out.get('development_profile'))
        if profile is None:
            raise ValueError('xp_only comparison requires an existing development profile')
        state = old.start(out, seed=seed, development_profile=profile)
        caps = {path: legacy.soft_cap(dict(state, P6=state['P_max']), path) for path in PATHS}
        body_max = dict(profile['body_max'])
    else:
        body_level = clamp(110 + (source_target - 150) * .80, 108, 150)
        body_max = {k: round(clamp(body_level + .35 * (out['P6'][k] - body_mean)
                                  + rng_for(seed, out.get('player_id'), 'body', k).uniform(-.8, .8), out['P6'][k], 150), 4)
                    for k in P}
        flat = {f'{g}.{k}': v for g, sub in out['children'].items() for k, v in sub.items()}
        mean_skill = sum(flat.values()) / len(flat)
        offsets = {path: clamp((flat[path] - mean_skill) * .22, -5., 5.)
                   + rng_for(seed, out.get('player_id'), 'shape', path).uniform(-.5, .5) for path in PATHS}
        # Invert only the estimated future profile. This never reads the CA gap
        # when assigning current points, training odds, or match quality.
        best = None
        low, high = 90., 150.
        centers = []
        for _ in range(18):
            center = (low + high) / 2
            centers.append(center)
            candidate = {p: max(flat[p], min(150, round(center + offsets[p]), math.floor(_hard_cap(body_max, p)))) for p in PATHS}
            envelope = _profile_envelope(out, body_max, candidate)
            if envelope < source_target:
                low = center
            else:
                high = center
        centers.extend((low, high, min(150., high + .1)))
        for center in centers:
            candidate = {p: max(flat[p], min(150, round(center + offsets[p]), math.floor(_hard_cap(body_max, p)))) for p in PATHS}
            envelope = _profile_envelope(out, body_max, candidate)
            score = (abs(envelope - source_target), abs(center - (source_target * .75)))
            if best is None or score < best[0]:
                best = score, candidate, envelope
        caps = best[1]
        mental = float(out.get('development_profile', {}).get('mental', 12))
        neural = {p: float(out.get('development_profile', {}).get('neuromotor', {}).get(p, 1.0)) for p in PATHS}
        talents = {}
        for path, target in caps.items():
            group, key = path.split('.')
            alpha = .12 if group in ('read', 'stable') else .71 if key in ('power', 'start', 'arrival') else .52 if key in ('continuity', 'defense', 'spin', 'flick') else .40
            base = 126 + alpha * (_mix(body_max, path) - 110) + (mental if group in ('read', 'stable') else 0)
            if key not in ('power', 'start', 'arrival') and group not in ('read', 'stable'):
                base += .78 * neural[path]
            talents[path] = (target - base) / .36
        profile = dict(body_max=body_max, talent=talents, neuromotor=neural, mental=mental,
                       focus=list(out.get('development_profile', {}).get('focus', [])), body_maturation_rate=.035,
                       classification='MODELLED_FUTURE_PROFILE_NOT_REAL_POTENTIAL_CERTIFICATION')
    support = {}
    for path in PATHS:
        group, key = path.split('.')
        natural = min(caps[path] - _alpha(path) * (_mix(body_max, path) - _mix(out['P6'], path)), _hard_cap(out['P6'], path))
        support[path] = max(out['children'][group][key], natural)
    envelope = _profile_envelope(out, body_max, caps)
    out['development_profile'] = profile
    out['career118_profile'] = dict(version=VERSION, strategy=strategy, seed=seed,
        latent_target=source_target, source_retrospective_PA=raw_pa, initial_public_PA=public_pa,
        public_discount=discount, appraisal_band=3, max_annual_revision=2,
        latent_technical_caps=caps, support_baseline_P6=copy.deepcopy(out['P6']), support_baseline_caps=support,
        reachable_envelope=envelope, classification='ASSESSMENT_MODEL_NOT_GUARANTEED_OUTCOME')
    out['potential_semantics'] = 'LIFETIME_CAREER_POTENTIAL_APPRAISAL_NOT_REMAINING_ABILITY'
    out['growth_contract'] = dict(authority='Training', schedule='TWO_PHASE_CATEGORY_TRAINING',
                                  ruleset=VERSION, legacy_lazy_growth_active=False)
    return out


def soft_cap(state, path):
    p = state['career_v118']
    start_body = p['support_baseline_P6']
    observed = p['initial_children'][path]
    drop = _alpha(path) * (_mix(state['P6'], path) - _mix(start_body, path))
    support = p['support_baseline_caps'][path] + drop
    # Preserve a known legacy skill at entry, but do not let its exception
    # create extra growth above the hard physical constraint.
    preserved = observed + min(0., drop)
    cap = min(p['latent_technical_caps'][path], max(preserved, min(support, _hard_cap(state['P6'], path))))
    return clamp(cap, 50, 150)


def performance_card(state):
    learned = copy.deepcopy(state['children'])
    effective = {g: {k: min(v, max(0., soft_cap(state, f'{g}.{k}'))) for k, v in sub.items()} for g, sub in learned.items()}
    value = {k: copy.deepcopy(state[k]) for k in ('PA', 'P6', 'xp', 'permits', 'P_xp', 'fatigue', 'injuries') if k in state}
    value['children'] = effective
    value['learned_children'] = learned
    value['player_id'] = state['id']
    value.update(compute_card(value, SCHEMA))
    value.pop('CA_effective', None)
    value['CA'] = value['CA_calculated']
    value['learned_CA'] = compute_card(dict(state, children=learned), SCHEMA)['CA_calculated']
    value['body_limitations'] = [dict(path=f'{g}.{k}', learned=v, effective=effective[g][k],
                                    support_cap=soft_cap(state, f'{g}.{k}'))
                                for g, sub in learned.items() for k, v in sub.items() if effective[g][k] < v - 1e-8]
    value['ca_semantics'] = 'BODY_SUPPORTED_LEARNED_G43_P6_OUTPUT'
    value['potential_semantics'] = 'LIFETIME_CAREER_POTENTIAL_APPRAISAL_NOT_REMAINING_ABILITY'
    # A bounded present-age structural envelope is a different quantity from
    # lifetime PA. It assumes the current age-adjusted body ceiling and all
    # compatible technical caps, not enough future time to learn them all.
    remaining_body = {k: max(state['P6'][k], physical_ceiling(state, k)) for k in P}
    projected = dict(state, P6=remaining_body)
    remaining_caps = {path: soft_cap(projected, path) for path in PATHS}
    value['remaining_body_envelope'] = _profile_envelope(value, remaining_body, remaining_caps)
    value['remaining_body_envelope_semantics'] = 'CURRENT_AGE_STRUCTURAL_BOUND_NOT_A_FORECAST_OR_PA'
    value['remaining_body_ceiling_P6'] = remaining_body
    return value


def learning_age_factor(state, age):
    peak = state['career_v118']['peak_age']
    youth = 1.12 if age < 22 else 1.04 if age < 25 else .96
    return youth * math.exp(-.12 * max(0, age - (peak - .8)))


def body_learning_factor(state, age):
    return math.exp(-.13 * max(0., age - 23))


def fatigue_factor(fatigue):
    return clamp(1 - .012 * max(0, fatigue - 35), .16, 1.)


def stochastic_round(value, rng):
    floor = math.floor(max(0., value))
    return floor + int(rng.random() < value - floor)


def physical_ceiling(state, key):
    """Trainable body ceiling after accumulated aging and any real injury."""
    return max(55., state['P_max'][key] - state['career_v118']['age_loss_P'][key])


def age_and_body(state, age, env, month):
    model = state['career_v118']
    peak = model['peak_age']
    elapsed = max(0., age - peak)
    maturity = 1 / (1 + math.exp(clamp((age - model['maturity_mid']) / 2.2, -30, 30)))
    for key in P:
        value = model['physiological_P'][key]
        room = max(0., state['P_max'][key] - value)
        gain = min(.36, room * .015 * maturity * env['sports_science']) if age < 27 else 0.
        vulnerability = dict(speed=1.25, burst=1.30, strength=.78, stamina=.90, agility=1.12, flexibility=.83)[key]
        annual_loss = (.35 + .28 * elapsed ** 1.12) * vulnerability * model['body_loss_rate'] / env['recovery'] if elapsed else 0.
        loss = annual_loss / 12
        # Aging lowers the body which training can support. An old XP reserve
        # cannot turn biological decline into a permanently renewable +1 point.
        model['age_loss_P'][key] += loss
        ceiling = physical_ceiling(state, key)
        recovered = 0.
        deficit = model['temporary_P_deficit'][key]
        if deficit > 0 and month >= model['temporary_recovery_start'][key]:
            recovered = min(deficit, .5 * env['recovery'])
            model['temporary_P_deficit'][key] -= recovered
        model['physiological_P'][key] = clamp(value + gain - loss + recovered, 55, ceiling)
        state['P6'][key] = round(model['physiological_P'][key], 4)
        state['audit']['P_MATURITY'] += gain
        state['audit']['P_AGE_LOSS'] += loss
        state['audit']['P_TEMPORARY_INJURY_RECOVERY'] += recovered
    # Learned technique decays much more slowly than physical execution. It is
    # not overwritten when strength/speed no longer supports the old performance.
    memory_elapsed = max(0., age - (peak + 3.5))
    if memory_elapsed:
        for group, sub in state['children'].items():
            rate = .010 if group in ('read', 'stable') else .025
            for key in sub:
                loss = rate * memory_elapsed / 12
                sub[key] = max(50., sub[key] - loss)
                state['audit']['TECH_AGE_LOSS'] += loss


def register_event(state, event):
    e = copy.deepcopy(event)
    if not isinstance(e.get('id'), str) or not e['id'] or e['id'] in state['event_registry']:
        raise ValueError('duplicate or invalid development event')
    if e.get('month') != state['month'] or e.get('kind') not in ('match_review', 'champion', 'camp'):
        raise ValueError('development event outside current month or kind')
    paths = e.get('paths', [])
    if not paths or len(paths) > 3 or len(set(paths)) != len(paths) or not set(paths) <= set(PATHS):
        raise ValueError('development event needs 1..3 valid paths')
    if e.get('source') not in ('MATCH_LOG', 'WORLD_EVENT', 'TRAINING_LOG', 'SYNTHETIC') or not e.get('evidence_ref'):
        raise ValueError('development evidence required')
    if e['kind'] == 'champion' and e['source'] not in ('WORLD_EVENT', 'SYNTHETIC'):
        raise ValueError('champion requires completed world event evidence')
    for key in ('challenge', 'review_quality'):
        finite(e.get(key), key, 0, 1)
    usage = e.get('usage', {})
    if set(usage) != set(paths) or any(type(n) is not int or n < 0 for n in usage.values()):
        raise ValueError('event usage must cover all paths')
    evidence_key = f"{e['source']}:{e['evidence_ref']}"
    if evidence_key in state['settled_evidence']:
        raise ValueError('duplicate development evidence')
    windows = state['windows']
    recent = [w for w in windows if state['month'] - 11 <= w['start'] <= state['month']]
    champion = e['kind'] == 'champion'
    budget = sum(w.get('kind') == 'champion' for w in recent) < 2 if champion else sum(w.get('kind') != 'champion' for w in recent) < 6
    quality = e['challenge'] * e['review_quality']
    eligible = [p for p in paths if usage[p] >= (4 if champion else 8)]
    config = CONFIGS[state['career_v118']['strategy']]
    probability = (1.0 if champion else .72 * quality) if config['events'] else 0.
    draw = rng_for(state['seed'], 'event', e['id']).random()
    granted = budget and bool(eligible) and quality >= .45 and draw < probability
    if granted:
        windows[:] = [w for w in windows if w['start'] >= state['month'] - 11]
        windows.append(dict(event_id=e['id'], kind=e['kind'], paths=eligible, start=state['month'],
                            end=state['month'] + (2 if champion else 3),
                            multiplier=1 + (.25 if champion else .20) * quality))
        state['career_v118']['formal_evidence'] += int(e['source'] == 'WORLD_EVENT')
    result = dict(e, granted=granted, probability=probability, draw=draw,
                  reason='WINDOW' if granted else 'BUDGET_OR_EVIDENCE', eligible=eligible)
    state['event_registry'][e['id']] = dict(id=e['id'], month=e['month'], kind=e['kind'],
                                          evidence_key=evidence_key, granted=granted)
    state['settled_evidence'].append(evidence_key)
    state['audit']['LEARNING_WINDOWS'] += int(granted)
    return result


def register_champion(state, event):
    if event.get('kind') != 'champion':
        raise ValueError('champion event kind required')
    return register_event(state, event)


def register_match(state, event):
    if event.get('kind') != 'match_review':
        raise ValueError('match review kind required')
    return register_event(state, event)


def injury(state, event_id, month, affected=('speed', 'burst'), severity=2):
    if event_id in state['event_registry'] or not isinstance(event_id, str) or not event_id:
        raise ValueError('duplicate or invalid injury event')
    if month != state['month'] or type(severity) is not int or not 1 <= severity <= 5 or not affected or len(set(affected)) != len(affected) or not set(affected) <= set(P):
        raise ValueError('invalid injury')
    model = state['career_v118']
    before = {k: state['P6'][k] for k in affected}
    before_max = dict(state['P_max'])
    old_caps = dict(model['latent_technical_caps'])
    before_envelope = _profile_envelope(state, before_max, old_caps)
    pa_before, target_before = state['PA'], model['latent_target']
    # Severity is a game-design impact scale. Only 3..5 represents lasting
    # impairment; the label does not diagnose a real-world medical condition.
    permanent = max(0, severity - 1) if severity >= 3 else 0
    for key in affected:
        state['P_max'][key] = max(55, state['P_max'][key] - permanent)
        acute_loss = min(severity, max(0, model['physiological_P'][key] - 55))
        model['physiological_P'][key] -= acute_loss
        model['temporary_P_deficit'][key] += max(0, acute_loss - permanent)
        model['temporary_recovery_start'][key] = max(model['temporary_recovery_start'][key], month + 1)
        state['P6'][key] = min(physical_ceiling(state, key), model['physiological_P'][key])
        model['physiological_P'][key] = state['P6'][key]
    if permanent:
        for path in PATHS:
            support_loss = _alpha(path) * max(0, _mix(before_max, path) - _mix(state['P_max'], path))
            model['latent_technical_caps'][path] = max(50., old_caps[path] - support_loss)
    after_envelope = _profile_envelope(state, state['P_max'], model['latent_technical_caps'])
    appraisal_loss = min(3, max(0, before_envelope - after_envelope)) if permanent else 0
    model['potential_damage_total'] += appraisal_loss
    model['latent_target'] = max(0, target_before - appraisal_loss)
    model['reachable_envelope'] = after_envelope
    state['PA'] = max(0, pa_before - appraisal_loss)
    state['injuries'] += 1
    state['rehab_until'] = max(state.get('rehab_until', 0), month + severity * 2)
    state['pa_range'] = [max(0, state['PA'] - 3), min(200, state['PA'] + 3)]
    result = dict(id=event_id, month=month, kind='major_injury' if permanent else 'temporary_injury', severity=severity,
                  persistent_physical_damage=bool(permanent), permanent_loss_per_affected_body_group=permanent,
                  body_before=before, body_after={k: state['P6'][k] for k in affected},
                  P_max_before={k: before_max[k] for k in affected}, P_max_after={k: state['P_max'][k] for k in affected},
                  potential_envelope_before=before_envelope, potential_envelope_after=after_envelope,
                  PA_before=pa_before, PA_after=state['PA'], PA_loss=appraisal_loss,
                  latent_target_before=target_before, latent_target_after=model['latent_target'],
                  semantics='SIMULATED_INJURY_IMPACT_NOT_A_MEDICAL_PROGNOSIS')
    state['event_registry'][event_id] = result
    if appraisal_loss:
        state['scouting_events'].append(dict(month=month, age=state['start_age'] + month / 12,
            before=pa_before, after=state['PA'], reason='PERSISTENT_INJURY_STRUCTURAL_DAMAGE',
            evidence_id=event_id, envelope_before=before_envelope, envelope_after=after_envelope))
    return result


major_injury = injury


def revise_pa(state, age):
    model = state['career_v118']
    current = performance_card(state)['CA']
    net = current - model['year_start_CA']
    target = model['latent_target']
    old_pa = state['PA']
    # Annual appraisal moves only on sustained net improvement or actual formal
    # opportunity evidence. A temporary trophy does not add permanent ability.
    if age <= model['peak_age'] + 1 and net >= 2 and state['PA'] < target:
        step = 2 if net >= 7 and model['formal_evidence'] else 1
        state['PA'] = min(target, state['PA'] + step)
    state['PA'] = int(clamp(state['PA'], 0, 200))
    state['pa_range'] = [max(0, state['PA'] - 3), min(200, state['PA'] + 3)]
    model['year_start_CA'] = current
    model['formal_evidence'] = 0
    state['annual_gained'].clear()
    if old_pa != state['PA']:
        state['scouting_events'].append(dict(age=age, before=old_pa, after=state['PA'], reason='EVIDENCED_LIFETIME_POTENTIAL_APPRAISAL'))


def dump_state(state):
    return json.dumps(state, ensure_ascii=False, allow_nan=False)


def load_state(serialized):
    state = json.loads(serialized)
    if state.get('version') != VERSION or state.get('training_release', {}).get('version') != TRAINING_VERSION or state.get('career_v118', {}).get('version') != VERSION:
        raise ValueError('unsupported V1.1.7 综合版 training state')
    for key in ('audit', 'annual_gained', 'PA_evidence'):
        state[key] = Counter(state.get(key, {}))
    if state['training_release']['month'] != state['month'] or state['training_release']['phase'] not in (0, 1):
        raise ValueError('training clock mismatch')
    _traits(dict(state, PA=state['PA']))
    finite(state['fatigue'], 'fatigue', 0, 100)
    for key in P:
        finite(state['career_v118']['age_loss_P'][key], 'accumulated physical age loss', 0)
        finite(state['career_v118']['physiological_P'][key], 'physiological body', 0, 150)
        finite(state['P_max'][key], 'physical potential', 0, 150)
        finite(state['P_xp'][key], 'physical XP', 0)
        finite(state['career_v118']['temporary_P_deficit'][key], 'temporary physical deficit', 0)
        if type(state['career_v118']['temporary_recovery_start'][key]) is not int or state['career_v118']['temporary_recovery_start'][key] < 0:
            raise ValueError('temporary recovery month must be a nonnegative integer')
    finite(state['career_v118']['potential_damage_total'], 'lifetime potential damage', 0)
    if state['pa_range'] != [max(0, state['PA'] - 3), min(200, state['PA'] + 3)]:
        raise ValueError('narrow appraisal interval mismatch')
    for path in PATHS:
        finite(state['xp'][path], 'technical XP', 0)
        if type(state['permits'][path]) is not int or state['permits'][path] < 0:
            raise ValueError('non-negative integer permits required')
    return state

