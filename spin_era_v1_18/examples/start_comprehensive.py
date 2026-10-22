"""Create a complete V1.1.7 comprehensive card/checkpoint and optional one-month sandbox."""
from pathlib import Path
import argparse
import copy
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from simulator import Card, WorldSession, RULESET


def roster():
    main = Card.make_ma18()
    main['growth_curve'] = 'foundation_builder'
    # Scenario resources are explicit. This means access to national-quality
    # training, not a new claim about a historical selection decision.
    main['career_resources'] = dict(national_eligible=True, investment_units=12)
    peer = copy.deepcopy(main)
    peer.update(player_id='comprehensive_synthetic_chopper', preset_id='comprehensive_synthetic_chopper@2006',
        name_zh='原创削球陪练测试卡', source_prototype='SYNTHETIC', origin='SYNTHETIC',
        style='modern_chopper', hand='left', rubbers=dict(fh='inverted', bh='long_pips'),
        historical_reference=dict(champion_history=[], classification='NO_REAL_HISTORY'),
        simulation_equipment_assumption='SYNTHETIC_TEST_NOT_HISTORICAL_EQUIPMENT')
    for key in ('style_profile', 'personality_profile', 'career117_profile', 'career118_profile'):
        peer.pop(key, None)
    return [Card.normalize(main), Card.normalize(peer)]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--demo', action='store_true', help='execute one month; preserve the initial save')
    parser.add_argument('--full-match', action='store_true', help='explicitly detail the primary demo match')
    args = parser.parse_args()
    if args.full_match and not args.demo:
        parser.error('--full-match requires --demo')
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('output must be empty; existing saves are preserved')
    args.output.mkdir(parents=True, exist_ok=True)
    world = WorldSession.create(roster(), 2006, start_date='2006-02-01',
        world_id='comprehensive-ma18-sandbox', seed=117001, main_player_id='ma_long_age18')
    (args.output / 'START_WORLD_COMPREHENSIVE.json').write_text(world.dump(), encoding='utf-8')
    write_json(args.output / 'COMPLETE_CARD_COMPREHENSIVE.json', world.card('ma_long_age18'))
    report = dict(version=RULESET, classification='SIMULATED',
        scenario='Ma-style age18 test card, not a replay of real history',
        narrative_scope='AGGREGATE_ONLY', receipts=[])
    if args.demo:
        match_id = 'comprehensive-demo-practice'
        match = world.play_practice('ma_long_age18', 'comprehensive_synthetic_chopper', match_id, 117002,
            detail_level='full' if args.full_match else 'summary')
        report['match'] = {k: match[k] for k in ('match_id', 'seed', 'ruleset', 'mode',
            'narrative_scope', 'winner', 'games_won', 'mean_strokes', 'log_sha256')}
        for phase in range(2):
            plan = dict(month=0, phase=phase, mode='train', body='stamina', technical=[
                dict(group='read', specialize=['opponent_read', 'choice']), dict(group='bh')])
            report['receipts'].append(world.train_phase('ma_long_age18', plan, f'demo-train-{phase}',
                environment_name='national' if phase == 0 else 'club',
                review_match_ids=[match_id] if phase == 0 else ()))
            world.train_phase('comprehensive_synthetic_chopper', dict(month=0, phase=phase, mode='rest'),
                f'demo-peer-rest-{phase}')
        if args.full_match:
            report['external_artifacts'] = world.export_artifacts(args.output / 'full_match_artifacts')
        (args.output / 'DEMO_WORLD_COMPREHENSIVE.json').write_text(world.dump(), encoding='utf-8')
        write_json(args.output / 'DEMO_CARD_COMPREHENSIVE.json', world.card('ma_long_age18'))
    if args.demo:
        report['match_narrative'] = world.narrate_match(match_id)
        report['training_narrative'] = world.narrate_training('demo-train-0')
        write_json(args.output / 'NARRATIVE_EXAMPLES.json', dict(match=report['match_narrative'], training=report['training_narrative']))
    report['consistency'] = world.consistency_check(deep=True)
    report['checkpoint_bytes'] = len(world.dump().encode())
    write_json(args.output / 'DEMO_SUMMARY_COMPREHENSIVE.json', report)
    print(json.dumps(dict(output=str(args.output), date=world.data['current_date'],
        ruleset=RULESET, valid=report['consistency']['valid']), ensure_ascii=False))


if __name__ == '__main__':
    main()
