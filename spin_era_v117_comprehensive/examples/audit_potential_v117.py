"""Audit all preset potential contracts without running a simulated career.

Preparation changes only modelled future development/appraisal metadata. This
structural inventory does not show that training will attain the stated ceiling.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common import SCHEMA, canonical_json
import career_v116 as baseline
import career_v117 as candidate


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def traits(card):
    return {key: copy.deepcopy(card[key]) for key in ('children', 'P6', 'G9', 'CA')}


def summary(rows):
    n = len(rows)
    return dict(profiles=n,
        old_source_PA_above_envelope=sum(row['old_gap_to_source_PA'] > 0 for row in rows),
        old_source_PA_gap_over_4=sum(row['old_gap_to_source_PA'] > 4 for row in rows),
        new_source_PA_above_envelope=sum(row['new_gap_to_source_PA'] > 0 for row in rows),
        new_source_PA_gap_over_4=sum(row['new_gap_to_source_PA'] > 4 for row in rows),
        new_public_PA_above_envelope=sum(row['new_gap_to_public_PA'] > 0 for row in rows),
        new_latent_target_above_envelope=sum(row['new_gap_to_latent_target'] > 0 for row in rows),
        new_envelope_within_2_of_latent_target=sum(abs(row['new_gap_to_latent_target']) <= 2 for row in rows),
        minimum_new_envelope_minus_source_PA=min((row['new_reachable_envelope'] - row['source_PA'] for row in rows), default=None),
        maximum_public_PA_interval_width=max((row['public_PA_interval'][1] - row['public_PA_interval'][0] for row in rows), default=None),
        maximum_initial_public_discount=max((row['source_PA'] - row['public_PA'] for row in rows), default=None),
        current_43_P6_G9_CA_preserved=sum(row['current_numeric_traits_preserved'] for row in rows))


def audit(seed=117, strategy=candidate.DEFAULT_CONFIG):
    if type(seed) is not int or strategy not in candidate.CONFIGS:
        raise ValueError('integer seed and supported development strategy required')
    data = ROOT / 'data/presets_normalized.json'
    files = [data, ROOT / 'data/original/spin_era_v013_frozen_attribute_schema.json',
             ROOT / 'runtime/career_v117.py', ROOT / 'runtime/career_v116.py',
             ROOT / 'runtime/career_v114.py', ROOT / 'runtime/card_training_v112.py',
             ROOT / 'common/__init__.py', Path(__file__).resolve()]
    fingerprints = {str(path.relative_to(ROOT)): digest(path) for path in files}
    profiles = json.loads(data.read_text())['profiles']
    if len(profiles) != 370:
        raise AssertionError('the declared release preset inventory must contain 370 snapshots')
    rows = []
    identities = set()
    for source in profiles:
        original = copy.deepcopy(source)
        identity = (source['player_id'], source['year'])
        if identity in identities:
            raise AssertionError(f'duplicate preset identity: {identity}')
        identities.add(identity)
        old_state = baseline.start(source, seed=seed, development_profile=source['development_profile'])
        old_envelope = baseline.reachable_envelope(old_state, SCHEMA)
        prepared = candidate.prepare_card(source, seed=seed, strategy=strategy)
        profile = prepared['career117_profile']
        new_envelope = profile['reachable_envelope']
        if source != original:
            raise AssertionError(f'preparation or old-envelope calculation mutated source: {identity}')
        unchanged = traits(source) == traits(prepared)
        if not unchanged:
            raise AssertionError(f'preparation changed current technical/body ratings: {identity}')
        interval = prepared['pa_range']
        if not interval[0] <= prepared['PA'] <= interval[1] or interval[1] - interval[0] > 6:
            raise AssertionError(f'public potential interval exceeds the declared narrow band: {identity}')
        source_pa = source['PA']
        rows.append(dict(player_id=source['player_id'], year=source['year'],
            age=source.get('age_approx', source.get('age')), source_classification=source.get('classification'),
            current_CA=source['CA'], source_PA=source_pa, public_PA=prepared['PA'],
            public_PA_interval=list(interval), latent_target=profile['latent_target'],
            old_reachable_envelope=old_envelope, new_reachable_envelope=new_envelope,
            old_gap_to_source_PA=source_pa - old_envelope,
            new_gap_to_source_PA=source_pa - new_envelope,
            new_gap_to_public_PA=prepared['PA'] - new_envelope,
            new_gap_to_latent_target=profile['latent_target'] - new_envelope,
            grandfathered_over_cap=bool(source.get('grandfathered_over_cap')),
            grandfathered_paths=[entry['path'] for entry in source.get('grandfathered_over_cap', [])],
            current_numeric_traits_preserved=unchanged,
            current_numeric_traits_sha256=hashlib.sha256(canonical_json(traits(source)).encode()).hexdigest(),
            development_profile_classification=prepared['development_profile'].get('classification')))
    changed = [name for name, old in fingerprints.items() if digest(ROOT / name) != old]
    if changed:
        raise AssertionError(f'inputs changed while structural audit was running: {changed}')
    groups = {'all': lambda row: True,
              'age_le18': lambda row: row['age'] <= 18,
              'age_le20': lambda row: row['age'] <= 20,
              'age_le23': lambda row: row['age'] <= 23,
              'age_ge30': lambda row: row['age'] >= 30}
    results = {}
    for name, criterion in groups.items():
        selected = [row for row in rows if criterion(row)]
        results[name] = dict(including_observed_cap_exceptions=summary(selected),
                            excluding_observed_cap_exceptions=summary([row for row in selected if not row['grandfathered_over_cap']]))
    return dict(version=candidate.VERSION, status='STRUCTURAL_PREPARATION_AUDIT_PASSED', seed=seed,
        strategy=strategy, presets=370, source_sha256=fingerprints,
        source_fingerprints_stable_at_finish=True, current_numeric_traits_preserved=True,
        definitions=dict(
            old_envelope='Legacy reachable_envelope: P6 set to old P_max and every technical child to old soft_cap.',
            new_envelope='V1.1.7 prepared latent caps with estimated future body maxima; not actual training output.',
            gap='Potential target minus envelope: positive means the labelled target exceeds the structural envelope.',
            current_numeric_traits='All 43 learned technical values, P6, G9 and CA, excluding deliberately revised PA appraisal.',
            public_PA='Initial narrow appraisal, which can differ from source retrospective PA and the latent model target.'),
        limitations=[
            'This is a structural consistency audit, not growth, championship, real-world potential or population validation.',
            'Legacy cap envelopes can understate an already observed grandfathered skill; all statistics are therefore also reported excluding those snapshots.',
            'The 370 entries are annual snapshots, not 370 independent contemporaneous athletes.',
            'A compatible estimated envelope is necessary but does not guarantee the career reaches it.'
        ], summary=results, profiles=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=117)
    parser.add_argument('--strategy', choices=tuple(candidate.CONFIGS), default=candidate.DEFAULT_CONFIG)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/v117/POTENTIAL_AUDIT.json')
    parser.add_argument('--replace', action='store_true', help='Explicitly replace this generated audit after source changes')
    args = parser.parse_args()
    if args.output.exists() and not args.replace:
        parser.error('output already exists; preserve it or explicitly use --replace after reviewing source changes')
    report = audit(args.seed, args.strategy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({key: report[key] for key in ('status', 'presets', 'strategy')}, ensure_ascii=False))
    print(json.dumps(report['summary']['age_le20'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
