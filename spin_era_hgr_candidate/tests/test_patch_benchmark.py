"""Regression fixture provenance and observed-statistic aggregation contracts."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('benchmark_specialist_patch', ROOT / 'examples/benchmark_specialist_patch.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class PatchBenchmarkTests(unittest.TestCase):
    def test_predeclared_plan_uses_every_consecutive_seed_once_per_case(self):
        plan = benchmark.seed_plan(32)
        self.assertEqual(tuple(plan), benchmark.CASE_NAMES)
        self.assertEqual(sum(map(len, plan.values())), 128)
        self.assertEqual(len(set(seed for seeds in plan.values() for seed in seeds)), 128)
        for seeds in plan.values():
            self.assertEqual(seeds, list(range(seeds[0], seeds[0] + 32)))
        for invalid in (False, 0, -1, 3.5):
            with self.assertRaises(ValueError):
                benchmark.seed_plan(invalid)

    def test_equipment_and_context_fixtures_do_not_tune_numeric_children(self):
        data = benchmark.fixtures()
        raw = json.loads((ROOT / 'data/original/spin_era_v016_schlager2003_joo2003_cards.json').read_text())
        for label, index, key in (('schlager2003_joo2003', 0, 'schlager'), ('schlager2003_joo2003', 1, 'joo')):
            card = data['cards'][label][index]
            self.assertEqual(benchmark.numeric_traits(card), benchmark.numeric_traits(raw[key]))
            self.assertIn('EXPERIMENTAL', card['simulation_equipment_assumption']['classification'])
        a, b = data['cards']['equal_right_left']
        self.assertEqual(benchmark.numeric_traits(a), benchmark.numeric_traits(b))
        self.assertEqual((a['hand'], b['hand']), ('right', 'left'))
        self.assertEqual(data['xu_selection']['context_year'], 2013)
        if data['xu_selection']['mode'] == 'PRIOR_BASELINE_NOT_GROWN':
            self.assertEqual(data['xu_selection']['source_year'], 2012)
            self.assertEqual(data['cards']['xu2013_context_joo2003'][0]['year'], 2012)

    def test_statistics_identify_side_arrival_counterattack_and_missing_data(self):
        cards = [dict(style='attacker'), dict(style='modern_chopper')]
        shots = [
            dict(player=0, action='serve', reach='service', quality=130),
            dict(player=1, action='bh_specialist_chop', action_family='chop', stroke_side='bh',
                 reach='limited', out_quality=128, return_state='neutral_return',
                 movement=dict(distance_m=1.2, load_after=2.4),
                 geometry=dict(line_category='cross'), technique_path='bh.defense'),
            dict(player=0, action='fh_slow_loop', reach='good', out_quality=110, return_state='neutral_return'),
            dict(player=1, action='fh_counter_loop', action_family='counter', stroke_side='fh',
                 reach='good', out_quality=142, return_state='strong_return')]
        log = dict(winner=1, games_won=[0, 4], rallies=[4], games=[dict(winner=1,
            points=[dict(winner=1, reason='winner', shots=shots)])])
        before = copy.deepcopy(log)
        summary = benchmark.summarize_logs([log], cards)
        self.assertEqual(summary['chop_usage_by_player_and_side'], {'1:bh': 1})
        self.assertEqual(summary['chop_quality_by_player_side_reach']['1:bh:limited']['mean'], 128)
        self.assertEqual(summary['chopper_counterattack_attempts_by_player'], {'1': 1})
        self.assertEqual(summary['attacking_direct_winners_by_player'], {'1': 1})
        self.assertEqual(summary['chopper_counterattack_direct_winners_by_player'], {'1': 1})
        self.assertEqual(summary['movement_distance_m']['mean'], 1.2)
        self.assertIsNone(summary['coverage']['explicit_spin_misread_events'])
        self.assertEqual(log, before)
        aggregate = benchmark.merge_summaries([summary, summary])
        self.assertEqual(aggregate['matches'], 2)
        self.assertEqual(aggregate['chop_usage_by_player_and_side'], {'1:bh': 2})
        self.assertEqual(aggregate['movement_distance_m']['n'], 2)
        self.assertEqual(aggregate['chopper_counterattack_attempts_by_player'], {'1': 2})


if __name__ == '__main__':
    unittest.main()
