"""Career integration checks: actual Game/Training/Ranking, no engine doubles."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import Card
import Game
from Area import v117 as Area
from world_v117 import WorldSession, RULESET, VERSION


def cards(n=2, *, year=2006, elite=False):
    result = []
    for i in range(n):
        card = copy.deepcopy(Card.make_ma18())
        card.update(player_id=f'world117_{i}', preset_id=f'world117_{i}@{year}',
                    source_prototype='SYNTHETIC', origin='SYNTHETIC',
                    year=year, snapshot_date=f'{year}-01-01', birth_year=year-18,
                    historical_reference={'champion_history': [], 'classification': 'NONE'})
        if elite:
            card['children'] = {g: {k: 145 for k in subs} for g, subs in card['children'].items()}
            card['P6'] = {key: 145 for key in card['P6']}
            card['PA'] = 200
        result.append(Card.normalize(card))
    return result


def phase(month=0, index=0, *, rest=False):
    if rest:
        return dict(month=month, phase=index, mode='rest')
    return dict(month=month, phase=index, technical=[
        dict(group='read', specialize=['self_read', 'choice']),
        dict(group='bh', specialize=['defense', 'placement'])], body='stamina')


def close_phase(world, *, rest=True, prefix='close'):
    for pid in world.data['players']:
        s = world.data['players'][pid]
        world.train_phase(pid, phase(s['month'], s['training_release']['phase'], rest=rest),
                          f'{prefix}:{pid}:{s["month"]}:{s["training_release"]["phase"]}')


class World117Tests(unittest.TestCase):
    def new(self, n=2, *, year=2006, start=None, elite=False):
        return WorldSession.create(cards(n, year=year, elite=elite), year,
                                   start_date=start or f'{year}-02-01', seed=117)

    def specialist_world(self, *, rubber='long_pips', chopper=True, mask_family=False):
        inputs = cards(4)
        inputs[-1].update(style='modern_chopper' if chopper else 'attacker',
                          rubbers=dict(fh='inverted', bh=rubber))
        if rubber == 'anti_spin':
            inputs[-1]['experimental_anti_spin'] = True
        if mask_family:
            inputs[-1]['tactical_family'] = 'attacker'
        world = WorldSession.create(inputs, 2006, start_date='2006-02-01', seed=117)
        world.confirm_sandbox_event('sandbox_major_2006_01')
        return world

    def test_explicit_ruleset_card_has_learned_and_effective_values(self):
        world = self.new()
        card = world.card('world117_0')
        self.assertEqual(world.data['version'], VERSION)
        self.assertEqual(world.data['game_ruleset'], RULESET)
        self.assertEqual(sum(map(len, card['children'].values())), 43)
        self.assertIn('learned_children', card)
        self.assertIn('body_limitations', card)
        self.assertEqual(card['career_resources']['national_eligible'], False)
        self.assertFalse(world.rankings()['complete_pool'] if 'complete_pool' in world.rankings() else False)
        game_card = world._match_card('world117_0')
        for forbidden in ('PA', 'xp', 'permits', 'simulated_career', 'ranking', 'career117_profile'):
            self.assertNotIn(forbidden, game_card)
        self.assertEqual(game_card['children'], card['children'])

    def test_summary_is_actual_aggregate_and_effort_charges_fatigue(self):
        world = self.new()
        before = world.data['players']['world117_0']['fatigue']
        result = world.play_practice('world117_0', 'world117_1', 'aggregate', 11701)
        self.assertEqual(result['mode'], 'summary')
        self.assertEqual(result['narrative_scope'], 'AGGREGATE_ONLY')
        self.assertEqual(world.artifacts, {})
        saved = world.data['matches']['aggregate']
        self.assertTrue(Game.verify_log(saved))
        self.assertTrue(all('points' not in game for game in saved['games']))
        delta = world.data['match_meta']['aggregate']['fatigue_cost']['world117_0']
        self.assertGreater(delta, 2)
        self.assertAlmostEqual(world.data['players']['world117_0']['fatigue']-before, delta, places=5)
        self.assertEqual(world.data['ranking']['matches'], {})

    def test_practice_cannot_repeat_without_time_or_recovery(self):
        world = self.new()
        accepted = 0
        for i in range(20):
            before = world.dump()
            try:
                world.play_practice('world117_0', 'world117_1', f'finite:{i}', 11800+i)
            except ValueError:
                self.assertEqual(world.dump(), before)
                break
            accepted += 1
        self.assertGreater(accepted, 1)
        self.assertLessEqual(accepted, 15)
        self.assertLess(accepted, 20)
        self.assertLessEqual(world.data['activity']['world117_0']['competition_days'], 15)

    def test_event_training_and_rest_share_fifteen_day_budget(self):
        world = self.new(4)
        cal = copy.deepcopy(world.data['calendar'])
        event = cal['events'][0]
        event.update(start_date='2006-02-01', end_date='2006-02-13', confirmed=True, travel_days=1)
        world.set_calendar(cal)
        result = world.run_event(event['event_id'], list(world.data['players']), 11702)
        self.assertEqual(result['time_cost_days'], 14)
        before = world.dump()
        with self.assertRaisesRegex(ValueError, 'shared half-month budget'):
            world.train_phase('world117_0', phase(), 'overbook', training_days=2)
        self.assertEqual(before, world.dump())
        receipt = world.train_phase('world117_0', phase(), 'one-day')
        summary = receipt['world_settlement']
        self.assertEqual(summary['training_days'], 1)
        self.assertEqual(summary['competition_days'] + summary['training_days'] + summary['rest_days'], 15)
        self.assertAlmostEqual(summary['training_fraction'], .1)
        self.assertAlmostEqual(summary['recovery_fraction'], 1/15)
        self.assertNotIn('focused', world.data['events']['one-day'])

    def test_practice_after_tournament_uses_new_day(self):
        world = self.new(4)
        eid = 'sandbox_major_2006_01'
        world.confirm_sandbox_event(eid)
        world.run_event(eid, list(world.data['players']), 11703)
        world.play_practice('world117_0', 'world117_1', 'after-event', 11704)
        self.assertEqual(world.data['match_meta']['after-event']['date'], '2006-02-14')

    def test_practice_on_event_start_prevents_overlapping_entry(self):
        world = self.new(4)
        cal = copy.deepcopy(world.data['calendar'])
        event = cal['events'][0]
        event.update(start_date='2006-02-01', end_date='2006-02-04', confirmed=True)
        world.set_calendar(cal)
        world.play_practice('world117_0', 'world117_1', 'same-day-practice', 11721)
        before = world.dump()
        with self.assertRaisesRegex(ValueError, 'competition on the event start day'):
            world.run_event(event['event_id'], list(world.data['players']), 11722)
        self.assertEqual(before, world.dump())

    def test_weak_title_has_points_but_no_elite_breakthrough_or_frontier(self):
        world = self.new(4)
        eid = 'sandbox_major_2006_01'
        before = {pid: copy.deepcopy(s['children']) for pid, s in world.data['players'].items()}
        world.confirm_sandbox_event(eid)
        result = world.run_event(eid, list(world.data['players']), 11705)
        winner = result['winner']
        self.assertEqual(len(world.data['ranking']['matches']), 3)
        self.assertEqual(len(world.data['titles']), 1)
        self.assertFalse(result['development_qualification']['eligible'])
        self.assertIsNone(result['champion_development'])
        self.assertEqual(world.data['resources'][winner]['frontier_tokens'], 0)
        self.assertFalse(world.data['resources'][winner]['national_eligible'])
        self.assertEqual(before[winner], world.data['players'][winner]['children'])
        checkpoint = world.dump()
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            world.run_event(eid, list(world.data['players']), 11706)
        self.assertEqual(checkpoint, world.dump())
        self.assertEqual(WorldSession.load(checkpoint).rankings(), world.rankings())

    def test_actual_elite_opposition_unlocks_limited_specific_opportunity(self):
        world = self.new(4, elite=True)
        eid = 'sandbox_major_2006_01'
        world.confirm_sandbox_event(eid)
        result = world.run_event(eid, list(world.data['players']), 11707)
        evidence = result['development_qualification']
        self.assertTrue(evidence['eligible'])
        self.assertGreaterEqual(evidence['near_peer_wins'], 2)
        self.assertGreaterEqual(evidence['mean_opponent_CA'], 165)
        event = result['champion_development']
        self.assertTrue(event['granted'])
        self.assertLessEqual(len(event['paths']), 3)
        self.assertTrue(all(event['usage'][p] >= 8 for p in event['paths']))
        budget = world.data['resources'][result['winner']]
        self.assertEqual(budget['frontier_tokens'], 1)
        self.assertEqual(budget['reward_tokens_granted'], 1)
        self.assertEqual(budget['championship_windows'], 1)

        winner, main = result['winner'], world.data['main_player_id']
        if winner != main:
            world.train_phase(main, phase(rest=True), 'main-first')
        world.train_phase(winner, phase(), 'earned-frontier', environment_name='frontier')
        self.assertEqual(world.data['resources'][winner]['frontier_tokens'], 0)
        if winner != main:
            world.train_phase(main, phase(index=1, rest=True), 'main-second')
        checkpoint = world.dump()
        with self.assertRaisesRegex(ValueError, 'finite earned opportunity'):
            world.train_phase(winner, phase(index=1), 'free-second-frontier', environment_name='frontier')
        self.assertEqual(checkpoint, world.dump())

    def test_environment_needs_finite_resources_and_qualification(self):
        world = self.new()
        original = world.dump()
        for name in ('national', 'frontier'):
            with self.assertRaises(ValueError):
                world.train_phase('world117_0', phase(), f'free-{name}', environment_name=name)
            self.assertEqual(world.dump(), original)
        receipt = world.invest_training('world117_0', 'camp', units=3)
        self.assertFalse(receipt['official_membership_granted'])
        outcome = world.train_phase('world117_0', phase(), 'paid-national', environment_name='national')
        self.assertEqual(outcome['budget_remaining']['investment_units'], 8)
        self.assertEqual(outcome['world_settlement']['investment_cost'], 1)

    def test_injury_forbids_match_and_rest_rehabilitates_on_clock(self):
        world = self.new()
        world.apply_injury('world117_0', 'scenario-injury', severity=1)
        checkpoint = world.dump()
        with self.assertRaisesRegex(ValueError, 'rehabilitation'):
            world.play_practice('world117_0', 'world117_1', 'forbidden', 11708)
        self.assertEqual(checkpoint, world.dump())
        initial = world.data['players']['world117_0']['fatigue']
        for i in range(4):
            close_phase(world, prefix=f'rehab{i}')
        self.assertEqual(world.data['players']['world117_0']['month'], 2)
        self.assertLess(world.data['players']['world117_0']['fatigue'], initial)
        world.play_practice('world117_0', 'world117_1', 'return', 11709)
        self.assertEqual(len(world.data['matches']), 1)

    def test_save_resume_continuation_identical_and_compact_training(self):
        world = self.new()
        world.play_practice('world117_0', 'world117_1', 'review-source', 11710)
        world.train_phase('world117_0', phase(), 'first', review_match_ids=['review-source'])
        recovered = WorldSession.load(world.dump())
        for item in (world, recovered):
            item.train_phase('world117_1', phase(), 'peer-first')
            item.train_phase('world117_0', phase(index=1), 'next')
        self.assertEqual(world.dump(), recovered.dump())
        self.assertNotIn('phase_log', world.data['events']['first'])
        self.assertLess(len(json.dumps(world.data['events']['first'])), 2500)

    def test_cross_2027_into_2028_and_stop_at_olympic_horizon(self):
        world = self.new(year=2027, start='2027-12-01')
        for i in range(2):
            close_phase(world, prefix=f'year{i}')
        self.assertEqual(world.data['current_date'], '2028-01-01')
        self.assertEqual(world.data['calendar']['year'], 2028)
        self.assertEqual(world.data['era']['classification'], 'SIMULATED_FORWARD')
        self.assertTrue(all(e['future_schedule'] for e in world.data['calendar']['events']))
        for i in range(14):
            close_phase(world, prefix=f'last{i}')
        self.assertTrue(world.data['completed'])
        self.assertEqual(world.data['current_date'], Area.HORIZON_END)
        restored = WorldSession.load(world.dump())
        with self.assertRaisesRegex(ValueError, 'horizon'):
            restored.train_phase('world117_0', phase(8, 0, rest=True), 'beyond')

    def test_full_log_export_is_optional_external_and_can_reattach(self):
        world = self.new()
        raw = world.play_practice('world117_0', 'world117_1', 'full', 11711, detail_level='full')
        self.assertEqual(len(world.artifacts), 1)
        serialized = world.dump()
        self.assertLess(len(serialized), 100000)
        recovered = WorldSession.load(serialized)
        self.assertEqual(recovered.artifacts, {})
        with tempfile.TemporaryDirectory() as directory:
            paths = world.export_artifacts(directory)
            digest = recovered.attach_artifact(paths[0])
            self.assertEqual(digest, raw['log_sha256'])
            self.assertEqual(recovered.artifacts[digest], raw)
        self.assertEqual(recovered.dump(), serialized)

    def test_resigned_checkpoint_still_checks_immutable_audit_payloads(self):
        world = self.new()
        world.train_phase('world117_0', phase(rest=True), 'audited')
        wrapper = json.loads(world.dump())
        wrapper['payload']['events']['audited']['CA_after'] += 1
        encoded = json.dumps(wrapper['payload'], ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        wrapper['sha256'] = hashlib.sha256(encoded.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'audit chain'):
            WorldSession.load(json.dumps(wrapper))

    def test_resigned_checkpoint_rejects_changed_ruleset_fingerprint(self):
        world = self.new()
        checkpoint = world.dump()
        self.assertEqual(WorldSession.load(checkpoint).dump(), checkpoint)
        wrapper = json.loads(checkpoint)
        fingerprint = wrapper['payload']['ruleset_fingerprint']
        fingerprint['files']['Game/light_v117.py'] = '0'*64
        encoded = json.dumps(wrapper['payload'], ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        wrapper['sha256'] = hashlib.sha256(encoded.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'RULESET_FINGERPRINT_MISMATCH:Game/light_v117.py'):
            WorldSession.load(json.dumps(wrapper))
        world.data['ruleset_fingerprint']['files']['runtime/ranking_v112.py'] = '1'*64
        with self.assertRaisesRegex(ValueError, 'RULESET_FINGERPRINT_MISMATCH:runtime/ranking_v112.py'):
            world.consistency_check(deep=True)

    def test_specialist_formal_summary_rolls_back_then_requires_real_opt_in(self):
        world = self.specialist_world()
        eid = 'sandbox_major_2006_01'
        before = world.dump()
        with self.assertRaisesRegex(ValueError, 'SPECIALIST_SUMMARY_REQUIRES_EXPLICIT_EXPERIMENTAL_OPT_IN'):
            world.run_event(eid, list(world.data['players']), 11731)
        self.assertEqual(world.dump(), before)
        self.assertEqual(world.data['matches'], {})
        self.assertEqual(world.data['ranking']['matches'], {})
        self.assertEqual(world.data['entries'], [])
        self.assertEqual(world.data['titles'], [])
        self.assertEqual(world.artifacts, {})
        self.assertFalse(world.rankings()['uncalibrated_specialist_summary'])

        result = world.run_event(eid, list(world.data['players']), 11731,
                                  allow_experimental_specialist_summary=True)
        self.assertEqual(result['calibration_status'], 'UNCALIBRATED')
        self.assertEqual(result['experimental_scope'], 'SPECIALIST_SUMMARY')
        self.assertTrue(result['allow_experimental_specialist_summary'])
        self.assertEqual([row['player_id'] for row in result['specialist_participants']], ['world117_3'])
        self.assertEqual(len(result['bracket']), 3)
        self.assertEqual(len(world.data['ranking']['matches']), 3)
        self.assertEqual(len(world.data['entries']), 4)
        self.assertEqual(len(world.data['titles']), 1)
        self.assertTrue(all(log['source_mode'] == 'summary' for log in world.data['matches'].values()))
        self.assertTrue(all(meta['calibration_status'] == 'UNCALIBRATED' for meta in world.data['match_meta'].values()))
        self.assertEqual(world.artifacts, {})
        standings = world.rankings()
        self.assertTrue(standings['uncalibrated_specialist_summary'])
        self.assertEqual(standings['uncalibrated_specialist_summary_event_ids'], [eid])
        self.assertTrue(world.card('world117_0')['ranking_state']['uncalibrated_specialist_summary'])
        self.assertEqual(world.card('world117_0')['ranking_state']['uncalibrated_specialist_summary_event_ids'], [eid])
        checkpoint = world.dump()
        self.assertEqual(WorldSession.load(checkpoint).dump(), checkpoint)

    def test_attacker_family_cannot_mask_specialist_rubber_from_guard(self):
        for rubber in ('short_pips', 'raw_pips', 'long_pips', 'anti_spin'):
            with self.subTest(rubber=rubber):
                world = self.specialist_world(rubber=rubber, chopper=False, mask_family=True)
                checkpoint = world.dump()
                with self.assertRaisesRegex(ValueError, 'SPECIALIST_SUMMARY_REQUIRES_EXPLICIT_EXPERIMENTAL_OPT_IN'):
                    world.run_event('sandbox_major_2006_01', list(world.data['players']), 11732)
                self.assertEqual(world.dump(), checkpoint)

    def test_full_formal_and_summary_practice_remain_explicit_and_available(self):
        world = self.specialist_world()
        log = world.play_practice('world117_0', 'world117_3', 'specialist-practice', 11733)
        self.assertEqual(log['mode'], 'summary')
        self.assertEqual(world.artifacts, {})
        result = world.run_event('sandbox_major_2006_01', list(world.data['players']), 11734,
                                  detail_level='full')
        self.assertNotEqual(result.get('calibration_status'), 'UNCALIBRATED')
        self.assertEqual(len(world.artifacts), 3)
        self.assertFalse(world.rankings()['uncalibrated_specialist_summary'])
        self.assertTrue(all(world.data['matches'][line['match_id']]['source_mode'] == 'full'
                            for line in result['bracket']))

    def test_experimental_permission_is_strict_boolean(self):
        world = self.specialist_world()
        checkpoint = world.dump()
        for value in (1, 0, 'true', None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'boolean experimental permission'):
                    world.run_event('sandbox_major_2006_01', list(world.data['players']), 11735,
                                      allow_experimental_specialist_summary=value)
                self.assertEqual(world.dump(), checkpoint)


if __name__ == '__main__':
    unittest.main()
