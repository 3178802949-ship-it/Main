"""Explicit, repeatable V117-to-V1.18 migration into a new worldline.

Original bytes are never overwritten. Archived results retain source identities;
no game is rerun and no retrospective health or official ranking is invented.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from common import ROOT,canonical_json
from Training import v118 as old_training
from Training import v1_18 as Training
from Game import v118 as old_game
from Game import v1_18 as Game
from Game.formats_v1_18 import validate_result
from world_extensions_v1_18 import initial_extensions,digest
import player_registry_v1_18 as registry

LEGACY_FORMAT='SPIN_ERA_V1.1.7_COMPREHENSIVE_1'
LEGACY_FINGERPRINT='8553215625546b27fe3bb066b9712909e6a1e88ba41d3c91c95630befd0f54fd'

def _sha(b):return hashlib.sha256(b).hexdigest()

def verify_legacy(blob):
    wrapper=json.loads(blob)
    if wrapper.get('format')!=LEGACY_FORMAT:raise ValueError('SUPPORTED_LEGACY_RELEASE_REQUIRED')
    data=wrapper['payload'];encoded=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    if _sha(encoded.encode())!=wrapper['sha256']:raise ValueError('LEGACY_WORLD_CHECKSUM_MISMATCH')
    fp=data['ruleset_fingerprint']
    if fp.get('sha256')!=LEGACY_FINGERPRINT or digest(fp['files'])!=LEGACY_FINGERPRINT:
        raise ValueError('UNSUPPORTED_LEGACY_DEPENDENCY_FINGERPRINT')
    for name,expected in fp['files'].items():
        relative='legacy_v117/simulator.py' if name=='simulator.py' else name
        path=(ROOT/relative).resolve()
        if not path.is_relative_to(ROOT) or _sha(path.read_bytes())!=expected:raise ValueError('LEGACY_DEPENDENCY_DIFFERS:'+name)
    from world_v118 import WorldSession as OldWorld
    for pid,s in data['players'].items():data['players'][pid]=old_training.load_state(json.dumps(s,ensure_ascii=False))
    OldWorld(data).consistency_check(deep=False)
    return data

def _resolve(obj,path):
    tokens=re.findall(r'\.([^\.\[\]]+)|\[(\d+)\]',path[1:])
    if path!='$'+''.join('.'+k if k else '['+i+']' for k,i in tokens):raise ValueError('bad evidence JSON path')
    for key,idx in tokens:obj=obj[key] if key else obj[int(idx)]
    return obj

def validate_reconciliation(bundle):
    index={x['sha256']:x for x in bundle['source_index']};objects={}
    base=ROOT/'data/v1_18/handoff2004/sources'
    for sha in index:
        if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('invalid source hash')
        b=(base/(sha+'.json')).read_bytes()
        if _sha(b)!=sha:raise ValueError('ARCHIVE_SOURCE_CHANGED')
        objects[sha]=json.loads(b)
    seen=set()
    for item in bundle['records']:
        rec=item['record'];source=_resolve(objects[rec['source_file_sha256']],rec['json_path'])
        raw=source.get('full_receipt') or source.get('result') or source.get('match') or source.get('raw',{}).get('match') or source
        if digest(raw)!=rec['receipt_canonical_sha256'] or raw!=item['raw']:raise ValueError('ARCHIVE_ROW_EVIDENCE_MISMATCH')
        if rec['receipt_canonical_sha256'] in seen:raise ValueError('DUPLICATE_ARCHIVE_MATCH')
        seen.add(rec['receipt_canonical_sha256'])
        score=dict(best_of=rec['best_of_inferred'],games_won=rec['games_won'],winner=rec['games_won'].index(max(rec['games_won'])),
            games=[dict(score=s,winner=int(s[1]>s[0])) for s in rec['scores']])
        validate_result(score)
        if raw.get('log_sha256'):old_game.verify_log(raw)
    for row in bundle['locked_cards']:
        if row['source_sha256'] not in objects or objects[row['source_sha256']]!=row['card']:raise ValueError('LOCKED_CARD_EVIDENCE_MISMATCH')
    return True

def _slug(name):
    key=unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().lower()
    return 'archived_'+re.sub('[^a-z0-9]+','_',key).strip('_')

def _archived_result(rec,raw,ids,world_id):
    games=[dict(score=list(s),winner=int(s[1]>s[0]),points_count=sum(s)) for s in rec['scores']]
    mid='legacy2004:'+(rec['receipt_identity']['match_id'] or rec['event']+':'+str(rec['seed'])+':'+rec['receipt_canonical_sha256'][:12])
    result=dict(ruleset='V1.18-1',classification='ARCHIVED_LEGACY_RESULT',world_id=world_id,match_id=mid,
        participant_ids=ids,seed=rec['seed'],best_of=rec['best_of_inferred'],first_server=0,
        winner=rec['games_won'].index(max(rec['games_won'])),games_won=list(rec['games_won']),games=games,
        points=sum(sum(s) for s in rec['scores']),mode='summary',source_mode='full' if rec['evidence_tier']=='HASH_BOUND_FULL_SHOT_LOG' else 'summary',
        narrative_scope='AGGREGATE_ONLY',compact_receipt=True,input_cards_sha256=None,
        source_receipt_canonical_sha256=rec['receipt_canonical_sha256'],source_file_sha256=rec['source_file_sha256'],
        original_world_id=rec['receipt_identity']['world_id'],original_match_id=rec['receipt_identity']['match_id'],
        original_log_sha256=rec['receipt_identity']['log_sha256'],source_archive_path=rec['source_archive_path'],
        source_json_path=rec['json_path'],evidence_tier=rec['evidence_tier'],historical_authentication='NOT_VERIFIED',
        fatigue_cost_evidence=dict(per_player=[],estimated=True,reason='NO_RETROACTIVE_HEALTH_RECONSTRUCTION'))
    exposure=raw.get('exposure_by_player') or (raw.get('exposure') if isinstance(raw.get('exposure'),list) else None)
    if exposure and len(exposure)==2 and all(isinstance(x,dict) and 'usage' in x for x in exposure):result['exposure_by_player']=copy.deepcopy(exposure)
    else:result['exposure_by_player']=[dict(usage={},pressure={}) for _ in ids]
    for key in ('mean_strokes','action_family_distribution','total_strokes','actions'):
        if key in raw:result[key]=copy.deepcopy(raw[key])
    result['log_sha256']=digest(result);Game.verify_log(result);return result

def migrate_checkpoint(blob,*,reconciliation=None,background_policy='club_auto',new_world_id=None):
    from world_v1_18 import WorldSession,VERSION,RULESET,ruleset_fingerprint
    wrapper=json.loads(blob)
    if wrapper.get('format')==VERSION:
        world=WorldSession.load(blob)
        if reconciliation is not None and world.data['v1_18'].get('migration',{}).get('reconciliation_sha256')!=digest(reconciliation):
            raise ValueError('MIGRATION_RECONCILIATION_CONFLICT')
        return world,dict(status='already_current',no_state_change=True)
    old=verify_legacy(blob);source_hash=_sha(blob.encode());data=copy.deepcopy(old)
    old_id=old['world_id'];data.update(version=VERSION,game_ruleset=RULESET,world_id=new_world_id or old_id+'::V1.18',
        ruleset_fingerprint=ruleset_fingerprint(),v1_18=initial_extensions())
    data['v1_18']['background_policy']=background_policy
    for state in data['players'].values():Training.ensure(state)
    migration=dict(source_world_id=old_id,source_checkpoint_sha256=source_hash,legacy_audit_head=old['audit_head'],
        source_ruleset_fingerprint=LEGACY_FINGERPRINT,reconciliation_sha256=digest(reconciliation) if reconciliation is not None else None,
        source_current_date=old['current_date'],target_current_date=data['current_date'],
        original_results_and_attributes_preserved=True,ranking_policy='OLD_WORLD_RATING_RETAINED; EXTERNAL_RESULTS_NOT_RETROACTIVELY_RERATED',
        patch_order=['P001_SHARED_CLOCK','P002_IDEMPOTENT_SETTLEMENT','P003_FORMAL_XP_RECONCILIATION','P004_FORMATS','P005_OPT_IN_ANTI_SHUTOUT','P006_PHYSICAL_FATIGUE'])
    data['v1_18']['migration']=migration
    world=WorldSession(data);world._register_initial_snapshots()
    # Existing legacy World matches already had rating/time settlement. Convert
    # only their containers, retaining original digests and no second rewards.
    if old['matches']:
        original_links=copy.deepcopy(data['audit_chain']);data['audit_chain']=[];data['audit_head']='0'*64
        migration['original_audit_chain_sha256']=digest(original_links)
        for mid,log in list(data['matches'].items()):
            adapted=copy.deepcopy(log);adapted.update(ruleset=RULESET,classification='ARCHIVED_LEGACY_RESULT',world_id=data['world_id'],original_log_sha256=log.get('full_log_sha256',log['log_sha256']),original_compact_sha256=log['log_sha256'],original_match_id=mid,original_world_id=old_id,
                best_of=2*max(log['games_won'])-1,first_server=0)
            adapted.pop('log_sha256',None);adapted['log_sha256']=digest(adapted);Game.verify_log(adapted);data['matches'][mid]=adapted
            data['v1_18']['settlements'][mid]=dict(status='migrated_existing_settlement',match_id=mid,receipt_hash=adapted['log_sha256'],transaction_hash=digest(['legacy-already-settled',log['log_sha256']]))
        for link in original_links:world._record(link['kind'],link['id'],data['matches'][link['id']] if link['kind']=='match' else data['events'][link['id']])
    for mid,m in data['matches'].items():
        key=digest(sorted(m['participant_ids']));h=data['v1_18']['h2h'].setdefault(key,dict(player_ids=sorted(m['participant_ids']),wins={},matches=[]));h['matches'].append(mid);q=m['participant_ids'][m['winner']];h['wins'][q]=h['wins'].get(q,0)+1
    pid=data['main_player_id'];main_before=world.card(pid);result_imports=[];xp_receipts=[];aliases={}
    if reconciliation is not None:
        if source_hash!=reconciliation['original_world_sha256']:raise ValueError('RECONCILIATION_SOURCE_WORLD_DIFFERS')
        validate_reconciliation(reconciliation)
        # Names map to locked identities where those exist; missing cards stay
        # identity-only and cannot be used as playable skill cards.
        for item in reconciliation['locked_cards']:
            card=item['card'];name=card.get('name_en');q=card['player_id']
            if name:aliases[name]=q
            registry.register(data['v1_18']['player_registry'],q,card,as_of=card.get('snapshot_date','2004-01-01'),
                source_ref=item['source_sha256'],classification='LOCKED_2004_ASSESSMENT')
        aliases.update({'Roger Federer':pid,'Federer':pid})
        for item in reconciliation['records']:
            rec,raw=item['record'],item['raw'];ids=[]
            for name in rec['players']:
                q=aliases.get(name,_slug(name));aliases[name]=q;ids.append(q)
                if q not in data['v1_18']['player_registry']:
                    data['v1_18']['player_registry'][q]=dict(player_id=q,name_en=name,snapshots={},classification='ARCHIVED_IDENTITY_ONLY_NO_INVENTED_CARD')
                else:data['v1_18']['player_registry'][q].setdefault('name_en',name)
            log=_archived_result(rec,raw,ids,data['world_id']);mid=log['match_id']
            if mid in data['matches']:raise ValueError('ARCHIVE_MATCH_ID_CONFLICT')
            data['matches'][mid]=log
            data['match_meta'][mid]=dict(date=rec['date'],event_id=None,ranking_settled=False,detail_level='summary',
                participant_clocks={},historical_import=True,date_provenance=rec['date_provenance'],source_log_sha256=rec['receipt_identity']['log_sha256'])
            # Recover documented contact usage. Sparse records earn no invented
            # contacts. The old 100-use credit convention is made explicit.
            exposure=raw.get('exposure_by_player') or (item.get('summary_row') or {}).get('exposure') or []
            if not exposure and isinstance(raw.get('exposure'),list):exposure=raw['exposure']
            i=ids.index(pid);counts=exposure[i].get('usage',{}) if len(exposure)==2 else {}
            grants={p:n/100 for p,n in counts.items() if p in Training.PATHS and isinstance(n,int) and n>0}
            reward=Training.award_xp(data['players'][pid],'legacy2004:'+rec['receipt_canonical_sha256'],grants,
                source_kind='LEGACY_USAGE_RECONCILIATION_100_TO_1',evidence_hash=rec['receipt_canonical_sha256'],exchange=False)
            xp_receipts.append(reward)
            settlement=dict(type='HistoricalMatchReconciliation',status='archived_applied',match_id=mid,receipt_hash=log['log_sha256'],
                transaction_hash=digest(['archive',rec['receipt_canonical_sha256']]),source='ARCHIVED_SIMULATION',
                retrospective_fatigue_or_injury_applied=False,ranking_rerated=False,XP=reward,
                source_original_world_id=rec['receipt_identity']['world_id'],source_original_match_id=rec['receipt_identity']['match_id'])
            data['v1_18']['settlements'][mid]=settlement;world._record('match',mid,log)
            eid='historical-reconciliation:'+mid;data['events'][eid]=settlement;world._record('event',eid,settlement)
            key=digest(sorted(ids));h=data['v1_18']['h2h'].setdefault(key,dict(player_ids=sorted(ids),wins={},matches=[]))
            h['matches'].append(mid);winner=ids[log['winner']];h['wins'][winner]=h['wins'].get(winner,0)+1
            result_imports.append(dict(match_id=mid,original_receipt_sha256=rec['receipt_canonical_sha256'],federer_won=rec['federer_won'],date=rec['date'],date_provenance=rec['date_provenance']))
        if reconciliation['poland_streak'].get('triggered'):
            aliases_fixed={'stable.consistency':'stable.sustain'}
            reward=Training.development_reward(data['players'][pid],'legacy_streak',['read.opponent_read','stable.sustain','bh.continuity'],
                'legacy2004:poland-streak',digest(reconciliation['poland_streak']),quality=.5)
            migration['explicit_subskill_aliases']=aliases_fixed;xp_receipts.append(reward)
        vouchers=Training.ensure(data['players'][pid])['vouchers']
        for n in range(reconciliation['athens']['observation_breakthrough_vouchers']):
            key=f'athens2004:{n+1}';vouchers[key]=dict(voucher_id=key,used=False,source_sha256=digest(reconciliation['athens']),
                kind='observation',source_date=reconciliation['athens']['date'],expiry=None)
        traits=['自负','娇气','完美主义']
        meta=data['metadata'][pid];original=meta.get('narrative_personality',[])
        merged=list(dict.fromkeys(original+traits))[:6];meta['narrative_personality']=merged
        meta['personality_profile']['simulation_traits']=merged
        migration['personality_extension_source']='YEAR_END_HANDOFF_USER_DECLARED_FICTION_NO_MATCH_MODIFIER'
        for source in reconciliation['source_index']:
            if source['filename'].endswith('dual_rankings_2004.json'):
                ledger=json.loads((ROOT/'data/v1_18/handoff2004/sources'/(source['sha256']+'.json')).read_text())
                data['v1_18']['legacy_points'][pid]=dict(source_sha256=source['sha256'],status='PARTIAL_EARLY_SEASON_LEDGER_NOT_YEAR_END_TOTAL',ledger=ledger,official_ranking_unknown=True,merged_into_2005_rating=False)
        migration['aggregate_pending_ledgers_not_added_twice']=True
        migration['original_2004_internal_points']='PARTIAL_EXTERNAL_LEDGER_RETAINED_IN_SOURCES_NOT_INVENTED_YEAR_END_RANKING'
    sync=world._sync_roster(policy=background_policy,source_id='migration-roster')
    migration['NPC_sync']=sync;after=world.card(pid)
    if any(after[k]!=main_before[k] for k in ('children','P6','G9','CA','PA','fatigue')):raise ValueError('LOCKED_MAIN_ATTRIBUTES_CHANGED')
    event=dict(type='version_migration',parent_checkpoint_sha256=source_hash,from_ruleset='V1.1.7-COMPREHENSIVE-1',to_ruleset=RULESET,
        source_world_id=old_id,worldline_id=data['world_id'],historical_matches=len(result_imports),
        XP_awarded=sum(sum(x.get('grants',{}).values()) for x in xp_receipts),original_CA=main_before['CA'],new_CA=after['CA'],
        no_match_replayed=True,no_2005_tournament_triggered=True)
    data['events']['migration:V1.18']=event;world._record('event','migration:V1.18',event)
    report=dict(status='MIGRATED_NEW_BRANCH',migration=migration,summary=event,imported_matches=result_imports,
        XP_receipts=xp_receipts,vouchers=copy.deepcopy(Training.ensure(data['players'][pid])['vouchers']),
        consistency=world.consistency_check(deep=True))
    return world,report
