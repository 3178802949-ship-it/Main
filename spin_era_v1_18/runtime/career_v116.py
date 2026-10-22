"""V1.1.6 career calibration prototype. No historical snapshots are written.

Keeps G43/P6, XP costs, permits, physical caps, five priors and mild PA XP.
Environment coefficients are game-design candidates, not measured sports science.
Events are development evidence, never a win-to-stat conversion or a match engine.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from collections import Counter

import career_v114 as legacy
import career_v115 as baseline
from card_training_v112 import P, compute_card

VERSION = 'V1.1.6-CALIBRATION-PROTOTYPE'
CURVES = baseline.CURVES
pa_xp_mult = baseline.pa_xp_mult
clamp = legacy.clamp
ENVIRONMENTS = {
    'club': dict(coaching=1.0, partners=1.0, sports_science=1.0, recovery=1.0),
    'national': dict(coaching=2.2, partners=2.0, sports_science=1.25, recovery=1.10),
    'frontier': dict(coaching=4.2, partners=3.6, sports_science=1.50, recovery=1.20),
}


def rng_for(seed, *parts):
    """Independent deterministic streams keep ablations from shifting other rolls."""
    digest = hashlib.sha256('|'.join(map(str, (seed,) + parts)).encode()).digest()
    return random.Random(int.from_bytes(digest[:16], 'big'))


def environment(name='club', **overrides):
    result = dict(ENVIRONMENTS[name])
    if set(overrides) - set(result):
        raise ValueError('unknown environment parameter')
    result.update(overrides)
    bounds = {'coaching': (0.7, 4.2), 'partners': (0.7, 3.6),
              'sports_science': (0.7, 1.5), 'recovery': (0.7, 1.2)}
    for key, (lo, hi) in bounds.items():
        if not math.isfinite(result[key]) or not lo <= result[key] <= hi:
            raise ValueError(f'environment out of bounds: {key}')
    return result


def start(card, seed=1, curve='balanced_progress', development_profile=None):
    """Explicit generic profile, or read-only legacy test-fixture compatibility.

    Generic profiles supply body_max, talent (43 paths), neuromotor (43 paths),
    mental and focus. PA is not used to infer these independent potentials.
    The old named archetypes remain test fixtures, not a general player generator.
    """
    source = copy.deepcopy(card)
    if development_profile is not None:
        source['archetype'] = 'ordinary'  # initialization scaffold, overwritten below
    if source.get('archetype') not in legacy.ARCH:
        raise ValueError('explicit development_profile required for generic cards')
    state = baseline.start(source, seed=seed, curve=curve)
    if development_profile is not None:
        profile = copy.deepcopy(development_profile)
        paths = set(state['xp'])
        if set(profile['body_max']) != set(P):
            raise ValueError('body_max must cover P6')
        for key in ('talent', 'neuromotor'):
            if set(profile[key]) != paths or any(not math.isfinite(v) for v in profile[key].values()):
                raise ValueError(f'{key} must cover all 43 paths with finite values')
        if not set(profile['focus']) <= paths or not math.isfinite(profile['mental']):
            raise ValueError('invalid focus or mental profile')
        if any(not state['P6'][k] <= profile['body_max'][k] <= 150 for k in P):
            raise ValueError('body potential below current body or above 150')
        state['P_max'] = profile['body_max']
        state['talent'] = profile['talent']
        state['neuromotor'] = profile['neuromotor']
        state['mental'] = profile['mental']
        # Remove the scaffold's preferred-skill tag before applying actual focus.
        scaffold_focus = set(legacy.ARCH['ordinary']['focus'])
        for path in paths:
            raw = state['learning_factor'][path] / (1.08 if path in scaffold_focus else 1)
            state['learning_factor'][path] = round(raw * (1.08 if path in profile['focus'] else 1), 4)
        state['focus'] = profile['focus']
        state['archetype'] = 'explicit_profile'
    if not 0 <= state['pa_range'][0] <= state['PA'] <= state['pa_range'][1] <= 200:
        raise ValueError('invalid PA estimate interval')
    state['seed'] = seed
    state['version'] = VERSION
    state['potential_source'] = ('EXPLICIT_PROFILE' if development_profile is not None
                                 else 'LEGACY_SYNTHETIC_ARCHETYPE_FIXTURE')
    state['decline_age'] = clamp(state['peak_age'] + .8 + rng_for(seed, 'decline').gauss(0, .6), 26.0, 34.0)
    # The previous Fan midpoint could be before 17. Development now refers to the
    # learning-window draw, still bounded independently from the actual CA peak.
    # Keep individual maturation distinct from technical peak. Only a mild prior
    # deviation is shared; changing curve must not move every body to later youth.
    state['maturity_mid'] = clamp(state['maturity_mid'] +
        .4 * (state['peak_age'] - data_peak(curve)), 19.5, 24.0)
    state['month'] = 0
    state['windows'] = []
    state['event_registry'] = {}
    state['development_log'] = []
    state['training_log'] = []
    state['settled_drills'] = []
    state['settled_evidence'] = []
    state['annual_gained'] = Counter()
    state['yearly'] = []
    state['body_maturation_rate'] = (development_profile.get('body_maturation_rate', .02)
                                     if development_profile is not None
                                     else legacy.ARCH[source['archetype']]['body_rate'])
    if not .001 <= state['body_maturation_rate'] <= .04:
        raise ValueError('invalid maturation rate')
    del state['event_dedupe']  # legacy, unused set; the new ledger is JSON-safe
    return state


def learning_age_factor(state, age):
    # The peak prior now matters but does not force a peak or grant skill levels.
    center = state['peak_age'] - (6.0 if state['curve'] == 'early_accelerator' else
                                 1.0 if state['curve'] == 'late_breakthrough' else 3.5)
    window = .78 + .38 * math.exp(-.5 * ((age - center) / 5.0) ** 2)
    # Acquiring genuinely new elite technique slows after the personal window;
    # this is continuous and does not force an actual peak at a specified age.
    return window * math.exp(-.10 * max(0, age - state['peak_age']))


def data_peak(curve):
    return CURVES[curve]['peak'][0]


def soft_cap(state, path):
    return legacy.soft_cap(state, path)


def exchange(state, path):
    before = state['children'][path.split('.')[0]][path.split('.')[1]]
    legacy.exchange(state, path)
    after = state['children'][path.split('.')[0]][path.split('.')[1]]
    if after > before:
        state['annual_gained'][path] += after - before


def _window(state, path, month):
    applicable = [w for w in state['windows']
                  if path in w['paths'] and w['start'] <= month < w['end']]
    return max(applicable, key=lambda w: w['multiplier']) if applicable else None


def train(state, path, d100, age, env, month, phase=0, roll_index=0, record=True):
    """Same D100 tiers, cost curve and permits; no lowering a skill to its soft cap."""
    if path not in state['xp'] or type(d100) is not int or not 1 <= d100 <= 100:
        raise ValueError('invalid technical drill')
    if month != state['month'] or phase not in (0, 1) or roll_index not in range(4):
        raise ValueError('invalid training month or slot')
    drill_id = f'{month}:{phase}:{roll_index}'
    if drill_id in state['settled_drills']:
        raise ValueError('DUPLICATE_TRAINING_SLOT')
    env = environment('club', **env)
    group, key = path.split('.')
    before = state['children'][group][key]
    aptitude = state['learning_factor'][path]
    bias = round(clamp((aptitude - 1) * 11, -2, 2))
    adjusted = int(clamp(d100 - bias, 1, 100))
    xp = direct = permits = 0
    secondary = None
    roll_rng = rng_for(state['seed'], 'secondary', month, phase, roll_index, path)
    if adjusted <= 10:
        if before < 128:
            secondary = roll_rng.randint(2, 4) if before < 120 else roll_rng.randint(1, 2)
            direct = secondary
        else:
            permits = 2 if adjusted <= 3 else 1
            xp = 1
    elif adjusted <= 20:
        if before < 118:
            direct = 1
        elif before >= 128:
            permits, xp = 1, 1
        else:
            xp = 2
    else:
        xp = 2.5 if adjusted <= 50 else 1.5
    window = _window(state, path, month)
    window_factor = window['multiplier'] if window else 1.0
    quality = .65 * env['coaching'] + .35 * env['partners']
    factors = dict(pa=pa_xp_mult(state['PA']), aptitude=aptitude,
                   activity=state['activity_rate'], age=learning_age_factor(state, age),
                   environment=quality, window=window_factor)
    awarded = xp * math.prod(factors.values())
    review_permit = 0
    if (window and before >= 128 and before < soft_cap(state, path)
            and 21 <= adjusted <= 50 and path not in window.get('consolidated', [])):
        # One evidence-backed consolidation per target, only after a good drill.
        # Still requires normal XP and the same physical cap for any level gain.
        review_permit = 1
        window.setdefault('consolidated', []).append(path)
        permits += 1
        state['audit']['EVENT_TRAINED_PERMITS'] += 1
    before_xp, before_permits = state['xp'][path], state['permits'][path]
    cap = soft_cap(state, path)
    applied = min(direct, max(0, cap - before))
    state['children'][group][key] += applied
    state['annual_gained'][path] += applied
    state['xp'][path] += awarded
    state['permits'][path] += permits
    exchange(state, path)
    after = state['children'][group][key]
    state['audit']['TRAINING_ROLLS'] += 1
    state['audit']['XP_FOCUS'] += awarded
    state['audit']['DIRECT_SKILL_LEVELS'] += applied
    state['settled_drills'].append(drill_id)
    if window and xp:
        state['audit']['WINDOW_XP_EXTRA'] += awarded - awarded / window_factor
    entry = dict(month=month, phase=phase, roll_index=roll_index, path=path,
                 roll=d100, adjusted=adjusted, secondary_direct_roll=secondary,
                 old=before, new=after, cap=cap, direct_applied=applied,
                 permit_awarded=permits, review_permit=review_permit, base_xp=xp, factors=factors,
                 xp_awarded=awarded, xp_before=before_xp, xp_balance=state['xp'][path],
                 permits_before=before_permits, permit_balance=state['permits'][path],
                 source_event=window['event_id'] if window else None)
    if record:
        state['training_log'].append(entry)
    return entry


def priorities(state, age, paths, adaptive=True):
    weights = baseline.priorities(state, age, paths)
    for i, path in enumerate(paths):
        group, key = path.split('.')
        current = state['children'][group][key]
        room = max(0, soft_cap(state, path) - current)
        if adaptive:
            # Planning responds to specific skills and latent room, never CA/PA gap.
            # A full XP bank without permits needs focused attempts, not more passive XP.
            urgency = clamp(legacy.xp_cost(current) / (state['xp'][path] + 2), .65, 1.8)
            if state['permits'][path] < legacy.permits(current):
                urgency = max(urgency, 1.4)
            weights[i] *= (.25 + min(1.6, room / 8)) * urgency
        # Focus early on actual preferred drills; a common factor had cancelled out.
        if age < 23 and path in state['focus']:
            weights[i] *= state['early_focus']
        if _window(state, path, state['month']):
            weights[i] *= 1.8
    return weights


def maintenance(state, age, env, month, adaptive=True, consolidation=True, record=False):
    r = rng_for(state['seed'], 'maintenance', month)
    pool = list(state['xp'])
    quality = .65 * env['coaching'] + .35 * env['partners']
    for _ in range(12):
        path = r.choices(pool, weights=priorities(state, age, pool, adaptive))[0]
        pool.remove(path)
        xp = (.82 * pa_xp_mult(state['PA']) * state['learning_factor'][path]
              * quality * learning_age_factor(state, age))
        group, key = path.split('.')
        before = state['children'][group][key]
        before_xp = state['xp'][path]
        before_permits = state['permits'][path]
        state['xp'][path] += xp
        state['audit']['MAINTENANCE_XP'] += xp
        # Top coaching supplies actionable correction, not just more raw practice.
        # This uses the SAME breakthrough permits as focused D100 training.
        # Club baseline has no extra permit roll. Probability is capped at .33.
        chance = min(.33, .16 * max(0, quality - 1)) if consolidation else 0
        draw = rng_for(state['seed'], 'correction', month, path).random()
        permit = int(before >= 128 and before < soft_cap(state, path)
                     and state['xp'][path] >= .5 * legacy.xp_cost(before) and draw < chance)
        state['permits'][path] += permit
        state['audit']['COACHED_CONSOLIDATION_PERMITS'] += permit
        exchange(state, path)
        if record:
            state['training_log'].append(dict(kind='coached_maintenance', month=month, path=path,
                old=before, new=state['children'][group][key], xp_before=before_xp,
                xp_awarded=xp, xp_balance=state['xp'][path], permits_before=before_permits,
                permit_awarded=permit, permit_balance=state['permits'][path],
                correction_draw=draw, correction_probability=chance, cap=soft_cap(state, path)))


def age_and_body(state, age, env, month):
    r = rng_for(state['seed'], 'biology', month)
    elapsed = max(0, age - state['decline_age'])
    maturation = 1 / (1 + math.exp(clamp((age - state['maturity_mid']) / 2.4, -30, 30)))
    body_rate = state['body_maturation_rate']
    for key in P:
        room = max(0, state['P_max'][key] - state['P6'][key])
        chance = min(.62, room * body_rate * maturation * env['sports_science'])
        if age < 32 and state['P6'][key] + 1 <= state['P_max'][key] and r.random() < chance:
            state['P6'][key] += 1
            state['audit']['P_MATURITY'] += 1
        vulnerability = dict(speed=1.20, burst=1.25, strength=.72,
                             stamina=.83, agility=1.03, flexibility=.78)[key]
        loss = min(.75, .022 * (elapsed + .25) ** 1.18 * vulnerability
                   * state['grace'] / env['recovery']) if elapsed else 0
        extra = min(.36, .0048 * elapsed ** 1.35 * state['body_loss_rate'] * vulnerability)
        for probability in (loss, extra):
            if r.random() < probability:
                state['P6'][key] = max(70, state['P6'][key] - 1)
                state['audit']['P_AGE_LOSS'] += 1
    for group, sub in state['children'].items():
        cognitive = group in ('read', 'stable')
        for key in sub:
            after = max(0, age - (state['decline_age'] + (3.4 if cognitive else 1.4)))
            risk = min(.43, .021 * (after + .5) ** 1.22 * state['grace'] / env['recovery']) if after else 0
            extra = min(.28, .0032 * after ** 1.35 * state['tech_loss_rate'] * (.46 if cognitive else 1))
            for probability in (risk, extra):
                if r.random() < probability:
                    sub[key] = max(62, sub[key] - 1)
                    state['audit']['TECH_AGE_LOSS'] += 1
            if elapsed and sub[key] > soft_cap(state, f'{group}.{key}') and r.random() < .14 * state['grace']:
                sub[key] -= 1
                state['audit']['CAP_EROSION'] += 1


def body_training(state, key, roll, age, env):
    xp = (4 if roll <= 5 else 2 if roll <= 20 else 1 if roll <= 60 else 0)
    state['P_xp'][key] += xp * pa_xp_mult(state['PA']) * state['activity_rate'] * env['sports_science']
    value = state['P6'][key]
    cost = 8 + .30 * max(0, value - 108) + .06 * max(0, value - 129) ** 2
    if state['P_xp'][key] >= cost and value + 1 <= state['P_max'][key]:
        state['P6'][key] += 1
        state['P_xp'][key] -= cost
        state['audit']['P_FOCUS_GROWTH'] += 1
    state['audit']['P_ROLLS'] += 1


def register_event(state, event):
    """Validate before mutation; duplicate IDs are rejected across all event types.

    Match evidence must be attached by a caller to a real match log, or explicitly
    tagged SYNTHETIC. A close score, trophy or generated 'epic' label is insufficient.
    No event instantly raises G/P/PA, creates permits, or changes the physical cap.
    """
    e = copy.deepcopy(event)
    if not isinstance(e.get('id'), str) or not e['id']:
        raise ValueError('event needs an id')
    if e['id'] in state['event_registry']:
        raise ValueError('DUPLICATE_DEVELOPMENT_EVENT')
    if type(e.get('month')) is not int or e['month'] != state['month']:
        raise ValueError('event must be settled in current month')
    if e.get('source') not in ('MATCH_LOG', 'TRAINING_LOG', 'SYNTHETIC') or not isinstance(e.get('evidence_ref'), str) or not e['evidence_ref']:
        raise ValueError('missing explicit evidence provenance')
    evidence_id = f"{e['source']}:{e['evidence_ref']}"
    if evidence_id in state['settled_evidence']:
        raise ValueError('DUPLICATE_EVIDENCE')
    if e.get('kind') not in ('match_review', 'camp'):
        raise ValueError('unsupported learning event')
    paths = e.get('paths', [])
    if not paths or len(paths) > 3 or len(set(paths)) != len(paths) or not set(paths) <= set(state['xp']):
        raise ValueError('event needs 1-3 distinct valid technical paths')
    for key in ('challenge', 'review_quality'):
        value = e.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f'{key} must be in [0,1]')
    usage = e.get('usage', {})
    if set(usage) != set(paths) or any(type(n) is not int or n < 0 for n in usage.values()):
        raise ValueError('usage evidence must cover paths')
    eligible = [p for p in paths if usage[p] >= 8]
    quality = e['challenge'] * e['review_quality']
    # Six per rolling twelve months; multiple victories cannot multiply budgets.
    recent = sum(1 for w in state['windows'] if e['month'] - 11 <= w['start'] <= e['month'])
    roll = rng_for(state['seed'], 'event', e['id']).random()
    chance = .72 * quality
    granted = bool(eligible and quality >= .5 and recent < 6 and roll < chance)
    result = dict(e, eligible=eligible, draw=roll, probability=chance,
                  granted=granted, reason=('WINDOW' if granted else
                  'ANNUAL_BUDGET' if recent >= 6 else 'NO_WINDOW'))
    if granted:
        # Current month plus next two. Only actual focused XP is enhanced.
        state['windows'].append(dict(event_id=e['id'], paths=eligible, start=e['month'],
                                     end=e['month'] + 3, multiplier=1 + .5 * quality))
        state['audit']['LEARNING_WINDOWS'] += 1
    state['event_registry'][e['id']] = result
    state['settled_evidence'].append(evidence_id)
    state['development_log'].append(result)
    return result


def major_injury(state, event_id, month, affected=('speed', 'burst'), severity=2):
    """Small explicit injury adapter; probabilistic injuries/calendar are out of scope.

    PA is only re-estimated if it exceeds the physically reachable cap envelope.
    Existing technical levels decay through aging/erosion; no training-triggered cut.
    """
    if event_id in state['event_registry']:
        raise ValueError('DUPLICATE_DEVELOPMENT_EVENT')
    if (not isinstance(event_id, str) or not event_id or month != state['month'] or
        not affected or len(set(affected)) != len(affected) or not set(affected) <= set(P) or
        type(severity) is not int or not 1 <= severity <= 5):
        raise ValueError('invalid injury')
    before = {k: state['P_max'][k] for k in affected}
    for key in affected:
        state['P_max'][key] = max(70, state['P_max'][key] - severity)
        state['P6'][key] = max(70, state['P6'][key] - severity)
    state['rehab_until'] = max(state.get('rehab_until', 0), month + severity * 2)
    state['injuries'] += 1
    e = dict(id=event_id, month=month, kind='major_injury', severity=severity,
             ceiling_before=before, ceiling_after={k: state['P_max'][k] for k in affected})
    state['event_registry'][event_id] = e
    state['development_log'].append(e)
    return e


def reachable_envelope(state, schema):
    hypothetical = copy.deepcopy(state)
    hypothetical['P6'] = {k: int(v) for k, v in state['P_max'].items()}
    hypothetical['children'] = {g: {k: soft_cap(hypothetical, f'{g}.{k}') for k in sub}
                                for g, sub in state['children'].items()}
    return compute_card(hypothetical, schema)['CA_calculated']


def revise_pa(state, age, schema, year):
    """Evidence-based appraisal, no annual lucky-D100 counting or trophy bonus."""
    before = state['PA']
    gains = state['annual_gained']
    envelope = reachable_envelope(state, schema)
    r = rng_for(state['seed'], 'scouting', year)
    if state['injuries'] and state['PA'] > envelope and r.random() < .70:
        state['PA'] = max(100, state['PA'] - min(2, state['PA'] - envelope))
        state['pa_range'][0] = min(state['pa_range'][0], state['PA'])
    elif sum(gains.values()) >= 18 and sum(v > 0 for v in gains.values()) >= 8 and state['PA'] < min(envelope, state['pa_range'][1]) and r.random() < .20:
        state['PA'] += 1
    if before != state['PA']:
        state['scouting_events'].append(dict(age=age, before=before, after=state['PA'],
                                            reason='injury_envelope' if state['PA'] < before else 'observed_development'))
    state['annual_gained'].clear()


def run_month(state, schema, env, events=(), adaptive=True, record=True, consolidation=True):
    """Advance exactly one month; two phases, 8 G rolls, 4 P rolls, 12 maintenance."""
    month = state['month']
    age = 18 + month / 12
    env = environment('club', **env)
    # Batch validation is transactional; one bad event cannot leave earlier ones.
    if events:
        proposed = copy.deepcopy(state)
        for event in events:
            register_event(proposed, event)
        state.clear()
        state.update(proposed)
    age_and_body(state, age, env, month)
    paths = list(state['xp'])
    # Rehab reduces work capacity; neither investment nor events negate injury.
    phases = 1 if month < state.get('rehab_until', 0) else 2
    for phase in range(phases):
        selection = rng_for(state['seed'], 'selection', month, phase)
        pool = list(paths)
        for index in range(2):
            path = selection.choices(pool, weights=priorities(state, age, pool, adaptive))[0]
            pool.remove(path)
            for roll_index in range(2):
                roll = rng_for(state['seed'], 'technical', month, phase, index, roll_index).randint(1, 100)
                train(state, path, roll, age, env, month, phase, index * 2 + roll_index, record)
        body_rng = rng_for(state['seed'], 'body', month, phase)
        key = body_rng.choices(P, weights=[1.2, 1.2, 1, 1.05, 1.1, .9])[0]
        for _ in range(2):
            body_training(state, key, body_rng.randint(1, 100), age, env)
    maintenance(state, age, env, month, adaptive, consolidation, record)
    state['month'] += 1
    if state['month'] % 12 == 0:
        revise_pa(state, 18 + state['month'] // 12, schema, state['month'] // 12)
        result = compute_card(state, schema)
        state['yearly'].append(dict(age=18 + state['month'] // 12, CA=result['CA_calculated'],
                                   PA=state['PA'], G9=result['G9'], G_aggregate=result['G_aggregate'],
                                   P_aggregate=result['P_aggregate'], P6=dict(state['P6']),
                                   environment=dict(env), injuries=state['injuries']))


def simulate(schema, card, seed, curve='balanced_progress', stop=40,
             env_name='club', events=(), adaptive=True, record=False,
             development_profile=None, consolidation=True):
    if type(stop) is not int or not 18 <= stop <= 60:
        raise ValueError('stop must be a whole age between 18 and 60')
    events = list(events)
    if any(type(e.get('month')) is not int or not 0 <= e['month'] < 12 * (stop - 18) for e in events):
        raise ValueError('event outside simulation range')
    state = start(card, seed, curve, development_profile)
    initial = compute_card(state, schema)
    state['yearly'].append(dict(age=18, CA=initial['CA_calculated'], PA=state['PA'],
                               G9=initial['G9'], P6=dict(state['P6']),
                               G_aggregate=initial['G_aggregate'], P_aggregate=initial['P_aggregate']))
    by_month = {}
    for event in events:
        by_month.setdefault(event['month'], []).append(event)
    for _ in range(12 * (stop - 18)):
        run_month(state, schema, environment(env_name), by_month.get(state['month'], ()), adaptive, record, consolidation)
    return state


def dump_state(state):
    """Portable snapshot, including ledgers, window expiries and deterministic seed."""
    # Preserve dictionary order because weighted selection uses ordered path lists.
    return json.dumps(state, ensure_ascii=False, allow_nan=False)


def load_state(serialized):
    state = json.loads(serialized)
    if state.get('version') != VERSION:
        raise ValueError('unsupported career state version')
    for key in ('audit', 'annual_gained', 'PA_evidence'):
        state[key] = Counter(state[key])
    return state


def event_from_match(state, match, player_index, match_id, review_quality=1.0):
    """Project actual logged actions into 1-3 drill targets; do not award stats.

    Uses pressure in the logged exchanges, not the final win or a legendary label.
    All matches from this engine are simulated; MATCH_LOG means an executed log,
    not a real-world historical event. Serve logs do not identify subskills and are
    therefore not invented into serve.spin/placement experience here.
    """
    import game_v115 as game
    patched = match.get('ruleset') == 'V1.1.6-HGR-CANDIDATE-1'
    if patched:
        from specialist_rubber_v116 import ACTION_SPECS
    if type(player_index) is not int or player_index not in (0, 1) or not isinstance(match_id, str) or not match_id:
        raise ValueError('invalid match participant or identity')
    counts, pressure = Counter(), Counter()
    for played_game in match.get('games', []):
        if 'points' not in played_game:
            raise ValueError('match requires keep_points=True')
        for point in played_game['points']:
            for shot in point.get('shots', []):
                if shot.get('player') == player_index:
                    action = shot.get('action')
                    if patched:
                        if action in ACTION_SPECS:
                            path = ACTION_SPECS[action]['technique_path']
                        elif action in game.TECH:
                            path = game.TECH[action][0]
                        else:
                            if shot.get('technique_path') is not None:
                                raise ValueError('unregistered action cannot claim technical exposure')
                            continue
                        if shot.get('technique_path') != path:
                            raise ValueError('logged technique path does not match the action registry')
                    elif action in game.TECH:
                        path = game.TECH[action][0]
                    else:
                        continue
                    counts[path] += 1
                    if shot.get('reach') in ('limited', 'bad') or shot.get('fault_prob', 0) >= .2:
                        pressure[path] += 1
    eligible = [p for p in counts if counts[p] >= 8]
    if not eligible:
        raise ValueError('no adequately logged technical exposure')
    paths = sorted(eligible, key=lambda p: (-pressure[p], -counts[p], p))[:3]
    challenge = .55 + .45 * sum(pressure[p] for p in paths) / sum(counts[p] for p in paths)
    content_hash = hashlib.sha256(json.dumps(match, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return dict(id=f'review:{match_id}:{player_index}', month=state['month'], kind='match_review',
                source='MATCH_LOG', evidence_ref=f'sha256:{content_hash}:{player_index}',
                match_id=match_id, match_seed=match.get('seed'), classification='SIMULATED',
                paths=paths, usage={p: counts[p] for p in paths},
                challenge=challenge, review_quality=review_quality,
                pressure={p: pressure[p] for p in paths}, won=match.get('winner') == player_index)
