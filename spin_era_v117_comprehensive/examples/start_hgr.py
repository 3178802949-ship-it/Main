"""Explicit opt-in HGR sandbox; equipment is synthetic, never historical fact."""
from pathlib import Path
import argparse
import copy
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Card
import Game
from world import WorldSession


def roster():
    template = Card.make_ma18()
    result = []
    for index, (hand, style, bh) in enumerate((('right', 'attacker', 'inverted'),
                                             ('left', 'modern_chopper', 'long_pips'))):
        card = copy.deepcopy(template)
        card.update(player_id=f'hgr_synthetic_{index}', preset_id=f'hgr_synthetic_{index}@2006',
            name_zh='原创进攻测试卡' if index == 0 else '异质胶皮削球陪练测试卡',
            source_prototype='SYNTHETIC', origin='SYNTHETIC', hand=hand, style=style,
            rubbers={'fh': 'inverted', 'bh': bh},
            simulation_equipment_assumption='EXPLICIT_SYNTHETIC_TEST_CONFIGURATION_NOT_HISTORICAL',
            historical_reference={'champion_history': [], 'classification': 'NO_REAL_HISTORY'},
            growth_curve='foundation_builder')
        result.append(Card.normalize(card))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('output must be empty; existing saves are preserved')
    args.output.mkdir(parents=True, exist_ok=True)
    world = WorldSession.create(roster(), 2006, start_date='2006-02-01',
        world_id='hgr-explicit-synthetic-demo', seed=11616116,
        main_player_id='hgr_synthetic_0', game_ruleset=Game.PATCH_RULESET)
    (args.output / 'START_WORLD_HGR.json').write_text(world.dump())
    (args.output / 'COMPLETE_CARD_HGR.json').write_text(json.dumps(world.card('hgr_synthetic_0'), ensure_ascii=False, indent=2))
    receipt = dict(classification='SIMULATED_SYNTHETIC', game_ruleset=Game.PATCH_RULESET,
                   note='Equipment/hand configuration is an explicit test assumption, not a real-player assessment.')
    if args.demo:
        match = world.play_practice('hgr_synthetic_0', 'hgr_synthetic_1', 'hgr-demo-practice', 11616117)
        receipt['match'] = {k: match[k] for k in ('match_id', 'seed', 'ruleset', 'winner', 'games_won', 'mean_strokes', 'log_sha256')}
        receipt['training'] = []
        for phase in range(2):
            plan = dict(month=0, phase=phase, mode='train', body='stamina',
                        technical=[dict(group='read', specialize=['self_read', 'choice']), dict(group='bh')])
            receipt['training'].append(world.train_phase('hgr_synthetic_0', plan, f'hgr-demo-train-{phase}',
                review_match_ids=['hgr-demo-practice'] if phase == 0 else ()))
            world.train_phase('hgr_synthetic_1', dict(month=0, phase=phase, mode='rest'), f'hgr-demo-peer-rest-{phase}')
        receipt['consistency'] = world.consistency_check()
        (args.output / 'DEMO_WORLD_HGR.json').write_text(world.dump())
    (args.output / 'DEMO_SUMMARY_HGR.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps(dict(output=str(args.output), date=world.data['current_date'],
                         ruleset=world.data['game_ruleset'], valid=world.consistency_check()['valid']), ensure_ascii=False))


if __name__ == '__main__':
    main()
