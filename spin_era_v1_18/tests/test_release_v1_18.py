"""Cross-system behavioral regressions for the V1.18 upgrade."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from common import ROOT,canonical_json
from simulator import WorldSession,Card,Game,Training
from Game import v118 as OldGame
from Game.formats_v1_18 import server_at,validate_result
from Game.competition_v1_18 import group_table,historical_replacement
from Game.psychology_v1_18 import adjust_probability
from migration_v1_18 import migrate_checkpoint
import game_v112 as core
import player_registry_v1_18 as registry


def cards(n=2,elite=False):
    result=[]
    for i in range(n):
        c=Card.make_ma18();c.update(player_id='v118_test_'+str(i),source_prototype='SYNTHETIC',origin='SYNTHETIC')
        for key in ('personality_profile','career117_profile','career118_profile'):c.pop(key,None)
        if elite:c['children']={g:dict.fromkeys(sub,136) for g,sub in c['children'].items()};c['P6']=dict.fromkeys(c['P6'],136);c['PA']=200
        result.append(Card.normalize(c))
    return result

def world(n=2,elite=False):return WorldSession.create(cards(n,elite),2006,start_date='2006-02-01',seed=118001)
def external(w,mid='external',seed=1182,**kwargs):
    ids=list(w.data['players'])[:2]
    return Game.play_match([w._match_card(p) for p in ids],seed,mid,world_id=w.data['world_id'],
        fatigue=[w.data['players'][p]['fatigue'] for p in ids],**kwargs)
def rest(w,eid='rest'):
    pid=w.data['main_player_id'];s=w.data['players'][pid]
    return w.train_phase(pid,dict(month=s['month'],phase=s['training_release']['phase'],mode='rest'),eid)

def seal(value):
    value=copy.deepcopy(value);value.pop('log_sha256',None);value['log_sha256']=hashlib.sha256(canonical_json(value).encode()).hexdigest();return value

class V118ReleaseTests(unittest.TestCase):
    def test_all_three_formats_both_modes_and_service_order(self):
        inputs=cards()
        for mode in ('summary','full'):
            for fmt in (3,5,7):
                for first in (0,1):
                    r=Game.play_match(inputs,11830+fmt,'formats',best_of=fmt,first_server=first,detail_level=mode)
                    self.assertTrue(Game.verify_log(r));self.assertEqual(max(r['games_won']),fmt//2+1)
                    self.assertTrue(Game.verify_log(Game.compact_log(r)))
        self.assertEqual([server_at(k,0) for k in range(8)],[0,0,1,1,0,0,1,1])
        self.assertEqual([server_at(k,0) for k in range(20,24)],[0,1,0,1])

    def test_disabled_patch_exact_old_scores_contacts_workload(self):
        for mode in ('summary','full'):
            for seed in (11841,11842,11843):
                old=OldGame.play_match(cards(),seed,'parity',detail_level=mode)
                new=Game.play_match(cards(),seed,'parity',detail_level=mode)
                for key in ('games','games_won','winner','points','exposure_by_player','workload'):
                    self.assertEqual(old[key],new[key],(mode,seed,key))

    def test_invalid_formats_and_no_hidden_full_fallback(self):
        for fmt in (1,4,9,True):
            with self.assertRaises(ValueError):Game.play_match(cards(),1,'bad',best_of=fmt)
        with self.assertRaises(ValueError):Game.play_match(cards(),1,'bad',detail_level='full',anti_shutout=True)

    def test_rehashed_illegal_score_or_extra_game_rejected(self):
        r=Game.play_match(cards(),1138,'badscore',best_of=3)
        a=copy.deepcopy(r);a['games'][0]['score']=[14,10]
        with self.assertRaises(ValueError):Game.verify_log(seal(a))
        a=copy.deepcopy(r);a['games'].append(a['games'][-1])
        with self.assertRaises(ValueError):Game.verify_log(seal(a))

    def test_experiment_symmetric_continuous_deuce_bounded_and_audited(self):
        c=cards();states=[core.warmup(x,core.rng_of('psych'),25) for x in c]
        for score in ([7,3],[8,4],[10,10],[12,12]):
            p,a=adjust_probability(.7,score,c,states,0,seed=2,game_index=0,point_index=sum(score))
            self.assertEqual(p,.7)
        adjusted=0
        for seed in range(100):
            p,a=adjust_probability(.98,[10,0],c,states,0,seed=seed,game_index=0,point_index=10)
            q,b=adjust_probability(.02,[0,10],c,states,1,seed=seed,game_index=0,point_index=10)
            self.assertLessEqual(abs(p-.98),.085+1e-12);self.assertTrue(0<p<1);adjusted+=p!=.98
        self.assertGreater(adjusted,0)
        r=Game.play_match(c,1518,'audit',best_of=3,anti_shutout=True)
        self.assertEqual(len(r['psychology_audit']),r['points'])
        self.assertTrue(Game.replay(Game.compact_log(r))['valid'])

    def test_match_settlement_idempotent_with_formal_xp_h2h_and_ranking(self):
        w=world();r=external(w,best_of=3);x=w.settle_match(r,date=w.data['current_date'],kind='youth_singles');saved=w.dump()
        y=w.settle_match(r,date=w.data['current_date'],kind='youth_singles')
        self.assertEqual(y['status'],'already_applied');self.assertEqual(saved,w.dump())
        self.assertEqual(len(w.data['ranking']['matches']),1);self.assertEqual(len(w.data['v1_18']['h2h']),1)
        self.assertGreater(sum(sum(a['grants'].values()) for a in x['xp'].values()),0)
        self.assertTrue(w.consistency_check(deep=True)['valid'])

    def test_conflicting_receipt_date_or_kind_does_not_mutate(self):
        w=world();r=external(w,best_of=3);w.settle_match(r,date=w.data['current_date']);saved=w.dump()
        for kwargs in (dict(date='2006-02-02'),dict(date='2006-02-01',kind='adult_singles')):
            with self.assertRaises(ValueError):w.settle_match(r,**kwargs)
            self.assertEqual(saved,w.dump())
        other=external(world(),seed=345,best_of=3)
        with self.assertRaises(ValueError):w.settle_match(other,date='2006-02-01')

    def test_atomic_failure_after_rewards_rolls_back_everything(self):
        w=world();r=external(w,best_of=3);saved=w.dump()
        with self.assertRaises(RuntimeError):w.settle_match(r,date='2006-02-01',fail_after='rewards')
        self.assertEqual(saved,w.dump());self.assertFalse(w.artifacts)

    def test_stale_timestamps_cards_and_fatigue_rejected(self):
        w=world();r=external(w,best_of=3);saved=w.dump()
        with self.assertRaisesRegex(ValueError,'STALE_MATCH_TIMESTAMP'):w.settle_match(r,date='2006-01-31')
        self.assertEqual(saved,w.dump())
        w.data['players'][list(w.data['players'])[0]]['fatigue']+=1
        with self.assertRaisesRegex(ValueError,'STALE_MATCH_FATIGUE'):w.settle_match(r,date='2006-02-01')

    def test_day_budget_multiple_matches_training_and_recovery(self):
        w=world();a,b=list(w.data['players']);w.play_practice(a,b,'m1',1,best_of=3);w.play_practice(a,b,'m2',2,best_of=3)
        self.assertEqual(w.data['activity'][a]['competition_days'],1)
        with self.assertRaises(ValueError):w.recover_day(a,'same-day')
        before=w.card(a)['fatigue'];w.recover_day(a,'next-day',date='2006-02-02');self.assertLess(w.card(a)['fatigue'],before)
        s=w.data['players'][a];receipt=w.train_phase(a,dict(month=0,phase=0,technical=[dict(group='read'),dict(group='bh')],body='stamina'),'train')
        self.assertNotIn('2006-02-01',receipt['world_settlement']['calendar_training_dates'])
        self.assertNotIn('2006-02-02',receipt['world_settlement']['calendar_training_dates'])
        self.assertEqual({(s['month'],s['training_release']['phase']) for s in w.data['players'].values()},{(0,1)})

    def test_roster_clock_auto_closes_and_queued_npc_plan_uses_same_training(self):
        w=world(3);npc=list(w.data['players'])[1]
        w.queue_npc_plan(npc,dict(month=0,phase=0,mode='rest'),'queue');rest(w)
        self.assertEqual({(s['month'],s['training_release']['phase']) for s in w.data['players'].values()},{(0,1)})
        self.assertEqual(w.data['players'][npc]['event_registry']['background:'+npc+':0:0']['kind'],'training_phase')
        with self.assertRaises(ValueError):w.train_phase(npc,dict(month=0,phase=1,mode='rest'),'ahead')

    def test_xp_survives_rest_save_load_and_tampering_detected(self):
        w=world();a,b=list(w.data['players']);w.play_practice(a,b,'bank',118,best_of=3);before=sum(w.data['players'][a]['xp'].values())
        rest(w);self.assertAlmostEqual(before,sum(w.data['players'][a]['xp'].values()))
        saved=w.dump();self.assertEqual(WorldSession.load(saved).dump(),saved)
        wrapper=json.loads(saved);wrapper['payload']['players'][a]['xp']['fh.power']+=1
        encoded=json.dumps(wrapper['payload'],ensure_ascii=False,separators=(',',':'),allow_nan=False)
        wrapper['sha256']=hashlib.sha256(encoded.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError,'CONSERVATION'):WorldSession.load(json.dumps(wrapper,ensure_ascii=False))

    def test_observation_is_bounded_one_source_once_and_no_direct_G(self):
        w=world();a,b=list(w.data['players']);w.play_practice(a,b,'watch-source',12,best_of=3)
        before=w.card(a);e=w.watch_match(a,'watch-source',['read.choice','read.opponent_read'],'watch')
        self.assertLessEqual(sum(e['reward']['grants'].values()),1.2)
        self.assertEqual(w.card(a)['children'],before['children']);self.assertEqual(w.card(a)['CA'],before['CA'])
        saved=w.dump()
        with self.assertRaises(ValueError):w.watch_match(a,'watch-source',['read.choice'],'repeat')
        self.assertEqual(saved,w.dump())

    def test_youth_tournament_full_BO5_and_phase_ledger(self):
        w=world(4,True);eid='sandbox_major_2006_01';w.confirm_sandbox_event(eid)
        result=w.run_event(eid,list(w.data['players']),128,detail_level='full')
        self.assertEqual(result['best_of'],5 if result['kind']=='youth_singles' else 7)
        for m in result['bracket']:self.assertEqual(w.data['matches'][m['match_id']]['best_of'],result['best_of'])
        self.assertTrue(w.consistency_check(deep=True)['valid'])

    def test_group_three_way_tie_and_format_lock(self):
        def log(a,b,scores):
            won=[sum(s[0]>s[1] for s in scores),sum(s[1]>s[0] for s in scores)]
            return dict(participant_ids=[a,b],best_of=3,games_won=won,winner=int(won[1]>won[0]),games=[dict(score=s,winner=int(s[1]>s[0])) for s in scores])
        ms=[log('a','b',[[11,5],[11,7]]),log('b','c',[[11,6],[8,11],[11,9]]),log('c','a',[[11,8],[11,9]])]
        table=group_table(['a','b','c'],ms,best_of=3)
        self.assertTrue(table['complete']);self.assertEqual(sum(r['wins'] for r in table['standings']),3)
        bad=copy.deepcopy(ms);bad[0]['best_of']=5
        with self.assertRaises(ValueError):group_table(['a','b','c'],bad,best_of=3)

    def test_group_world_round_robin_ranking_and_no_fake_champion(self):
        w=world(4);r=w.run_group('group',list(w.data['players']),18,best_of=3,detail_level='full')
        self.assertTrue(r['table']['complete']);self.assertEqual(len(w.data['ranking']['matches']),6);self.assertEqual(w.data['titles'],[])
        self.assertTrue(w.consistency_check(deep=True)['valid'])

    def test_specialist_cannot_bypass_formal_summary_guard(self):
        c=cards();c[1].update(style='modern_chopper',rubbers=dict(fh='inverted',bh='long_pips'))
        w=WorldSession.create(c,2006,start_date='2006-02-01');r=external(w,best_of=3);saved=w.dump()
        with self.assertRaisesRegex(ValueError,'SPECIALIST'):w.settle_match(r,date='2006-02-01',kind='youth_singles')
        self.assertEqual(saved,w.dump());w.settle_match(r,date='2006-02-01',kind='youth_singles',allow_experimental_specialist_summary=True)
        self.assertTrue(w.rankings()['uncalibrated_specialist_summary'])

    def test_registry_locks_snapshots_and_draw_avoids_protected_slots(self):
        r={};c=cards()[0];registry.register(r,c['player_id'],c,as_of='2006-01-01',source_ref='fixture')
        self.assertEqual(registry.select(r,c['player_id'],'2006-02-01')['card'],c)
        bad=copy.deepcopy(c);bad['children']['fh']['power']+=1
        with self.assertRaises(ValueError):registry.register(r,c['player_id'],bad,as_of='2006-01-01',source_ref='changed')
        entries=[dict(player_id='star',qualification_tier='main',confirmed_seed=True),dict(player_id='low',qualification_tier='main')]
        d=historical_replacement(entries,'user',seed=2,qualification_tier='main')
        self.assertEqual(d['removed_player_id'],'low');self.assertEqual(d['status'],'HYPOTHETICAL')

    def test_migration_preserves_original_and_imports_results_xp_vouchers(self):
        r=ROOT/'data/v1_18/handoff2004';blob=(r/'WORLD_2005_OPENING_ORIGINAL.json').read_text();bundle=json.loads((r/'RECONCILIATION_INPUT.json').read_text())
        w,report=migrate_checkpoint(blob,reconciliation=bundle);pid=w.data['main_player_id']
        self.assertEqual(w.data['current_date'],'2005-01-01');self.assertEqual(w.card(pid)['CA'],150);self.assertEqual(w.card(pid)['PA'],191)
        self.assertEqual(w.card(pid)['record_totals']['wins'],14);self.assertEqual(w.card(pid)['record_totals']['losses'],9)
        self.assertEqual(len(w.data['matches']),23);self.assertEqual(report['summary']['XP_awarded'],26.34)
        self.assertEqual(len({(s['month'],s['training_release']['phase']) for s in w.data['players'].values()}),1)
        self.assertEqual(len(report['vouchers']),2)
        saved=w.dump();again,rr=migrate_checkpoint(saved,reconciliation=bundle);self.assertEqual(rr['status'],'already_current');self.assertEqual(saved,again.dump())
        w2,_=migrate_checkpoint(blob,reconciliation=bundle);self.assertEqual(saved,w2.dump())
        self.assertEqual(blob,(r/'WORLD_2005_OPENING_ORIGINAL.json').read_text())

    def test_legacy_narration_and_voucher_redemption_do_not_reroll(self):
        r=ROOT/'data/v1_18/handoff2004';w,_=migrate_checkpoint((r/'WORLD_2005_OPENING_ORIGINAL.json').read_text(),reconciliation=json.loads((r/'RECONCILIATION_INPUT.json').read_text()))
        before=w.dump();mid=next(iter(w.data['matches']));text=w.narrate_match(mid);self.assertEqual(text['narrative_scope'],'AGGREGATE_ONLY');self.assertEqual(before,w.dump())
        pid=w.data['main_player_id'];w.redeem_voucher(pid,'athens2004:1',['read.choice'],'voucher1')
        self.assertTrue(Training.ensure(w.data['players'][pid])['vouchers']['athens2004:1']['used'])
        with self.assertRaises(ValueError):w.redeem_voucher(pid,'athens2004:1',['read.choice'],'voucher-again')
        self.assertEqual(w.card(pid)['CA'],150);self.assertEqual(len(w.data['matches']),23)

    def test_existing_legacy_settled_world_migrates_without_second_xp(self):
        blob=(ROOT/'data/v1_18/fixtures/LEGACY_WITH_SETTLED_MATCH.json').read_text()
        w,r=migrate_checkpoint(blob)
        self.assertEqual(len(w.data['matches']),1)
        self.assertEqual(sum(len(s['integration_v1_18']['sources']) for s in w.data['players'].values()),0)
        self.assertTrue(w.consistency_check(deep=True)['valid'])

    def test_optional_patch_steps_idempotent_and_no_required_patch_disable(self):
        w=world();before=w.dump();r=w.apply_patch('P001_SHARED_CLOCK')
        self.assertEqual(r['status'],'already_applied');self.assertEqual(before,w.dump())
        with self.assertRaises(ValueError):w.apply_patch('P001_SHARED_CLOCK',enabled=False)
        w.apply_patch('P005_OPT_IN_ANTI_SHUTOUT',enabled=True);saved=w.dump()
        self.assertEqual(w.apply_patch('P005_OPT_IN_ANTI_SHUTOUT',enabled=True)['status'],'already_applied');self.assertEqual(saved,w.dump())
        w.apply_patch('P005_OPT_IN_ANTI_SHUTOUT',enabled=False)
        self.assertFalse(w.data['v1_18']['patches']['anti_shutout'])

    def test_locked_opponent_activation_and_legacy_detail_binding(self):
        r=ROOT/'data/v1_18/handoff2004';bundle=json.loads((r/'RECONCILIATION_INPUT.json').read_text())
        w,_=migrate_checkpoint((r/'WORLD_2005_OPENING_ORIGINAL.json').read_text(),reconciliation=bundle)
        pid=bundle['locked_cards'][0]['card']['player_id'];w.activate_player_snapshot(pid,'activate')
        self.assertEqual(w.data['players'][pid]['month'],12)
        with self.assertRaises(ValueError):w.activate_player_snapshot(pid,'reroll')
        mid=next(mid for mid,m in w.data['matches'].items() if m.get('original_log_sha256'))
        w.attach_legacy_artifact(mid,r/'legacy_full_logs'/(w.data['matches'][mid]['original_log_sha256']+'.json'))
        self.assertEqual(w.narrate_match(mid)['narrative_scope'],'EXECUTED_SHOTS_ONLY')
        self.assertTrue(w.consistency_check(deep=True)['valid'])

    def test_physical_fatigue_reduces_execution_without_changing_permanent_card(self):
        c=cards();original=copy.deepcopy(c)
        for mode in ('summary','full'):
            r=Game.play_match(c,18171,'fatigue',fatigue=(10,70),detail_level=mode,best_of=3)
            self.assertEqual(r['physical_fatigue_audit'][0]['multipliers']['speed'],1.)
            self.assertLess(r['physical_fatigue_audit'][1]['multipliers']['speed'],1.)
            self.assertEqual(c,original)
            old=OldGame.play_match(c,18172,'off',fatigue=(10,70),detail_level=mode)
            new=Game.play_match(c,18172,'off',fatigue=(10,70),detail_level=mode,physical_fatigue=False)
            self.assertEqual(old['games'],new['games'])

    def test_atomic_save_keeps_previous_checkpoint_and_recovers_only_when_explicit(self):
        w=world()
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'world.json';first=w.dump();w.save(p)
            with self.assertRaises(ValueError):w.save(p)
            rest(w);second=w.dump();w.save(p,overwrite=True)
            self.assertEqual(WorldSession.load_file(p).dump(),second)
            self.assertEqual(p.with_name(p.name+'.bak').read_text(),first)
            p.write_text('{broken')
            with self.assertRaises(ValueError):WorldSession.load_file(p)
            self.assertEqual(WorldSession.load_file(p,recover_backup=True).dump(),first)

    def test_annual_resources_roll_for_every_actor_only_once(self):
        w=WorldSession.create(cards(),2006,start_date='2006-12-01')
        rest(w,'first');rest(w,'second')
        self.assertEqual(w.data['current_date'],'2007-01-01')
        self.assertEqual({r['year'] for r in w.data['resources'].values()},{2007})
        saved=w.dump();w.synchronize_roster();self.assertEqual(saved,w.dump())

if __name__=='__main__':unittest.main()
