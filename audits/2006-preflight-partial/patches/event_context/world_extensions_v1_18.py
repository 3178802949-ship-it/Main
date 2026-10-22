"""Atomic settlement, shared schedules, background players and bounded rewards."""
from collections import Counter
import copy
from datetime import date,timedelta
import hashlib
from zoneinfo import ZoneInfo
from common import canonical_json,SCHEMA
from Game import v1_18 as Game
from Training import v1_18 as Training
from Card import v118 as Card
from Area import v118 as Area
import career_v116 as legacy_career
import player_registry_v1_18 as registry


def digest(value):return hashlib.sha256(canonical_json(value).encode()).hexdigest()

def initial_extensions():
    return dict(version='V1.18-INTEGRATION-1',timezone='UTC',settlements={},h2h={},daily_schedule={},
        player_registry={},queued_plans={},migration=None,patches=dict(clock=True,settlement=True,
        shared_XP=True,formats=True,anti_shutout=False,physical_fatigue=True),background_policy='club_auto',roster_aligned=True,
        historical_provenance={},reward_events={},snapshot_provenance={},legacy_points={})

class WorldExtensions:
    def _phase_dates(self,pid):
        from world_v1_18 import _period,_phase_end
        s=self.data['players'][pid];a=_period(self.data['base_date'],s['month'],s['training_release']['phase']);b=_phase_end(self.data['base_date'],s)
        return [(a+timedelta(days=i)).isoformat() for i in range((b-a).days+1)]

    def _day_entries(self,pid,day):
        return self.data['v1_18']['daily_schedule'].get(day,{}).get(pid,[])

    def _reserve_day(self,pid,day,kind,source,*,minutes=90):
        if day not in self._phase_dates(pid):raise ValueError('activity outside actor phase')
        entries=self._day_entries(pid,day)
        if kind=='match' and any(x['kind'] in ('train','rest','travel') for x in entries):raise ValueError('MATCH_DAY_CONFLICT')
        if kind in ('train','rest','travel') and any(x['kind'] in ('match','train','rest','travel') for x in entries):raise ValueError('DAY_ALREADY_OCCUPIED')
        if sum(x['minutes'] for x in entries)+minutes>480:raise ValueError('DAILY_ACTIVITY_MINUTES_EXCEEDED')
        if kind=='match' and sum(x['kind']=='match' for x in entries)>=4:raise ValueError('DAILY_MATCH_LIMIT')
        self.data['v1_18']['daily_schedule'].setdefault(day,{}).setdefault(pid,[]).append(dict(kind=kind,source=source,minutes=minutes))

    def _available_training_days(self,pid):
        return [d for d in self._phase_dates(pid) if not any(x['kind'] in ('match','train','rest','travel') for x in self._day_entries(pid,d)) and sum(x['minutes'] for x in self._day_entries(pid,d))<=120]

    def _register_initial_snapshots(self):
        e=self.data['v1_18']
        for pid,meta in self.data['metadata'].items():
            registry.register(e['player_registry'],pid,meta,as_of=meta.get('snapshot_date',self.data['base_date']),
                source_ref='WORLD_INITIAL_CARD',classification=meta.get('classification','ASSESSMENT'))

    def synchronize_roster(self,*,policy=None,source_id='explicit-roster-sync'):
        """Derived branch updates only; never rewrites locked source snapshots."""
        self._writable();proposed=self._fork(tuple(self.data['players']))
        report=proposed._sync_roster(policy=policy,source_id=source_id)
        self._commit(proposed);return report

    def _sync_roster(self,*,policy=None,source_id='phase-background-sync'):
        policy=policy or self.data['v1_18']['background_policy']
        if policy not in ('club_auto','passive_aging'):raise ValueError('explicit background policy required')
        primary=self.data['players'][self.data['main_player_id']];target=(primary['month'],primary['training_release']['phase'])
        groups=list(SCHEMA['core_order']);bodies=list(SCHEMA['body_weights_pct']);updates=[]
        for pid,original in list(self.data['players'].items()):
            if pid==self.data['main_player_id']:continue
            state=copy.deepcopy(original);self.data['players'][pid]=state
            before=Training.performance_card(state);phases=0;start=(state['month'],state['training_release']['phase'])
            while (state['month'],state['training_release']['phase'])<target:
                m,p=state['month'],state['training_release']['phase'];queued=self.data['v1_18']['queued_plans'].pop(f'{pid}:{m}:{p}',None)
                rest=policy=='passive_aging' or state['fatigue']>=45 or state['month']<state.get('rehab_until',0)
                plan=queued or dict(month=m,phase=p,mode='rest' if rest else 'train')
                if not queued and not rest:
                    offset=int(hashlib.sha256(pid.encode()).hexdigest()[:4],16)
                    selected=[groups[(m*2+p+offset+i*4)%len(groups)] for i in range(2)]
                    plan.update(technical=[dict(group=g) for g in selected],body=bodies[m%len(bodies)])
                free=self._available_training_days(pid);days=min(10,len(free)) if plan.get('mode','train')=='train' else 0
                plan.update(training_fraction=days/10,recovery_fraction=len(free)/max(1,len(self._phase_dates(pid))))
                if not days:plan=dict(month=m,phase=p,mode='rest',training_fraction=0.,recovery_fraction=plan['recovery_fraction'])
                eid=f'background:{pid}:{m}:{p}'
                for d in free[:days]:self._reserve_day(pid,d,'train',eid,minutes=360)
                Training.settle_phase(state,plan,legacy_career.environment('club'),eid,record=False)
                if not source_id.startswith('migration') and plan['mode']=='train':self._injury_chance(pid,eid)
                self.data['activity'][pid]=dict(month=state['month'],phase=state['training_release']['phase'],competition_days=0,
                    match_count=0,effort=0.,movement_m=0.,last_match_date=None,last_competition_day=None)
                phases+=1
            if phases:
                after=Training.performance_card(state)
                updates.append(dict(player_id=pid,from_clock=start,to_clock=target,phases=phases,policy=policy,
                    CA_before=before['CA'],CA_after=after['CA'],P6_before=before['P6'],P6_after=after['P6'],
                    classification='SIMULATED_BACKGROUND_DEVELOPMENT_NOT_REPLAYED_HISTORY'))
        rollovers=[]
        for actor in self.data['players']:
            before_budget=dict(self.data['resources'][actor]);after_budget=self._resource_year(actor)
            if before_budget['year']!=after_budget['year']:
                rollovers.append(dict(player_id=actor,before=before_budget,after=dict(after_budget),source='ANNUAL_SIMULATION_RESOURCE_RULE'))
        if rollovers:
            eid='annual-resources:'+str(max(x['after']['year'] for x in rollovers))
            if eid not in self.data['events']:
                event=dict(type='annual_resource_rollover',players=rollovers);self.data['events'][eid]=event;self._record('event',eid,event)
        self.data['v1_18']['roster_aligned']=True
        result=dict(type='roster_clock_sync',source_id=source_id,updates=updates,target_clock=target,resource_rollovers=rollovers,
            numeric_training_core='SAME_TRAINING_XP_CAP_AGE_PIPE_AS_MAIN_PLAYER')
        if updates:
            eid=f'{source_id}:{target[0]}:{target[1]}'
            if eid not in self.data['events']:
                self.data['events'][eid]=result;self._record('event',eid,result)
        return copy.deepcopy(result)

    def queue_npc_plan(self,pid,plan,event_id):
        if pid==self.data['main_player_id'] or pid not in self.data['players']:raise ValueError('a loaded NPC is required')
        self._new_id(event_id);s=self.data['players'][pid]
        if (plan.get('month'),plan.get('phase'))!=(s['month'],s['training_release']['phase']):raise ValueError('PLAN_OUT_OF_SEQUENCE')
        proposed=self._fork();key=f"{pid}:{s['month']}:{s['training_release']['phase']}"
        if key in proposed.data['v1_18']['queued_plans']:raise ValueError('NPC_PLAN_ALREADY_QUEUED')
        from Training import v118 as old
        old._validate(s,plan,event_id)
        proposed.data['v1_18']['queued_plans'][key]=copy.deepcopy(plan)
        event=dict(type='queued_npc_plan',player_id=pid,plan=copy.deepcopy(plan))
        proposed.data['events'][event_id]=event;proposed._record('event',event_id,event);self._commit(proposed);return event

    def _next_match_day(self,players):
        candidates=[d for d in self._phase_dates(players[0]) if d>=self.data['current_date']]
        for d in candidates:
            if all(not any(x['kind'] in ('train','rest','travel') for x in self._day_entries(p,d))
                   and sum(x['kind']=='match' for x in self._day_entries(p,d))<4
                   and sum(x['minutes'] for x in self._day_entries(p,d))<=240 for p in players):return d
        raise ValueError('no available competition day in phase')

    def _settle_inplace(self,log,*,when,kind='practice',event_id=None,charge_day=True,fail_after=None,allow_experimental_specialist_summary=False):
        Game.verify_log(log)
        from Game.integration_v1_18 import _validate_exposures
        _validate_exposures(log.get('exposure_by_player'))
        mid=log['match_id'];e=self.data['v1_18']
        transaction_hash=digest(dict(log_hash=log['log_sha256'],date=when,kind=kind,event_id=event_id,charge_day=charge_day,allow_experimental_specialist_summary=allow_experimental_specialist_summary))
        prior=e['settlements'].get(mid)
        if prior:
            if prior['transaction_hash']!=transaction_hash:raise ValueError('MATCH_SETTLEMENT_CONFLICT')
            return dict(copy.deepcopy(prior),status='already_applied')
        if log['world_id']!=self.data['world_id']:raise ValueError('MATCH_WORLDLINE_MISMATCH')
        if when<self.data['current_date']:raise ValueError('STALE_MATCH_TIMESTAMP')
        date.fromisoformat(when);ZoneInfo(e['timezone'])
        ids=log['participant_ids']
        if len(set(ids))!=2:raise ValueError('two distinct actors required')
        for p in ids:self._check_actor(p,in_event=event_id is not None)
        current=[self._match_card(p) for p in ids]
        if kind in ('youth_singles','adult_singles') and log['mode']=='summary':
            from Game.tactics_v117 import specialist_kind
            from specialist_rubber_v116 import rubber_for
            special=any(specialist_kind(c) in ('chopper','short_pips','long_pips') or any(rubber_for(c,k) in ('short_pips','long_pips','raw_pips','anti_spin') for k in ('fh','bh')) for c in current)
            if special and not allow_experimental_specialist_summary:raise ValueError('SPECIALIST_SUMMARY_REQUIRES_EXPLICIT_EXPERIMENTAL_OPT_IN')
        if digest([Game.match_card(c) for c in current])!=log['input_cards_sha256']:raise ValueError('STALE_MATCH_CARD_INPUT')
        context=log.get('request_context',{})
        if context.get('physical_fatigue',True)!=e['patches'].get('physical_fatigue',True):raise ValueError('MATCH_PHYSICAL_RULES_MISMATCH')
        if context.get('fatigue')!=[self.data['players'][p]['fatigue'] for p in ids]:raise ValueError('STALE_MATCH_FATIGUE_INPUT')
        before={p:self.card(p) for p in ids};costs={};health={};xp={}
        for i,p in enumerate(ids):
            minutes=min(180,max(45,30+int(log['points']*.40)))
            self._reserve_day(p,when,'match',mid,minutes=minutes)
            a=self.data['activity'][p];state=self.data['players'][p]
            effort,move=self._effort(log,i)
            density=sum(x['kind']=='match' for x in self._day_entries(p,when))-1
            cost=min(22.,2+.10*effort+move/180+.7*density)
            state['fatigue']=min(100.,state['fatigue']+cost);costs[p]=cost
            a.update(competition_days=sum(any(x['kind'] in ('match','travel') for x in self._day_entries(p,d)) for d in self._phase_dates(p)),
                match_count=a['match_count']+1,effort=a['effort']+effort,movement_m=a['movement_m']+move,last_match_date=when)
            if charge_day:a['last_competition_day']=when
            xp[p]=Training.match_reward(state,log,p,before[ids[1-i]]['CA'])
            health[p]=dict(deferred_to=event_id) if event_id is not None else self._injury_chance(p,mid,effort)
        if fail_after=='rewards':raise RuntimeError('INJECTED_TRANSACTION_FAILURE')
        compact=Game.compact_log(log);self.data['matches'][mid]=compact
        formal=kind in ('youth_singles','adult_singles')
        if formal:
            book=Card.RankingBook.from_snapshot(self.data['ranking']);book.settle_match(mid,*ids,ids[log['winner']],when,kind=kind)
            self.data['ranking']=book.snapshot()
        for i,p in enumerate(ids):
            q=ids[1-i];key=digest(sorted((p,q)));row=e['h2h'].setdefault(key,dict(player_ids=sorted((p,q)),wins={},matches=[]))
            if mid not in row['matches']:
                row['matches'].append(mid);winner=ids[log['winner']];row['wins'][winner]=row['wins'].get(winner,0)+1
        self.data['match_meta'][mid]=dict(event_id=event_id,date=when,timezone=e['timezone'],
            participant_clocks={p:dict(month=self.data['players'][p]['month'],phase=self.data['players'][p]['training_release']['phase']) for p in ids},
            fatigue_cost=costs,health=health,ranking_settled=formal,detail_level=log['mode'],source_log_sha256=log['log_sha256'])
        if kind in ('youth_singles','adult_singles') and log['mode']=='summary' and allow_experimental_specialist_summary:
            self.data['match_meta'][mid].update(calibration_status='UNCALIBRATED',experimental_scope='SPECIALIST_SUMMARY')
        after={p:self.card(p) for p in ids}
        result=dict(type='MatchSettlement',status='applied',match_id=mid,receipt_hash=log['log_sha256'],
            worldline_id=self.data['world_id'],date=when,timezone=e['timezone'],transaction_hash=transaction_hash,
            xp=xp,fatigue_delta=costs,injuries=health,h2h_updated=True,rank_settled=formal,
            CA_before={p:before[p]['CA'] for p in ids},CA_after={p:after[p]['CA'] for p in ids},
            original_receipt=dict(log_sha256=log['log_sha256'],input_cards_sha256=log['input_cards_sha256']),
            source='SIMULATED',approximate=log.get('mode')=='summary')
        result['settlement_sha256']=digest(result);e['settlements'][mid]=copy.deepcopy(result)
        self._record('match',mid,compact);eid='settlement:'+mid;self.data['events'][eid]=result;self._record('event',eid,result)
        self.data['current_date']=max(self.data['current_date'],when)
        return result

    def settle_match(self,log,*,date,kind='practice',event_id=None,fail_after=None,allow_experimental_specialist_summary=False):
        self._writable()
        # Event privileges belong to the internal tournament/group transaction.
        # External receipts cannot name an event to bypass entry fatigue or defer health.
        if event_id is not None:raise ValueError('EXTERNAL_EVENT_CONTEXT_FORBIDDEN')
        if kind not in ('practice','youth_singles','adult_singles'):raise ValueError('explicit match category required')
        prior=self.data['v1_18']['settlements'].get(log.get('match_id'))
        if prior:
            # Validate even a duplicate: content or context changes are conflicts.
            return self._settle_inplace(log,when=date,kind=kind,event_id=event_id,fail_after=fail_after,allow_experimental_specialist_summary=allow_experimental_specialist_summary)
        proposed=self._fork(log['participant_ids'])
        result=proposed._settle_inplace(log,when=date,kind=kind,event_id=event_id,fail_after=fail_after,allow_experimental_specialist_summary=allow_experimental_specialist_summary)
        self._commit(proposed);return copy.deepcopy(result)

    def _play(self,a,b,match_id,seed,*,detail_level='summary',event_id=None,when=None,kind='adult_singles',charge_day=True,best_of=7,anti_shutout=None,first_server=0,allow_experimental_specialist_summary=False):
        self._new_id(match_id)
        for p in (a,b):self._check_actor(p,in_event=event_id is not None)
        when=when or self._next_match_day((a,b))
        patch=self.data['v1_18']['patches']['anti_shutout'] if anti_shutout is None else anti_shutout
        raw=Game.play_match([self._match_card(a),self._match_card(b)],seed,match_id,world_id=self.data['world_id'],
            fatigue=tuple(self.data['players'][p]['fatigue'] for p in (a,b)),best_of=best_of,detail_level=detail_level,
            anti_shutout=patch,first_server=first_server,physical_fatigue=self.data['v1_18']['patches'].get('physical_fatigue',True))
        self._settle_inplace(raw,when=when,kind=kind,event_id=event_id,charge_day=charge_day,allow_experimental_specialist_summary=allow_experimental_specialist_summary)
        if detail_level=='full':self.artifacts[raw['log_sha256']]=raw
        elif patch:self.artifacts['psychology:'+raw['log_sha256']]=raw
        return raw

    def play_practice(self,a,b,match_id,seed,*,detail_level='summary',best_of=5,anti_shutout=None,first_server=0,date=None):
        self._writable();proposed=self._fork((a,b))
        result=proposed._play(a,b,match_id,seed,detail_level=detail_level,kind='practice',best_of=best_of,
            anti_shutout=anti_shutout,first_server=first_server,when=date)
        self._commit(proposed);return copy.deepcopy(result)

    def match_settlement(self,mid):return copy.deepcopy(self.data['v1_18']['settlements'][mid])

    def set_experiment(self,enabled,event_id):
        if type(enabled)is not bool:raise ValueError('boolean experiment switch required')
        self._new_id(event_id);p=self._fork();p.data['v1_18']['patches']['anti_shutout']=enabled
        e=dict(type='experiment_switch',experiment='anti_shutout',enabled=enabled,numerical_version='V1.18-ANTI-SHUTOUT-2')
        p.data['events'][event_id]=e;p._record('event',event_id,e);p.data['current_date']=max(p.data['current_date'],e.get('date',p.data['current_date']));self._commit(p);return e

    def watch_match(self,pid,source_match_id,paths,event_id,*,date=None,quality=.6):
        self._writable();self._new_id(event_id)
        if pid not in self.data['players'] or source_match_id not in self.data['matches']:raise ValueError('loaded observer and known match required')
        self._check_actor(pid)
        source=self.data['matches'][source_match_id];meta=self.data['match_meta'][source_match_id]
        if meta.get('date') and meta['date']>self.data['current_date']:raise ValueError('FUTURE_OBSERVATION_SOURCE')
        if len(paths)>2:raise ValueError('observation supports at most two paths')
        p=self._fork((pid,));day=date or self.data['current_date']
        if day<self.data['current_date']:raise ValueError('STALE_OBSERVATION_TIMESTAMP')
        p._reserve_day(pid,day,'watch',event_id,minutes=90)
        reward=Training.development_reward(p.data['players'][pid],'observation',paths,'watch:'+event_id,source['log_sha256'],quality=quality)
        e=dict(type='observation',player_id=pid,source_match_id=source_match_id,date=day,reward=reward)
        p.data['events'][event_id]=e;p._record('event',event_id,e);p.data['current_date']=max(p.data['current_date'],e.get('date',p.data['current_date']));self._commit(p);return e

    def redeem_voucher(self,pid,voucher_id,paths,event_id,*,date=None):
        self._writable();self._check_actor(pid)
        self._new_id(event_id);p=self._fork((pid,));s=p.data['players'][pid];v=Training.ensure(s)['vouchers'].get(voucher_id)
        if not v or v.get('used'):raise ValueError('VOUCHER_MISSING_OR_USED')
        if len(paths)>2:raise ValueError('observation voucher supports at most two paths')
        day=date or self.data['current_date']
        if day<self.data['current_date']:raise ValueError('STALE_OBSERVATION_TIMESTAMP')
        p._reserve_day(pid,day,'watch',event_id,minutes=90)
        reward=Training.development_reward(s,'observation',paths,'voucher:'+voucher_id,digest(v),quality=.5)
        v=Training.ensure(s)['vouchers'][voucher_id];v.update(used=True,redeemed_event=event_id)
        e=dict(type='voucher_redemption',player_id=pid,voucher_id=voucher_id,date=day,reward=reward)
        p.data['events'][event_id]=e;p._record('event',event_id,e);p.data['current_date']=max(p.data['current_date'],e.get('date',p.data['current_date']));self._commit(p);return e

    def _event_rewards(self,event,bracket,winner,entry_CA):
        results={};major=event['level'] in ('olympics','world_championships','world_cup','major')
        if not major:return results
        for pid in entry_CA:
            logs=[self.data['matches'][b['match_id']] for b in bracket if pid in b['players']]
            opp=[entry_CA[next(q for q in l['participant_ids'] if q!=pid)] for l in logs]
            if not logs or sum(opp)/len(opp)<155:continue
            usage=Counter()
            for l in logs:usage.update(l['exposure_by_player'][l['participant_ids'].index(pid)]['usage'])
            paths=[k for k,v in usage.most_common(3) if v>=4]
            if not paths:continue
            kind='champion' if pid==winner and len(entry_CA)>=4 and sum(opp)/len(opp)>=165 and sum(v>=entry_CA[pid]-8 for v in opp)>=2 else 'participation'
            quality=max(0.,min(1.,(sum(opp)/len(opp)-130)/60))
            try:results[pid]=Training.development_reward(self.data['players'][pid],kind,paths,
                f"{kind}:{event['event_id']}:{pid}",digest([event['event_id'],pid,[l['log_sha256'] for l in logs]]),quality=quality)
            except ValueError as error:results[pid]=dict(granted=False,reason=str(error))
        return results

    def recover_day(self,pid,event_id,*,date=None,method='sleep'):
        self._writable();self._new_id(event_id);self._check_actor(pid)
        rates=dict(sleep=4.,physio=5.,light_rest=2.)
        if method not in rates:raise ValueError('known recovery method required')
        day=date or self.data['current_date']
        if day<self.data['current_date']:raise ValueError('STALE_RECOVERY_TIMESTAMP')
        p=self._fork((pid,));p._reserve_day(pid,day,'rest',event_id,minutes=360)
        state=p.data['players'][pid];before=state['fatigue'];state['fatigue']=max(0.,before-rates[method])
        e=dict(type='daily_recovery',player_id=pid,date=day,method=method,fatigue_before=before,fatigue_after=state['fatigue'],
            permanent_P_or_PA_gain=0,not_recounted_by_phase_training=True)
        p.data['events'][event_id]=e;p._record('event',event_id,e);p.data['current_date']=day;self._commit(p);return e

    def run_group(self,event_id,participant_ids,seed,*,best_of=5,detail_level='summary',kind='youth_singles',
                  allow_experimental_specialist_summary=False,tiebreaks=None):
        """Simulated round robin, explicit rules. Does not invent a historical draw."""
        from Game.competition_v1_18 import group_table,DEFAULT_TIEBREAKS
        from Game.formats_v1_18 import validate_format
        self._writable();self._new_id(event_id);validate_format(best_of)
        if kind not in ('youth_singles','adult_singles') or not 2<=len(participant_ids)<=8 or len(set(participant_ids))!=len(participant_ids):
            raise ValueError('2..8 distinct actors and explicit singles category required')
        for pid in participant_ids:self._check_actor(pid)
        if detail_level=='summary' and not allow_experimental_specialist_summary:
            from Game.tactics_v117 import specialist_kind
            from specialist_rubber_v116 import rubber_for
            if any(specialist_kind(self._match_card(pid)) in ('chopper','short_pips','long_pips') or
                   any(rubber_for(self._match_card(pid),w) in ('short_pips','long_pips','raw_pips','anti_spin') for w in ('fh','bh')) for pid in participant_ids):
                raise ValueError('SPECIALIST_SUMMARY_REQUIRES_EXPLICIT_EXPERIMENTAL_OPT_IN')
        p=self._fork(participant_ids);rng=legacy_career.rng_for(seed,self.data['world_id'],event_id)
        ids=list(participant_ids);rng.shuffle(ids)
        if len(ids)%2:ids.append(None)
        rotation=list(ids);logs=[]
        for round_index in range(len(ids)-1):
            day=(date.fromisoformat(self.data['current_date'])+timedelta(days=round_index)).isoformat()
            for i in range(len(ids)//2):
                a,b=rotation[i],rotation[-1-i]
                if a is None or b is None:continue
                mid=f'{event_id}:r{round_index+1}:m{i+1}'
                logs.append(p._play(a,b,mid,rng.randrange(2**31),best_of=best_of,detail_level=detail_level,
                    kind=kind,event_id=event_id,when=day,anti_shutout=False if detail_level=='full' else None,allow_experimental_specialist_summary=allow_experimental_specialist_summary))
            rotation=[rotation[0],rotation[-1],*rotation[1:-1]]
        table=group_table(participant_ids,logs,best_of=best_of,tiebreaks=tiebreaks or DEFAULT_TIEBREAKS)
        # Individual matches defer health to this group transaction; resolve once
        # per participant before commit, using only this group's accumulated effort.
        health={pid:p._injury_chance(pid,event_id,sum(p._effort(log,log['participant_ids'].index(pid))[0]
            for log in logs if pid in log['participant_ids'])) for pid in participant_ids}
        e=dict(type='completed_group',event_id=event_id,date=p.data['current_date'],classification='SIMULATED',
            best_of=best_of,kind=kind,table=table,matches=[l['match_id'] for l in logs],post_event_health=health,
            historical_status='HYPOTHETICAL_UNLESS_CALLER_PROVIDES_VERIFIED_ENTRY_EVIDENCE')
        if allow_experimental_specialist_summary and detail_level=='summary':e.update(calibration_status='UNCALIBRATED',experimental_scope='SPECIALIST_SUMMARY')
        p.data['events'][event_id]=e;p._record('event',event_id,e);self._commit(p);return copy.deepcopy(e)

    def attach_legacy_artifact(self,match_id,path):
        import json
        from pathlib import Path
        from Game import v118 as legacy_game
        log=self.data['matches'][match_id];raw=json.loads(Path(path).read_text())
        if log.get('classification')!='ARCHIVED_LEGACY_RESULT':raise ValueError('explicit archived match required')
        legacy_game.verify_log(raw)
        if raw['log_sha256']!=log.get('original_log_sha256') or raw['world_id']!=log.get('original_world_id') or raw['match_id']!=log.get('original_match_id'):
            raise ValueError('LEGACY_ARTIFACT_SOURCE_MISMATCH')
        self.artifacts['legacy:'+raw['log_sha256']]=raw;return raw['log_sha256']

    def _narrate_archived(self,match_id,*,seed=None,history=None):
        import narrative_v1_18 as narrative
        log=self.data['matches'][match_id];raw=self.artifacts.get('legacy:'+str(log.get('original_log_sha256')))
        names=[]
        for p in log['participant_ids']:
            row=self.data['v1_18']['player_registry'].get(p,{})
            name=row.get('name_en',self.data['metadata'].get(p,{}).get('name_zh',p))
            names.append(dict(player_id=p,name_zh=name))
        chosen=raw or log
        if raw:names=[dict(player_id=p,name_zh=names[i]['name_zh']) for i,p in enumerate(raw['participant_ids'])]
        result=narrative.render_match(chosen,cards=names,seed=self.data['seed'] if seed is None else seed,history=history)
        result['historical_source_notice']=dict(classification='ARCHIVED_SIMULATION_NOT_AUTHENTICATED_REAL_HISTORY',
            canonical_match_id=match_id,original_world_id=log.get('original_world_id'),original_log_sha256=log.get('original_log_sha256'),
            detailed_artifact_attached=raw is not None)
        return result

    def attach_probability_audit(self,path):
        import json
        from pathlib import Path
        log=json.loads(Path(path).read_text());Game.verify_log(log)
        if not log.get('anti_shutout') or not any(m.get('source_log_sha256')==log['log_sha256'] for m in self.data['matches'].values()):
            raise ValueError('probability audit is not referenced by this World')
        if digest(log.get('psychology_audit',[]))!=log.get('psychology_audit_sha256'):raise ValueError('PROBABILITY_AUDIT_HASH_MISMATCH')
        self.artifacts['psychology:'+log['log_sha256']]=log;return log['log_sha256']

    def activate_player_snapshot(self,player_id,event_id):
        """Activate a locked card at the current clock; never generate missing skills."""
        self._writable();self._new_id(event_id)
        if player_id in self.data['players']:raise ValueError('PLAYER_ALREADY_ACTIVE_NO_REROLL')
        source=registry.select(self.data['v1_18']['player_registry'],player_id,self.data['current_date'])
        if source.get('card') is None:raise ValueError('IDENTITY_ONLY_NEEDS_EXPLICIT_COMPLETE_CARD')
        card=copy.deepcopy(source['card']);day=date.fromisoformat(self.data['current_date']);observed=date.fromisoformat(source['as_of'])
        age=card.get('age_approx',card.get('age',day.year-card.get('birth_year',day.year-18)))+(day-observed).days/365.2425
        card.update(year=day.year,snapshot_date=day.isoformat(),model_start_age=age,age_approx=age,
            selection=dict(mode='PRIOR_BASELINE_NOT_GROWN'),classification='CARRIED_FORWARD_ASSESSMENT')
        card=Card.normalize(card);p=self._fork();primary=p.data['players'][p.data['main_player_id']]
        state=Training.initialize(card,seed=p.data['seed'],start_age=age,curve=card.get('growth_curve','balanced_progress'))
        state['month']=primary['month'];state['training_release'].update(month=primary['month'],phase=primary['training_release']['phase'])
        state['start_age']=age-(primary['month']+primary['training_release']['phase']/2)/12
        if isinstance(card.get('xp'),dict) and set(card['xp'])==Training.PATHS:
            state['xp']=copy.deepcopy(card['xp']);Training.ensure(state)['initial_xp_total']=sum(state['xp'].values())
        p.data['players'][player_id]=state;p.data['metadata'][player_id]=card
        from world_v1_18 import _activity
        p.data['activity'][player_id]=_activity(state)
        p.data['resources'][player_id]=dict(year=day.year,investment_units=12,national_eligible=False,frontier_tokens=0,
            reward_tokens_granted=0,championship_windows=0,paid_camp_until=0,provenance='EXPLICIT_SNAPSHOT_ACTIVATION')
        book=Card.RankingBook.from_snapshot(p.data['ranking']);book.register_player(player_id);p.data['ranking']=book.snapshot()
        event=dict(type='player_snapshot_activation',player_id=player_id,date=day.isoformat(),source_snapshot_sha256=source['sha256'],
            source_as_of=source['as_of'],numeric_policy='LOCKED_VALUES_CARRIED_FORWARD_NO_UNRECORDED_TRAINING',
            clock=dict(month=state['month'],phase=state['training_release']['phase']))
        if day.isoformat() not in p.data['v1_18']['player_registry'][player_id]['snapshots']:
            registry.register(p.data['v1_18']['player_registry'],player_id,card,as_of=day.isoformat(),source_ref=source['sha256'],classification='CARRIED_FORWARD_ASSESSMENT')
        p.data['events'][event_id]=event;p._record('event',event_id,event);self._commit(p);return event

    def apply_patch(self,patch_id,**kwargs):
        from patches_v1_18 import apply
        return apply(self,patch_id,**kwargs)


    def set_physical_fatigue(self,enabled,event_id):
        if type(enabled)is not bool:raise ValueError('boolean physical fatigue switch required')
        self._new_id(event_id);p=self._fork();p.data['v1_18']['patches']['physical_fatigue']=enabled
        e=dict(type='physical_execution_switch',enabled=enabled,date=self.data['current_date'],coefficient_version='V1.18-PHYSICAL-FATIGUE-1')
        p.data['events'][event_id]=e;p._record('event',event_id,e);self._commit(p);return e

    def save(self,path,*,overwrite=False):
        """Atomic checkpoint replacement, with a validated previous-version backup."""
        import os
        from pathlib import Path
        import tempfile
        target=Path(path);target.parent.mkdir(parents=True,exist_ok=True);payload=self.dump()
        if target.exists():
            if not overwrite:raise ValueError('CHECKPOINT_ALREADY_EXISTS')
            previous=target.read_text(encoding='utf-8');prior=type(self).load(previous)
            if prior.data['world_id']!=self.data['world_id']:raise ValueError('DIFFERENT_WORLD_CHECKPOINT_OVERWRITE')
        else:previous=None
        def temporary(text):
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,prefix=target.name+'.tmp-',delete=False) as f:
                f.write(text);f.flush();os.fsync(f.fileno());return Path(f.name)
        temp=temporary(payload)
        try:
            if previous is not None:
                backup=target.with_name(target.name+'.bak');old_temp=temporary(previous)
                os.replace(old_temp,backup)
            if overwrite:os.replace(temp,target)
            else:os.link(temp,target);temp.unlink()
        finally:
            if temp.exists():temp.unlink()
        return dict(path=str(target),sha256=hashlib.sha256(payload.encode()).hexdigest(),atomic=True,backup_created=previous is not None)

    @classmethod
    def load_file(cls,path,*,recover_backup=False):
        from pathlib import Path
        target=Path(path)
        try:return cls.load(target.read_text(encoding='utf-8'))
        except (ValueError,OSError):
            if not recover_backup:raise
            return cls.load(target.with_name(target.name+'.bak').read_text(encoding='utf-8'))
