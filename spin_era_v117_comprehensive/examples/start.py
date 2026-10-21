"""Start a clean world, or execute an explicitly synthetic full integration demo."""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Card
from world import WorldSession


def roster():
    base = Card.make_ma18()
    base['growth_curve'] = 'foundation_builder'
    cards = [base]
    for i in range(1, 4):
        other = copy.deepcopy(base)
        other.update(player_id=f'sandbox_peer_{i}', preset_id=f'sandbox_peer_{i}@2006',
            name_zh=f'同水平合成对手{i}', source_prototype='SYNTHETIC', origin='SYNTHETIC',
            historical_reference={'champion_history': [], 'classification': 'NO_REAL_HISTORY'},
            simulated_career={'titles': [], 'matches': [], 'classification': 'SIMULATED'})
        cards.append(Card.normalize(other))
    return cards


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def main():
    parser = argparse.ArgumentParser(description='旋球年代四模块开局与集成示例')
    parser.add_argument('--demo', action='store_true', help='运行四人沙盒淘汰赛及两次训练结算')
    parser.add_argument('--output', type=Path, default=ROOT / 'examples/demo_output')
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('output is not empty; select a new path to preserve existing saves')
    args.output.mkdir(parents=True, exist_ok=True)
    world = WorldSession.create(roster(), 2006, start_date='2006-02-01',
        world_id='v116-four-module-demo', seed=1163001, main_player_id='ma_long_age18')
    (args.output / 'START_WORLD.json').write_text(world.dump())
    write_json(args.output / 'COMPLETE_CARD_MA18.json', world.card('ma_long_age18'))
    summary = dict(classification='SIMULATED', world_id=world.data['world_id'],
        note='Fresh source snapshot; demo results are not auto-loaded into new careers.')
    if args.demo:
        event_id = 'sandbox_major_2006_01'
        world.confirm_sandbox_event(event_id)
        event = world.run_event(event_id, list(world.data['players']), 1163002)
        summary['tournament'] = event
        last_match = next(mid for mid in reversed(world.data['matches'])
                          if 'ma_long_age18' in world.data['matches'][mid]['participant_ids'])
        receipts = []
        for phase in range(2):
            plan = dict(month=0, phase=phase, mode='train', body='stamina' if phase else 'agility',
                technical=[dict(group='read', specialize=['self_read', 'choice']),
                           dict(group='bh', specialize=['defense', 'placement'])])
            receipt = world.train_phase('ma_long_age18', plan, f'demo-training-{phase}',
                review_match_ids=[last_match] if phase == 0 else ())
            receipts.append(receipt)
        summary['training'] = receipts
        summary['sample_ranking'] = world.rankings()
        summary['check'] = world.consistency_check()
        (args.output / 'DEMO_WORLD.json').write_text(world.dump())
        write_json(args.output / 'COMPLETE_CARD_AFTER_DEMO.json', world.card('ma_long_age18'))
    write_json(args.output / 'DEMO_SUMMARY.json', summary)
    print(json.dumps(dict(output=str(args.output), mode='sandbox', current_date=world.data['current_date'],
        CA=world.card('ma_long_age18')['CA'], fatigue=world.card('ma_long_age18')['fatigue'],
        matches=len(world.data['matches']), consistency=world.consistency_check()['valid']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
