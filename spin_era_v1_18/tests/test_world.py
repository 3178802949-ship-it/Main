import copy
from concurrent.futures import ThreadPoolExecutor
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Area
import Card
import Game
from common import canonical_json
from world import WorldSession


def cards(n=2):
    result = []
    base = Card.make_ma18()
    base['growth_curve'] = 'foundation_builder'
    result.append(base)
    for i in range(1, n):
        peer = copy.deepcopy(base)
        peer.update(player_id=f'synthetic_peer_{i}', preset_id=f'synthetic_peer_{i}@2006',
                    name_zh=f'合成陪练{i}', source_prototype='SYNTHETIC',
                    origin='SYNTHETIC', historical_reference={'champion_history': [], 'classification': 'NONE'})
        result.append(Card.normalize(peer))
    return result


def phase(month=0, index=0):
    return dict(month=month, phase=index, technical=[
        dict(group='read', specialize=['self_read', 'choice']),
        dict(group='bh', specialize=['defense', 'placement'])], body='stamina')


class WorldTests(unittest.TestCase):
    def new(self, n=2, mode='sandbox'):
        return WorldSession.create(cards(n), 2006, start_date='2006-02-01', mode=mode)

    def test_complete_card_has_current_subvalues_balances_and_sample_rank(self):
        world = self.new()
        card = world.card('ma_long_age18')
        self.assertEqual(sum(map(len, card['children'].values())), 43)
        self.assertEqual(len(card['xp']), 43)
        self.assertEqual(card['CA'], 159)
        self.assertEqual(card['ranking']['match_count'], 0)
        self.assertTrue(all('world_rank' not in row for row in world.rankings()['standings']))
        with self.assertRaisesRegex(ValueError, 'complete ranking pool'):
            world.rankings(complete_pool=True)

    def test_two_phases_advance_month_and_saved_continuation_exactly(self):
        world = self.new()
        world.train_phase('ma_long_age18', phase(), 'phase0')
        recovered = WorldSession.load(world.dump())
        a = world.train_phase('ma_long_age18', phase(index=1), 'phase1')
        b = recovered.train_phase('ma_long_age18', phase(index=1), 'phase1')
        self.assertEqual(a, b)
        self.assertEqual(world.dump(), recovered.dump())
        self.assertEqual(world.data['current_date'], '2006-03-01')

    def test_invalid_or_duplicate_phase_keeps_world_unchanged(self):
        world = self.new()
        before = world.dump()
        with self.assertRaises(ValueError):
            world.train_phase('ma_long_age18', phase(index=1), 'out-of-order')
        self.assertEqual(before, world.dump())
        world.train_phase('ma_long_age18', phase(), 'same')
        after = world.dump()
        with self.assertRaises(ValueError):
            world.train_phase('ma_long_age18', phase(index=1), 'same')
        self.assertEqual(after, world.dump())

    def test_practice_binds_identity_and_review_without_ranking(self):
        world = self.new()
        log = world.play_practice('ma_long_age18', 'synthetic_peer_1', 'practice', 22601)
        self.assertTrue(Game.verify_log(log))
        self.assertTrue(log['isolated_process'])
        self.assertEqual(world.data['ranking']['matches'], {})
        receipt = world.train_phase('ma_long_age18', phase(), 'review-phase', review_match_ids=['practice'])
        self.assertEqual(receipt['budget']['focused_technical'], 4)
        self.assertTrue(world.consistency_check()['valid'])

    def test_full_four_actor_bracket_elo_and_event_points_once(self):
        world = self.new(4)
        event_id = 'sandbox_major_2006_01'
        world.confirm_sandbox_event(event_id)
        result = world.run_event(event_id, list(world.data['players']), 22602)
        self.assertEqual(len(result['bracket']), 3)
        self.assertEqual(result['draw_size'], 4)
        self.assertEqual(len(world.data['ranking']['matches']), 3)
        self.assertEqual(sum(v == 'champion' for v in result['finishes'].values()), 1)
        self.assertEqual(len(world.data['titles']), 1)
        before = world.dump()
        with self.assertRaises(ValueError):
            world.run_event(event_id, list(world.data['players']), 9)
        self.assertEqual(before, world.dump())
        restored = WorldSession.load(before)
        self.assertEqual(restored.rankings(), world.rankings())

    def test_unconfirmed_event_and_reference_mode_do_not_mutate(self):
        world = self.new()
        before = world.dump()
        with self.assertRaises(ValueError):
            world.run_event('sandbox_major_2006_01', list(world.data['players']), 2)
        self.assertEqual(before, world.dump())
        reference = self.new(mode='historical_reference')
        with self.assertRaises(ValueError):
            reference.train_phase('ma_long_age18', phase(), 'readonly')

    def test_future_card_duplicate_identity_and_checkpoint_tamper_rejected(self):
        future = cards()[0]
        future['year'] = 2024
        with self.assertRaises(ValueError):
            WorldSession.create([future], 2006)
        with self.assertRaises(ValueError):
            WorldSession.create(cards() + [cards()[0]], 2006)
        world = self.new()
        checkpoint = json.loads(world.dump())
        checkpoint['payload']['players']['ma_long_age18']['PA'] -= 1
        with self.assertRaisesRegex(ValueError, 'CHECKSUM'):
            WorldSession.load(json.dumps(checkpoint))
        with self.assertRaises(ValueError):
            WorldSession.load(json.dumps({'version': 'legacy', 'month': 1}))

    def test_isolated_games_can_run_concurrently_without_changing_source_cards(self):
        inputs = cards()
        before = canonical_json(inputs)
        def call(_):
            return Game.play_match(inputs, 22603, 'same-repro-match')
        with ThreadPoolExecutor(max_workers=2) as executor:
            a, b = list(executor.map(call, range(2)))
        self.assertEqual(a, b)
        self.assertEqual(before, canonical_json(inputs))
        corrupted = copy.deepcopy(a)
        corrupted['winner'] = 1 - corrupted['winner']
        with self.assertRaises(ValueError):
            Game.verify_log(corrupted)

    def test_calendar_replacement_preserves_history(self):
        world = self.new()
        calendar = Area.calendar_for_year(2006)
        calendar['events'][0]['name'] = '另一项明确的沙盒赛事'
        world.set_calendar(calendar)
        self.assertEqual(len(world.data['calendar_archive']), 1)
        self.assertEqual(world.data['calendar']['events'][0]['name'], calendar['events'][0]['name'])

    def test_npc_cannot_train_ahead_and_formal_entrants_must_share_phase(self):
        world = self.new()
        before = world.dump()
        with self.assertRaisesRegex(ValueError, 'future phase'):
            world.train_phase('synthetic_peer_1', phase(), 'future-npc')
        self.assertEqual(before, world.dump())
        world.train_phase('ma_long_age18', phase(), 'main-phase')
        calendar = copy.deepcopy(world.data['calendar'])
        calendar['events'][0].update(start_date='2006-02-20', end_date='2006-02-22', confirmed=True)
        world.set_calendar(calendar)
        with self.assertRaisesRegex(ValueError, 'stale'):
            world.run_event(calendar['events'][0]['event_id'], list(world.data['players']), 1)
        world.train_phase('synthetic_peer_1', phase(), 'npc-catchup')
        self.assertTrue(world.consistency_check()['valid'])

    def test_future_half_month_event_cannot_feed_earlier_training(self):
        world = self.new()
        calendar = copy.deepcopy(world.data['calendar'])
        calendar['events'][0].update(start_date='2006-02-20', end_date='2006-02-22', confirmed=True)
        world.set_calendar(calendar)
        before = world.dump()
        with self.assertRaisesRegex(ValueError, 'half-month'):
            world.run_event(calendar['events'][0]['event_id'], list(world.data['players']), 1)
        self.assertEqual(before, world.dump())

    def test_practice_requires_current_phase_and_records_review_clock(self):
        world = self.new()
        world.train_phase('ma_long_age18', dict(month=0, phase=0, mode='rest'), 'main-rest')
        before = world.dump()
        with self.assertRaisesRegex(ValueError, 'current world phase'):
            world.play_practice('ma_long_age18', 'synthetic_peer_1', 'future-practice', 22604)
        self.assertEqual(before, world.dump())
        world.train_phase('synthetic_peer_1', dict(month=0, phase=0, mode='rest'), 'peer-rest')
        world.play_practice('ma_long_age18', 'synthetic_peer_1', 'valid-practice', 22604)
        clocks = world.data['match_meta']['valid-practice']['participant_clocks']
        self.assertTrue(all(c == dict(month=0, phase=1) for c in clocks.values()))
        broken = copy.deepcopy(world)
        broken.data['match_meta']['valid-practice']['participant_clocks']['ma_long_age18']['phase'] = 0
        with self.assertRaisesRegex(ValueError, 'contemporaneous'):
            broken.consistency_check()

    def test_calendar_ids_cannot_be_consumed_by_training_or_practice(self):
        world = self.new()
        reserved = 'sandbox_major_2006_01'
        before = world.dump()
        with self.assertRaisesRegex(ValueError, 'reserved'):
            world.train_phase('ma_long_age18', phase(), reserved)
        with self.assertRaisesRegex(ValueError, 'reserved'):
            world.play_practice('ma_long_age18', 'synthetic_peer_1', reserved, 1)
        self.assertEqual(before, world.dump())
        world.train_phase('ma_long_age18', dict(month=0, phase=0, mode='rest'), 'custom-training')
        calendar = copy.deepcopy(world.data['calendar'])
        calendar['events'][0]['event_id'] = 'custom-training'
        after = world.dump()
        with self.assertRaisesRegex(ValueError, 'collides'):
            world.set_calendar(calendar)
        self.assertEqual(after, world.dump())

    def test_year_rollover_reports_calendar_refresh_without_losing_settlement(self):
        world = WorldSession.create(cards(1), 2006, start_date='2006-12-01')
        world.train_phase('ma_long_age18', dict(month=0, phase=0, mode='rest'), 'dec-a')
        world.train_phase('ma_long_age18', dict(month=0, phase=1, mode='rest'), 'dec-b')
        self.assertEqual(world.data['current_date'], '2007-01-01')
        self.assertTrue(world.consistency_check()['calendar_refresh_required'])
        world.set_calendar(Area.calendar_for_year(2007))
        self.assertFalse(world.consistency_check()['calendar_refresh_required'])


if __name__ == '__main__':
    unittest.main()
