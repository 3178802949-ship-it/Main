"""Run inside an isolated candidate copy; no archived world is loaded/replayed."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ENGINE = Path(sys.argv.pop(1)).resolve()
sys.path.insert(0, str(ENGINE))
from simulator import WorldSession, Card, Game


def world(n=2, fatigue=0):
    cards = []
    for i in range(n):
        card = Card.make_ma18()
        card.update(player_id='synthetic-event-context-' + str(i),
                    source_prototype='SYNTHETIC_NON_HISTORICAL',
                    origin='SYNTHETIC_NON_HISTORICAL')
        cards.append(Card.normalize(card))
    result = WorldSession.create(cards, 2006, start_date='2006-02-01',
                                 seed=613811, world_id='synthetic-event-context-probe')
    for state in result.data['players'].values():
        state['fatigue'] = fatigue
    return result


def external(w, match_id='external'):
    ids = list(w.data['players'])[:2]
    return Game.play_match([w._match_card(p) for p in ids], 613812, match_id,
                          world_id=w.data['world_id'], best_of=3,
                          fatigue=[w.data['players'][p]['fatigue'] for p in ids])


class EventContextPatchTests(unittest.TestCase):
    def test_fake_event_rejected_without_any_mutation(self):
        w = world(fatigue=95)
        log = external(w)
        before = w.dump()
        with self.assertRaisesRegex(ValueError, 'EXTERNAL_EVENT_CONTEXT_FORBIDDEN'):
            w.settle_match(log, date=w.data['current_date'],
                           event_id='PHANTOM-DOES-NOT-EXIST')
        self.assertEqual(w.dump(), before)
        self.assertFalse(w.artifacts)
        with self.assertRaisesRegex(ValueError, 'fatigue requires rest'):
            w.settle_match(log, date=w.data['current_date'])
        self.assertEqual(w.dump(), before)

    def test_external_event_context_forbidden_even_if_event_exists(self):
        w = world()
        w.set_experiment(False, 'previous-existing-event')
        log = external(w)
        before = w.dump()
        with self.assertRaisesRegex(ValueError, 'EXTERNAL_EVENT_CONTEXT_FORBIDDEN'):
            w.settle_match(log, date=w.data['current_date'],
                           event_id='previous-existing-event')
        self.assertEqual(w.dump(), before)

    def test_normal_external_settlement_and_duplicate_still_work(self):
        w = world()
        log = external(w)
        receipt = w.settle_match(log, date=w.data['current_date'])
        self.assertEqual(receipt['status'], 'applied')
        self.assertTrue(all('deferred_to' not in value
                            for value in receipt['injuries'].values()))
        saved = w.dump()
        duplicate = w.settle_match(log, date=w.data['current_date'])
        self.assertEqual(duplicate['status'], 'already_applied')
        self.assertEqual(saved, w.dump())
        self.assertTrue(w.consistency_check(deep=True)['valid'])
        self.assertEqual(WorldSession.load(saved).dump(), saved)

    def test_group_resolves_all_deferred_health_once_with_group_effort(self):
        w = world(3)
        original = WorldSession._injury_chance
        calls = []

        def trace(session, pid, source_id, effort=0.):
            calls.append((pid, source_id, effort))
            return original(session, pid, source_id, effort)

        with patch.object(WorldSession, '_injury_chance', trace):
            result = w.run_group('group-health', list(w.data['players']),
                                 613813, kind='adult_singles', best_of=3)
        self.assertEqual(len(calls), 3)
        self.assertEqual({x[0] for x in calls}, set(w.data['players']))
        self.assertTrue(all(x[1] == 'group-health' for x in calls))
        self.assertEqual(set(result['post_event_health']), set(w.data['players']))
        for pid, source, effort in calls:
            logs = [w.data['matches'][mid] for mid in result['matches']]
            expected = sum(w._effort(log, log['participant_ids'].index(pid))[0]
                           for log in logs if pid in log['participant_ids'])
            self.assertAlmostEqual(effort, expected)
        self.assertTrue(w.consistency_check(deep=True)['valid'])
        saved = w.dump()
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_WORLD_EVENT'):
            w.run_group('group-health', list(w.data['players']), 613813,
                        kind='adult_singles', best_of=3)
        self.assertEqual(w.dump(), saved)

    def test_group_health_failure_rolls_back_full_transaction(self):
        w = world(3)
        before = w.dump()
        original = WorldSession._injury_chance
        calls = []

        def fail_after_first(session, pid, source_id, effort=0.):
            calls.append(pid)
            value = original(session, pid, source_id, effort)
            if len(calls) == 2:
                raise RuntimeError('INJECTED_HEALTH_FAILURE')
            return value

        with patch.object(WorldSession, '_injury_chance', fail_after_first):
            with self.assertRaisesRegex(RuntimeError, 'INJECTED_HEALTH_FAILURE'):
                w.run_group('group-rollback', list(w.data['players']), 613814,
                            kind='adult_singles', best_of=3)
        self.assertEqual(len(calls), 2)
        self.assertEqual(w.dump(), before)
        self.assertFalse(w.artifacts)


if __name__ == '__main__':
    unittest.main(verbosity=2)
