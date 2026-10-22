"""Reproduce public event-id privilege bypass using synthetic fixtures only."""
from pathlib import Path
import json
import sys

sys.path.insert(0, '/workspace/spin-era-v1_18-github/spin_era_v1_18')
from simulator import Card, Game, WorldSession

cards = []
for index in range(2):
    card = Card.make_ma18()
    card.update(player_id=f'synthetic-deferred-{index}',
                source_prototype='SYNTHETIC', origin='SYNTHETIC')
    for key in ('personality_profile', 'career117_profile', 'career118_profile'):
        card.pop(key, None)
    cards.append(Card.normalize(card))
world = WorldSession.create(cards, 2006, start_date='2006-02-01',
    world_id='SYNTHETIC-DEFERRED-PROBE', seed=9929)
# A high-fatigue fixture is deliberately injected only into this synthetic world.
for player_id in world.data['players']:
    world.data['players'][player_id]['fatigue'] = 95
ids = list(world.data['players'])
log = Game.play_match([world._match_card(p) for p in ids], 1199,
    'SYNTHETIC-PHANTOM-MATCH', world_id=world.data['world_id'],
    fatigue=[95, 95], best_of=3)
before = world.dump()
try:
    world.settle_match(log, date='2006-02-01')
except ValueError as error:
    rejected = str(error)
else:
    raise AssertionError('expected fatigue rejection')
assert world.dump() == before
receipt = world.settle_match(log, date='2006-02-01',
    event_id='PHANTOM-DOES-NOT-EXIST')
result = dict(classification='SYNTHETIC_NON_HISTORICAL', fatigue=95,
    without_event=rejected, with_event_status=receipt['status'],
    injury_checks=receipt['injuries'],
    event_present='PHANTOM-DOES-NOT-EXIST' in world.data['events'],
    deep_consistency=world.consistency_check(deep=True)['valid'])
assert receipt['status'] == 'applied' and not result['event_present']
assert result['deep_consistency']
Path(__file__).with_name('PHANTOM_EVENT_PROBE.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False, indent=2))
