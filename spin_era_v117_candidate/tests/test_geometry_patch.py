"""Physical/metamorphic geometry contracts, independent of match winner samples."""
import copy
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Game.geometry import lane_to_point, map_line, normalize_hand, point_to_lane


def line(**updates):
    data = dict(hitter_hand='right', receiver_hand='right', hitter_end=0,
                hitter_stance=dict(x=.35, y=-1.15), receiver_stance=dict(x=0., y=1.15),
                incoming=dict(x=.72, y=-.90), target=dict(x=-.72, y=.90), technique='fh_loop')
    data.update(updates)
    return data


class GeometryPatchTests(unittest.TestCase):
    def test_four_hand_combinations_map_forehand_diagonal_to_correct_receiver_wing(self):
        expected = {('right', 'right'): 'fh', ('left', 'right'): 'bh',
                    ('right', 'left'): 'bh', ('left', 'left'): 'fh'}
        for (hitter, receiver), wing in expected.items():
            with self.subTest(hitter=hitter, receiver=receiver):
                source = lane_to_point('fh', hitter, 0)
                result = map_line(**line(hitter_hand=hitter, receiver_hand=receiver,
                                         incoming=source, target=dict(x=-source['x'], y=.90)))
                self.assertEqual(result['receiver_table_side'], wing)
                self.assertEqual(result['receiver_contact_side'], wing)
                self.assertTrue(result['crosscourt'])
                self.assertEqual(result['geometric_line'], 'crosscourt')

    def test_straight_targets_opposite_wing_for_same_hands_and_preserves_physical_x(self):
        for hand in ('left', 'right'):
            source = lane_to_point('fh', hand, 0)
            result = map_line(**line(hitter_hand=hand, receiver_hand=hand, incoming=source,
                                     target=dict(x=source['x'], y=.90)))
            self.assertEqual(result['receiver_side'], 'bh')
            self.assertTrue(result['straight'])
            self.assertEqual(result['geometric_line'], 'down_the_line')

    def test_mirror_flips_world_direction_but_preserves_anatomy_and_movement(self):
        data = line(hitter_stance=dict(x=.55, y=-1.2, recovery=.45),
                    receiver_stance=dict(x=.25, y=1.3, recovery=.6, momentum_x=.25, movement_load=7),
                    target=dict(x=-.95, y=.9))
        mirrored = copy.deepcopy(data)
        mirrored['hitter_hand'] = mirrored['receiver_hand'] = 'left'
        for key in ('hitter_stance', 'receiver_stance', 'incoming', 'target'):
            mirrored[key]['x'] *= -1
            if 'momentum_x' in mirrored[key]:
                mirrored[key]['momentum_x'] *= -1
        a, b = map_line(**data), map_line(**mirrored)
        for key in ('receiver_side', 'hitter_side', 'distance_m', 'recovery_pressure',
                    'geometric_line', 'angle_degrees', 'wide_angle', 'step_around', 'reversing'):
            self.assertEqual(a[key], b[key], key)
        self.assertEqual(a['lateral_direction'], 'left')
        self.assertEqual(b['lateral_direction'], 'right')
        self.assertEqual(a['delta_m']['x'], -b['delta_m']['x'])

    def test_end_swap_with_full_rotation_preserves_receiver_side(self):
        original = line()
        rotated = copy.deepcopy(original)
        rotated['hitter_end'] = 1
        for key in ('hitter_stance', 'receiver_stance', 'incoming', 'target'):
            rotated[key]['x'] *= -1
            rotated[key]['y'] *= -1
        a, b = map_line(**original), map_line(**rotated)
        self.assertEqual(a['receiver_side'], b['receiver_side'])
        self.assertAlmostEqual(a['distance_m'], b['distance_m'])
        self.assertEqual(a['geometric_line'], b['geometric_line'])

    def test_middle_and_body_are_distinct_when_receiver_stands_off_centre(self):
        middle = map_line(**line(receiver_stance=dict(x=.75, y=1.2), target=dict(x=0., y=.9)))
        body = map_line(**line(receiver_stance=dict(x=.75, y=1.2), target=dict(x=.75, y=.9)))
        self.assertTrue(middle['middle'])
        self.assertFalse(middle['body'])
        self.assertEqual(middle['line_category'], 'middle')
        self.assertTrue(body['body'])
        self.assertFalse(body['middle'])
        self.assertEqual(body['receiver_contact_side'], 'middle')
        self.assertEqual(body['receiver_table_side'], 'bh')
        self.assertGreater(middle['distance_m'], body['distance_m'])

    def test_wide_angle_short_ball_and_deep_contact_have_separate_movement_costs(self):
        long = map_line(**line(receiver_stance=dict(x=0., y=2.1), target=dict(x=-.95, y=.9),
                              receiver_contact=dict(x=-.95, y=2.0)))
        short = map_line(**line(receiver_stance=dict(x=0., y=2.1), target=dict(x=-.95, y=.28)))
        self.assertTrue(long['wide_angle'])
        self.assertTrue(long['cross_step'])
        self.assertGreater(short['forward_distance_m'], 2.)
        self.assertGreater(short['distance_m'], long['distance_m'])
        self.assertAlmostEqual(long['receiver_contact']['y'], 2.)
        self.assertAlmostEqual(long['target']['y'], .9)

    def test_same_world_target_changes_contact_side_with_body_position(self):
        target = dict(x=-.65, y=.9)
        central = point_to_lane(target, 'right', 1, dict(x=0., y=1.2))
        shifted = point_to_lane(target, 'right', 1, dict(x=-1.0, y=1.2))
        self.assertEqual(central, 'fh')
        self.assertEqual(shifted, 'bh')
        self.assertEqual(point_to_lane(target, 'right', 1), 'fh')

    def test_forehand_from_backhand_contact_requires_step_around(self):
        result = map_line(**line(hitter_stance=dict(x=.5, y=-1.2),
                                 incoming=dict(x=-.6, y=-.9), technique='fh_counter'))
        self.assertEqual(result['hitter_side'], 'bh')
        self.assertTrue(result['step_around'])
        self.assertTrue(result['cross_body'])
        self.assertTrue(result['needs_recovery'])

    def test_bad_recovery_reversal_and_load_increase_pressure_without_changing_distance(self):
        base = line(receiver_stance=dict(x=0., y=1.2))
        loaded = copy.deepcopy(base)
        loaded['receiver_stance'].update(recovery=.2, momentum_x=.5, movement_load=40)
        a, b = map_line(**base), map_line(**loaded)
        self.assertAlmostEqual(a['distance_m'], b['distance_m'])
        self.assertFalse(a['reversing'])
        self.assertTrue(b['reversing'])
        self.assertGreater(b['recovery_pressure'], a['recovery_pressure'])
        self.assertEqual(a['receiver_side'], b['receiver_side'])

    def test_hand_fields_are_explicit_and_conflicts_fail(self):
        for value in (None, '', 'unknown', 'UNSPECIFIED', '未提供', 'ambidextrous'):
            self.assertEqual(normalize_hand(value), 'unknown')
        self.assertEqual(normalize_hand({'hand': 'unknown', 'handedness': 'L'}), 'left')
        self.assertEqual(normalize_hand({'hand': '右手', 'handedness': 'right'}), 'right')
        self.assertEqual(normalize_hand({'grip': 'penhold', 'name': 'a left hand name'}), 'unknown')
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            normalize_hand({'hand': 'left', 'handedness': 'right'})
        for value in (True, 1, [], object()):
            with self.assertRaises(ValueError):
                normalize_hand(value)

    def test_unknown_hand_preserves_physical_movement_and_marks_anatomy_unresolved(self):
        result = map_line(**line(hitter_hand=None, receiver_hand='unknown'))
        self.assertFalse(result['mapping_resolved'])
        self.assertEqual(result['receiver_side'], 'unknown')
        self.assertGreater(result['distance_m'], 0)
        self.assertEqual(point_to_lane(dict(x=0., y=.9), None, 1), 'unknown')
        self.assertIsNone(lane_to_point('fh', None, 1))
        self.assertEqual(lane_to_point('middle', None, 1), dict(x=0., y=.9))

    def test_lane_point_roundtrips_cover_both_ends_and_hands(self):
        for end in (0, 1):
            for hand in ('left', 'right'):
                for lane in ('fh', 'bh', 'middle'):
                    for length in ('short', 'half', 'long'):
                        p = lane_to_point(lane, hand, end, length)
                        self.assertEqual(point_to_lane(p, hand, end), lane)
                        self.assertEqual(p['y'] > 0, end == 1)

    def test_no_mutation_or_skill_fields_and_invalid_numeric_inputs_rejected(self):
        data = line()
        original = copy.deepcopy(data)
        result = map_line(**data)
        self.assertEqual(data, original)
        self.assertTrue({'G9', 'CA', 'PA', 'P6', 'quality_multiplier'}.isdisjoint(result))
        for bad in (True, math.nan, math.inf, '1'):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                map_line(**line(target=dict(x=bad, y=.9)))
        for bad in (True, 0., 2):
            with self.subTest(end=bad), self.assertRaises(ValueError):
                map_line(**line(hitter_end=bad))
        for bad in (True, -.1, 1.1, math.inf):
            with self.subTest(recovery=bad), self.assertRaises(ValueError):
                map_line(**line(receiver_stance=dict(x=0., y=1.2, recovery=bad)))
        with self.assertRaises(ValueError):
            map_line(**line(target=dict(x=0., y=-.9)))


if __name__ == '__main__':
    unittest.main()
