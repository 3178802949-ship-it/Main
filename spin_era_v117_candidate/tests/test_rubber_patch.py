"""Equipment gates and ball properties, independently of match quality rolls."""
import copy
import unittest

from common import SCHEMA
import specialist_rubber_v116 as rubber


def ball(spin='top', length='long', strength=130, quality=120):
    return dict(spin=spin, length=length, spin_strength=strength, quality=quality)


class RubberPatchTests(unittest.TestCase):
    def test_faces_are_independent_and_grip_hand_do_not_replace_equipment(self):
        card = dict(hand='left', grip='penhold', rubbers=dict(fh='反胶', bh='长胶'))
        before = copy.deepcopy(card)
        self.assertEqual(rubber.rubber_for(card, 'fh'), 'inverted')
        self.assertEqual(rubber.rubber_for(card, 'bh'), 'long_pips')
        self.assertEqual(card, before)
        self.assertEqual(rubber.rubber_for(dict(hand='right', grip='shakehand'), 'fh'), 'unknown')

    def test_aliases_descriptors_and_conflicts_are_explicit(self):
        card = dict(rubbers=dict(fh='short-pips'), equipment=dict(rubber=dict(fh=dict(type='正胶'), bh='生胶')))
        self.assertEqual(rubber.rubber_for(card, 'fh'), 'short_pips')
        self.assertEqual(rubber.rubber_for(card, 'bh'), 'raw_pips')
        card['equipment']['rubber']['fh'] = 'long_pips'
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            rubber.rubber_for(card, 'fh')
        with self.assertRaises(ValueError):
            rubber.rubber_for(dict(rubber='long_pips'), 'bh')
        with self.assertRaises(ValueError):
            rubber.rubber_for(dict(rubbers=dict(fh='inverted', bh='imaginary')), 'fh')

    def test_anti_spin_requires_opt_in_and_is_marked_experimental(self):
        card = dict(rubbers=dict(bh='anti_spin'))
        with self.assertRaisesRegex(ValueError, 'experimental'):
            rubber.rubber_for(card, 'bh')
        card['experimental_anti_spin'] = True
        self.assertEqual(rubber.rubber_for(card, 'bh'), 'anti_spin')
        contact = rubber.resolve_contact('anti_spin', 'bh_anti_block', ball(),
                                         base_spin='top', base_pace=120, base_strength=130)
        self.assertTrue(contact['experimental'])
        self.assertEqual(contact['spin'], 'back')

    def test_all_new_actions_have_stable_existing_skill_paths(self):
        for name, spec in rubber.ACTION_SPECS.items():
            with self.subTest(action=name):
                self.assertEqual(set(spec), {'family', 'alias', 'technique_path', 'wing', 'label'})
                group, child = spec['technique_path'].split('.')
                self.assertIn(group, SCHEMA['subskill_weights_pct'])
                self.assertIn(child, SCHEMA['subskill_weights_pct'][group])
                self.assertEqual(spec['wing'], name[:2])
        for name in ('fh_chop', 'bh_chop', 'fh_specialist_chop', 'bh_specialist_chop'):
            spec = rubber.action_spec(name)
            self.assertEqual(spec['family'], 'chop')
            self.assertEqual(spec['alias'], 'chop')
            self.assertEqual(spec['technique_path'], name[:2] + '.defense')

    def test_registered_spec_return_does_not_mutate_registry(self):
        spec = rubber.action_spec('bh_lp_chop')
        spec['technique_path'] = 'fh.power'
        self.assertEqual(rubber.action_spec('bh_lp_chop')['technique_path'], 'bh.defense')

    def test_legacy_alias_resolves_contact_wing_without_changing_skill_path(self):
        spec = rubber.action_spec('middle_jam_counter')
        self.assertEqual(spec['wing'], 'bh')
        self.assertEqual(spec['alias'], 'bh_counter')
        self.assertEqual(spec['technique_path'], 'read.choice')

    def test_short_pips_and_raw_pips_share_conditional_contacts(self):
        for kind in ('short_pips', 'raw_pips'):
            top = rubber.specialist_actions(kind, ball(), 'fh')
            under = rubber.specialist_actions(kind, ball('back'), 'fh')
            self.assertIn('fh_sp_punch', top)
            self.assertIn('fh_sp_block', top)
            self.assertNotIn('fh_sp_under_attack', top)
            self.assertIn('fh_sp_under_attack', under)
            self.assertNotIn('fh_sp_punch', under)
            self.assertNotIn('fh_sp_punch', rubber.specialist_actions(kind, ball(length='short'), 'fh'))

    def test_long_pips_contacts_react_to_spin_and_length(self):
        top = rubber.specialist_actions('long_pips', ball(), 'bh')
        under = rubber.specialist_actions('long_pips', ball('back'), 'bh')
        self.assertIn('bh_lp_chop', top)
        self.assertIn('bh_lp_block', top)
        self.assertNotIn('bh_lp_arch', top)
        self.assertIn('bh_lp_arch', under)
        self.assertNotIn('bh_lp_chop', under)
        self.assertIn('bh_lp_wipe', rubber.specialist_actions('long_pips', ball('back', 'short'), 'bh'))

    def test_long_pips_weak_ball_counterattack_is_conditional_and_low_friction(self):
        for wing in ('fh', 'bh'):
            action = wing + '_lp_flat_attack'
            self.assertTrue(rubber.legal_action(action, 'long_pips', ball('top', quality=112)))
            self.assertTrue(rubber.legal_action(action, 'long_pips', ball('side_top', 'half', quality=110)))
            self.assertTrue(rubber.legal_action(action, 'long_pips', ball('dead', quality=124)))
            for incoming, position in ((ball('top', quality=113), 'good'),
                                       (ball('dead', quality=125), 'good'),
                                       (ball('top', quality=100), 'limited'),
                                       (ball('dead', 'short', quality=100), 'good'),
                                       (ball('back', quality=100), 'good')):
                self.assertFalse(rubber.legal_action(action, 'long_pips', incoming, position))
            self.assertFalse(rubber.legal_action(action, 'inverted', ball('top', quality=100)))
            contact = rubber.resolve_contact('long_pips', action, ball('top', quality=100),
                                             base_spin='top', base_pace=130, base_strength=140)
            self.assertEqual(contact['mechanism'], 'LONG_PIPS_LOW_FRICTION_ATTACK')
            self.assertEqual(contact['spin_strength'], 22.4)
            self.assertNotIn('quality', contact)

    def test_rubber_mismatches_and_impossible_loop_conditions_are_rejected(self):
        self.assertFalse(rubber.legal_action('bh_lp_block', 'inverted', ball()))
        self.assertFalse(rubber.legal_action('fh_sp_punch', 'long_pips', ball()))
        self.assertFalse(rubber.legal_action('bh_banana_twist', 'long_pips', ball('back', 'short')))
        self.assertFalse(rubber.legal_action('fh_counter_loop', 'inverted', ball(length='short')))
        self.assertTrue(rubber.legal_action('fh_counter_loop', 'inverted', ball()))
        self.assertFalse(rubber.legal_action('fh_specialist_chop', 'inverted', ball(length='short')))
        self.assertFalse(rubber.legal_action('unknown_action', 'inverted', ball()))
        self.assertFalse(rubber.legal_action('fh_chop', 'inverted', ball(), 'miss'))

    def test_unknown_equipment_does_not_unlock_special_contacts_or_guess_type(self):
        self.assertEqual(rubber.specialist_actions('unknown', ball(), 'fh'), [])
        self.assertFalse(rubber.legal_action('fh_lp_chop', 'unknown', ball()))
        self.assertTrue(rubber.legal_action('fh_chop', 'unknown', ball()))
        output = rubber.resolve_contact('unknown', 'fh_chop', ball(),
                                        base_spin='side_back', base_pace=111.125, base_strength=137.25)
        self.assertEqual((output['spin'], output['pace'], output['spin_strength']), ('side_back', 111.125, 137.25))
        self.assertEqual(output['arc'], 'legacy')

    def test_passive_long_pips_reverses_signed_spin_without_fixed_quality(self):
        args = dict(base_spin='top', base_pace=120, base_strength=130)
        top = rubber.resolve_contact('long_pips', 'bh_lp_block', ball('top'), **args)
        back = rubber.resolve_contact('long_pips', 'bh_lp_arch', ball('back'), **args)
        dead = rubber.resolve_contact('long_pips', 'bh_lp_arch', ball('dead', strength=0), **args)
        self.assertEqual(top['spin'], 'back')
        self.assertEqual(back['spin'], 'top')
        self.assertEqual(dead['spin'], 'dead')
        self.assertEqual(dead['spin_strength'], 0)
        self.assertNotIn('quality', top)
        self.assertNotIn('G', top)
        self.assertNotIn('success_probability', top)

    def test_reversal_depends_on_strength_and_active_contact(self):
        args = dict(base_spin='back', base_pace=112, base_strength=130)
        weak = rubber.resolve_contact('long_pips', 'bh_lp_chop', ball(strength=40), **args)
        strong = rubber.resolve_contact('long_pips', 'bh_lp_chop', ball(strength=150), **args)
        block = rubber.resolve_contact('long_pips', 'bh_lp_block', ball(strength=150), **args)
        self.assertGreater(strong['spin_strength'], weak['spin_strength'])
        self.assertNotEqual(strong['spin_strength'], block['spin_strength'])
        self.assertNotEqual(strong['arc'], block['arc'])

    def test_same_named_block_changes_ball_properties_not_quality(self):
        args = dict(base_spin='top', base_pace=118, base_strength=130)
        inverted = rubber.resolve_contact('inverted', 'block', ball(), **args)
        short = rubber.resolve_contact('short_pips', 'block', ball(), **args)
        long = rubber.resolve_contact('long_pips', 'block', ball(), **args)
        self.assertEqual(inverted['spin'], 'top')
        self.assertLess(short['spin_strength'], inverted['spin_strength'])
        self.assertEqual(long['spin'], 'back')
        self.assertTrue(all('quality' not in out for out in (inverted, short, long)))

    def test_inverted_uses_existing_active_spin_and_high_loop_arc(self):
        output = rubber.resolve_contact('inverted', 'fh_slow_loop', ball('back'),
                                        base_spin='top', base_pace=125, base_strength=138)
        self.assertEqual(output['spin_strength'], 138)
        self.assertEqual(output['pace'], 125)
        self.assertEqual(output['arc'], 'high')

    def test_contact_preserves_input_and_validates_finite_properties(self):
        incoming = ball()
        before = copy.deepcopy(incoming)
        rubber.resolve_contact('long_pips', 'bh_lp_chop', incoming,
                               base_spin='back', base_pace=115, base_strength=140)
        self.assertEqual(incoming, before)
        with self.assertRaises(ValueError):
            rubber.resolve_contact('inverted', 'fh_chop', incoming,
                                   base_spin='back', base_pace=float('nan'), base_strength=140)

    def test_contact_resolution_rejects_incompatible_rubber_or_incoming_conditions(self):
        for kind, action, incoming in (
            ('inverted', 'fh_lp_chop', ball()),
            ('long_pips', 'bh_lp_chop', ball('back')),
            ('short_pips', 'fh_sp_punch', ball(length='short')),
        ):
            with self.subTest(rubber=kind, action=action):
                with self.assertRaisesRegex(ValueError, 'illegal contact'):
                    rubber.resolve_contact(kind, action, incoming,
                                           base_spin='back', base_pace=115, base_strength=140)


if __name__ == '__main__':
    unittest.main()
