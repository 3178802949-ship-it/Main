"""Synthetic read-only V1.18 ranking/draw probes; never historic matches."""
from pathlib import Path
import hashlib
import json
import sys

BASE = Path('/workspace/spin-era-v1_18-github/spin_era_v1_18')
sys.path.insert(0, str(BASE))
from simulator import Card, WorldSession
from Game.competition_v1_18 import historical_replacement


def main():
    result = dict(classification='SYNTHETIC_NON_HISTORICAL_PROBE',
                  historical_matches_replayed=0, official_2007_events=0)
    entries = [dict(player_id='a', qualification_tier='q'),
               dict(player_id='b', qualification_tier='q')]
    draw = historical_replacement(entries, 'a', seed=0, qualification_tier='q')
    result['replacement_can_duplicate_player'] = dict(
        requested_player='a', input_ids=['a', 'b'],
        output_ids=[e['player_id'] for e in draw['draw']],
        removed_player_id=draw['removed_player_id'], status=draw['status'])

    book = Card.RankingBook()
    for pid in ('youth-champion', 'adult-peer'):
        book.register_player(pid)
    book.record_event('youth-champion', 'synthetic-2006', '2006-02-01',
                      'pro_tour_open', 'champion', kind='youth_singles')
    result['youth_query_is_missing'] = dict(
        youth_points=book.snapshot()['players']['youth-champion']['youth_points'],
        public_world_ranking=book.world_ranking('2006-02-01',
            ['youth-champion', 'adult-peer']))

    cards = []
    for index in range(2):
        card = Card.make_ma18()
        card.update(player_id=f'synthetic-adult-{index}',
            name_zh=f'成年资格测试{index}', source_prototype='SYNTHETIC',
            origin='SYNTHETIC', age_approx=30, model_start_age=30, birth_year=1976)
        for name in ('personality_profile', 'career117_profile', 'career118_profile'):
            card.pop(name, None)
        cards.append(Card.normalize(card))
    world = WorldSession.create(cards, 2006, start_date='2006-02-01',
        world_id='SYNTHETIC-AGE-PROBE', seed=6001)
    group = world.run_group('SYNTHETIC-NOT-HISTORICAL-YOUTH',
        list(world.data['players']), 2, best_of=3, kind='youth_singles')
    result['adult_can_play_youth_group'] = dict(
        ages=[world.card(p)['age'] for p in world.data['players']],
        type=group['type'], kind=group['kind'], matches=len(group['matches']),
        youth_rating_match_records=len(world.data['ranking']['matches']),
        consistency=world.consistency_check(deep=True)['valid'])
    names = ('Game/competition_v1_18.py', 'world_v1_18.py',
             'world_extensions_v1_18.py', 'Card/__init__.py',
             'runtime/ranking_v112.py', 'Area/__init__.py',
             'Area/v117.py', 'Area/v118.py', 'Area/v1_18.py')
    result['source_sha256'] = {n: hashlib.sha256((BASE/n).read_bytes()).hexdigest()
                               for n in names}
    assert result['replacement_can_duplicate_player']['output_ids'] == ['a', 'a']
    assert result['adult_can_play_youth_group']['ages'] == [30.0, 30.0]
    assert result['adult_can_play_youth_group']['consistency']
    path = Path(__file__).with_name('PROBE_RESULTS.json')
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
