"""Observer preferences, numeric preservation and evidence-bounded personality."""
import copy
from datetime import date
import json
import unittest

import Card
from Card import v118
from common import ROOT


class Card118Tests(unittest.TestCase):
    def card(self, pid='ma_long', year=2004):
        return Card.get_preset(pid, year)

    def test_all_370_snapshots_and_104_players_are_covered_without_numeric_changes(self):
        source = ROOT / 'data/presets_normalized.json'
        original = source.read_bytes()
        cards = json.loads(original)['profiles']
        library = json.loads((ROOT / 'data/player_profiles_v118.json').read_text())
        self.assertEqual(set(library['players']), {x['player_id'] for x in cards})
        self.assertEqual(len(library['players']), 104)
        self.assertEqual(len(cards), 370)
        for card in cards:
            with self.subTest(player=card['player_id'], year=card['year']):
                prepared = v118.prepare(card)
                for key in ('children', 'P6', 'G9', 'CA', 'PA', 'pa_range'):
                    self.assertEqual(prepared[key], card[key])
                self.assertEqual(set(prepared['style_profile']['axes']), set(v118.AXES))
                self.assertTrue(all(0 <= value <= 1 for value in prepared['style_profile']['axes'].values()))
                self.assertEqual(prepared['personality_profile']['visibility'], 'NARRATOR_ONLY')
        self.assertEqual(source.read_bytes(), original)

    def test_preferences_use_preference_inputs_not_skill_pa_titles_or_future_identity(self):
        a = self.card()
        b = copy.deepcopy(a)
        b.update(PA=150, pa_range=[147, 153], champion_history_as_of_snapshot=['invented future title'],
                 technical_identity='2030未来神技', status_tags=['future_champion_prototype'])
        b['children'] = {g: dict.fromkeys(sub, 100) for g, sub in b['children'].items()}
        b['P6'] = dict.fromkeys(b['P6'], 100)
        b = Card.normalize(b)
        self.assertEqual(v118.prepare(a)['style_profile'], v118.prepare(b)['style_profile'])
        self.assertIn('MODELLED', v118.prepare(a)['style_profile']['confidence'])

    def test_chopper_and_attacker_have_observable_preference_descriptions(self):
        a = v118.prepare(self.card('joo_saehyuk', 2000))['style_profile']
        b = v118.prepare(self.card('fan_zhendong', 2012))['style_profile']
        self.assertEqual(a['class_label'], '削球与反攻组织')
        self.assertGreater(a['axes']['backspin_control'], b['axes']['backspin_control'])
        self.assertGreater(b['axes']['backhand_use'], a['axes']['backhand_use'])
        self.assertTrue(a['preferred_methods'])
        self.assertTrue(b['preferred_methods'])

    def test_public_view_removes_backend_persona_and_latents_but_keeps_complete_current_card(self):
        value = self.card()
        value['career118_profile'] = dict(latent_target=200, private_notes='backend')
        value['extra'] = dict(private_notes='secret', normal_value=7, nested=dict(hidden_trait=9))
        value['xp'] = {'fh.power': 12}
        value['permits'] = {'fh.power': 2}
        public = v118.public_view(value)
        encoded = json.dumps(public, ensure_ascii=False)
        for forbidden in ('personality_profile', 'simulation_traits', 'latent_target', 'private_notes',
                          'hidden_trait', 'body_max', 'champion_prototype', '历史级'):
            self.assertNotIn(forbidden, encoded)
        for key in ('children', 'P6', 'G9', 'CA', 'PA', 'pa_range', 'learning_factor',
                    'birth_year', 'nation', 'snapshot_date', 'ranking_state', 'xp', 'permits', 'style_profile'):
            self.assertIn(key, public)
        self.assertEqual(public['extra']['normal_value'], 7)
        self.assertEqual(public['children'], value['children'])

    def test_future_and_unknown_interviews_are_not_available_to_earlier_narration(self):
        card = v118.prepare(self.card())
        base = dict(source_id='UNIT_FIXTURE_NOT_ACTUAL_RESEARCH', source_url='https://example.test/fixture',
                    basis='PUBLIC_SELF_DESCRIPTION', keywords=['测试词'], interpretation_limit='unit fixture only',
                    verification_status='VERIFIED_PUBLIC_PRIMARY_SOURCE')
        card['personality_profile']['public_cues'] = [dict(base, source_date='2010-06-15', source_year=2010),
            dict(base, source_id='year-only-fixture', source_year=2011),
            dict(base, source_id='unknown-date-fixture'),
            dict(base, source_id='conflicting-date-fixture', source_date='2004-01-01', source_year=2020),
            dict(base, source_id='unverified-fixture', source_year=2004, verification_status='UNVERIFIED_BIBLIOGRAPHIC_LEAD')]
        self.assertEqual(v118.narrative_view(card, 2004)['personality_guidance']['public_cues'], [])
        self.assertEqual(v118.narrative_view(card, 2010, as_of_date='2010-06-14')['personality_guidance']['public_cues'], [])
        exact = v118.narrative_view(card, 2010, as_of_date='2010-06-15')
        self.assertEqual(len(exact['personality_guidance']['public_cues']), 1)
        self.assertEqual(exact['temporal_precision'], 'EXACT_DATE')
        self.assertEqual(len(v118.narrative_view(card, 2011, as_of_date='2011-01-01')['personality_guidance']['public_cues']), 1)
        self.assertEqual(len(v118.narrative_view(card, 2011)['personality_guidance']['public_cues']), 2)

    def test_future_snapshot_cannot_narrate_past_and_conflicting_dates_fail(self):
        with self.assertRaisesRegex(ValueError, 'future card'):
            v118.narrative_view(self.card(), 2003)
        with self.assertRaisesRegex(ValueError, 'consistent'):
            v118.narrative_view(self.card(), 2004, as_of_date='2005-01-01')
        with self.assertRaisesRegex(ValueError, 'snapshot date'):
            v118.narrative_view(self.card(), 2004, as_of_date='2004-01-01')
        card = self.card()
        card['snapshot_date'] = 'invalid-date'
        with self.assertRaisesRegex(ValueError, 'valid card snapshot date'):
            v118.narrative_view(card, 2004)

    def test_defaults_are_explicit_simulation_not_claimed_real_personality(self):
        profile = v118.prepare(self.card())['personality_profile']
        self.assertEqual(profile['basis'], 'SIMULATED_NARRATIVE_DEFAULT')
        self.assertTrue(profile['not_match_modifiers'])
        self.assertTrue(profile['not_a_psychological_diagnosis'])
        self.assertEqual(profile['public_cues'], [])
        self.assertTrue(profile['simulation_traits'])

    def test_original_traits_are_stable_and_user_can_declare_fiction(self):
        card = Card.make_ma18()
        card.update(player_id='original-personality', source_prototype='SYNTHETIC', origin='SYNTHETIC')
        self.assertEqual(v118.prepare(card, 1), v118.prepare(card, 1))
        different = [v118.prepare(card, seed)['personality_profile']['simulation_traits'] for seed in range(8)]
        self.assertGreater(len(set(map(tuple, different))), 1)
        card['narrative_personality'] = ['安静准备', '乐于复盘']
        result = v118.prepare(card)
        self.assertEqual(result['personality_profile']['basis'], 'USER_DECLARED_FICTION')
        self.assertEqual(result['personality_profile']['simulation_traits'], card['narrative_personality'])
        self.assertNotIn('narrative_personality', v118.public_view(result))

    def test_copying_a_prototype_to_a_new_player_rebinds_personality_subject(self):
        template = v118.make_ma18()
        template['personality_profile']['public_cues'] = [dict(source_id='UNIT_FIXTURE_NOT_REAL_INTERVIEW',
            source_url='https://example.test/fixture', source_year=2006, keywords=['模拟测试'],
            basis='PUBLIC_SELF_DESCRIPTION')]
        clone = copy.deepcopy(template)
        clone.update(player_id='original_clone', source_prototype='SYNTHETIC', origin='SYNTHETIC')
        clone = v118.prepare(clone, seed=118)
        self.assertEqual(clone['personality_profile']['subject_player_id'], 'original_clone')
        self.assertEqual(clone['personality_profile']['public_cues'], [])
        self.assertEqual(clone['personality_profile']['provenance']['source_person_id'], 'original_clone')
        self.assertEqual(clone['children'], template['children'])

    def test_preparation_is_copying_idempotent_and_json_portable(self):
        card = self.card()
        before = copy.deepcopy(card)
        prepared = v118.prepare(card)
        self.assertEqual(card, before)
        self.assertEqual(v118.prepare(prepared), prepared)
        self.assertEqual(json.loads(json.dumps(prepared)), prepared)
        self.assertEqual(v118.narrative_view(prepared, as_of_date=date(2004, 12, 31))['as_of_year'], 2004)

    def test_illegal_axes_and_wrong_personality_authority_are_rejected(self):
        for value in (float('nan'), 2, -1, True):
            card = v118.prepare(self.card())
            card['style_profile']['axes']['risk'] = value
            with self.assertRaises(ValueError):
                v118.prepare(card)
        card = v118.prepare(self.card())
        card['personality_profile']['not_match_modifiers'] = False
        with self.assertRaisesRegex(ValueError, 'cannot change match'):
            v118.prepare(card)
        card = v118.prepare(self.card())
        card['personality_profile']['basis'] = 'TRUE_PRIVATE_PERSONALITY'
        with self.assertRaisesRegex(ValueError, 'fictional basis'):
            v118.prepare(card)

    def test_new_card_exports_existing_ranking_and_selection_interfaces(self):
        self.assertIs(v118.RankingBook, Card.RankingBook)
        self.assertEqual(v118.PATHS, Card.PATHS)
        self.assertEqual(v118.recompute(self.card())['CA'], self.card()['CA'])
        self.assertIn('style_profile', v118.get_preset('ma_long', 2004))
        self.assertIn('style_profile', v118.make_ma18())

    def test_mature_elite_design_priors_have_temporal_bounds_and_leave_youth_fallback(self):
        library = json.loads((ROOT / 'data/player_profiles_v118.json').read_text())
        self.assertEqual(sum(bool(x.get('curated_style_priors')) for x in library['players'].values()), 14)
        for pid, young_year, mature_year in (('ma_long', 2004, 2016), ('fan_zhendong', 2012, 2016),
                                           ('zhang_jike', 2008, 2012), ('truls_moregard', 2016, 2024)):
            young = v118.prepare(self.card(pid, young_year))
            mature_source = self.card(pid, mature_year)
            mature = v118.prepare(mature_source)
            self.assertEqual(young['style_profile']['provenance']['classification'], 'MODELLED_FROM_SNAPSHOT_ASSESSMENT')
            provenance = mature['style_profile']['provenance']
            self.assertEqual(provenance['classification'], 'CURATED_GAME_DESIGN_PRIOR')
            self.assertLessEqual(provenance['effective_from'], mature_year)
            self.assertGreaterEqual(provenance['effective_through'], mature_year)
            self.assertEqual(mature['CA'], mature_source['CA'])
            self.assertEqual(mature['children'], mature_source['children'])
        zhang = v118.prepare(self.card('zhang_jike', 2012))['style_profile']['axes']
        harimoto = v118.prepare(self.card('harimoto', 2024))['style_profile']['axes']
        self.assertNotEqual(zhang, harimoto)

    def test_explicit_preferences_take_priority_over_named_elite_design_prior(self):
        card = v118.prepare(self.card('ma_long', 2016))
        card['style_profile']['axes']['risk'] = .123
        card['style_profile']['labels'] = ['用户设定偏好', '控制优先']
        result = v118.prepare(card)
        self.assertEqual(result['style_profile']['axes']['risk'], .123)
        self.assertEqual(result['style_profile']['labels'], card['style_profile']['labels'])


if __name__ == '__main__':
    unittest.main()
