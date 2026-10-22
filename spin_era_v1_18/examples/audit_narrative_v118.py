"""Execute small real matches, then audit diverse evidence-bound narrations."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import canonical_json
from Card import v118 as Card
from Game import v118 as Game
from Area import v118 as Area
from Training import v118 as Training
import career_v116
import narrative_v118 as narrative


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixtures():
    result = []
    for index, (label, year, style, rubber, hand) in enumerate((
            ('equal_attacking', 2006, 'attacker', 'inverted', 'left'),
            ('chopper', 2012, 'modern_chopper', 'long_pips', 'right'),
            ('short_pips', 2024, 'attacker', 'short_pips', 'left'),
            ('olympic_horizon', 2028, 'attacker', 'inverted', 'right'))):
        pair = []
        for player in range(2):
            card = copy.deepcopy(Card.make_ma18())
            card.update(player_id=f'narrative_case_{index}_{player}', preset_id=f'narrative_case_{index}_{player}@{year}',
                name_zh=f'原创测试员{index+1}{"甲乙"[player]}', source_prototype='SYNTHETIC', origin='SYNTHETIC',
                year=year, snapshot_date=f'{year}-01-01', birth_year=year-18,
                style=style if player else 'attacker', hand=hand if player else 'right',
                rubbers=dict(fh='inverted', bh=rubber if player else 'inverted'),
                historical_reference=dict(champion_history=[], classification='NO_REAL_HISTORY'))
            for key in ('style_profile', 'personality_profile'):
                card.pop(key, None)
            pair.append(Card.normalize(card))
        result.append((label, year, pair))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/v118/NARRATIVE_AUDIT')
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('use an empty output directory to preserve earlier evidence')
    args.output.mkdir(parents=True, exist_ok=True)
    names = ('narrative_v118.py', 'Card/v118.py', 'Game/v118.py', 'Game/worker_v118.py',
             'Game/preferences_v118.py', 'Area/v118.py', 'Training/v118.py', 'runtime/career_v118.py',
             'data/player_profiles_v118.json', 'examples/audit_narrative_v118.py')
    sources = {name: digest(ROOT / name) for name in names}
    plan = dict(version=narrative.VERSION, match_seed_base=11897000, real_matches=8,
        variants_per_match=12, source_sha256=sources,
        classification='SYNTHETIC_NARRATIVE_AUDIT_NOT_MATCH_BALANCE_CALIBRATION')
    (args.output / 'PREDECLARED_PLAN.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    rows, samples, formats, checks, count = [], [], set(), 0, 0
    for case_index, (label, year, cards) in enumerate(fixtures()):
        for mode in ('summary', 'full'):
            seed = 11897000 + case_index * 10 + int(mode == 'full')
            log = Game.play_match(cards, seed, f'narrative:{label}:{mode}', detail_level=mode)
            original = canonical_json(log)
            day = f'{year}-02-01' if year < 2028 else '2028-07-01'
            era, history, template_ids = Area.context_for_date(day), {}, []
            for variant in range(12):
                report = narrative.render_match(log, cards, seed=seed+variant,
                    era=era, as_of_year=year, as_of_date=day, history=history)
                assert narrative.verify_evidence(report, dict(match=log, cards=cards, era=era))
                if mode == 'summary':
                    assert report['narrative_scope'] == 'AGGREGATE_ONLY'
                    assert '逐板记录中' not in report['text']
                    assert '聚合估计' in report['text']
                else:
                    assert report['narrative_scope'] == 'EXECUTED_SHOTS_ONLY'
                if template_ids:
                    assert template_ids[-1] != report['template_id']
                assert len(report['history']['recent_templates']) <= narrative.HISTORY_LIMIT
                history = report['history']
                template_ids.append(report['template_id'])
                formats.add(report['template_id'])
                checks += len(report['facts'])
                count += 1
                if variant == 0:
                    samples.append(dict(case=label, mode=mode, narrative=report))
            assert canonical_json(log) == original
            if mode == 'full':
                compact = Game.compact_log(log)
                without = narrative.render_match(compact, seed=seed)
                with_full = narrative.render_match(compact, seed=seed, detail_artifact=log)
                assert without['narrative_scope'] == 'AGGREGATE_ONLY'
                assert with_full['narrative_scope'] == 'EXECUTED_SHOTS_ONLY'
                assert narrative.verify_evidence(with_full, dict(match=compact, detail=log))
            rows.append(dict(case=label, mode=mode, seed=seed, log_sha256=log['log_sha256'],
                             generated=12, used_templates=sorted(set(template_ids)),
                             input_log_unchanged=True, compact_scope_tested=mode == 'full'))
    state = Training.initialize(Card.make_ma18(), seed=11897091)
    plan0 = dict(month=0, phase=0, mode='train', body='stamina',
        technical=[dict(group='read', specialize=['opponent_read', 'choice']), dict(group='bh')])
    receipt = Training.settle_phase(state, plan0, career_v116.environment('club'), 'narrative-audit-training')
    trained = narrative.render_training(receipt)
    assert narrative.verify_evidence(trained, dict(training=receipt))
    samples.append(dict(case='actual_training', narrative=trained))
    rest = Training.settle_phase(state, dict(month=0, phase=1, mode='rest'),
                                career_v116.environment('club'), 'narrative-audit-rest')
    rested = narrative.render_training(rest)
    assert narrative.verify_evidence(rested, dict(training=rest))
    assert '突破' not in rested['text']
    samples.append(dict(case='actual_rest', narrative=rested))
    assert all(digest(ROOT/name) == value for name, value in sources.items()), 'source changed during audit'
    report = dict(**{k:v for k,v in plan.items() if k!='source_sha256'}, source_sha256=sources,
        status='EVIDENCE_AND_SCOPE_AUDIT_PASSED', generated_match_narratives=count,
        exact_fact_references_checked=checks, unique_result_templates=len(formats),
        actual_training_receipts=2, rows=rows, source_fingerprints_unchanged=True,
        limitations=['Eight real synthetic matches audit narrative contracts, not all natural-language quality.',
                    'There are eight result templates; broad literary generation remains host work with source constraints.',
                    'Personality guidance is labelled and separate, not a verified private-character description.',
                    'The unchanged specialist light-model calibration limit is not certified by this audit.'])
    (args.output/'NARRATIVE_AUDIT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (args.output/'NARRATIVE_SAMPLES.json').write_text(json.dumps(samples, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','source_sha256')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
