"""Explicit V1.18 new-world / 2005 migration entry. No automatic tournament."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from simulator import WorldSession,Card
from migration_v1_18 import migrate_checkpoint


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--from-2004',action='store_true');p.add_argument('--demo',action='store_true');a=p.parse_args()
    if a.output.exists() and any(a.output.iterdir()):raise ValueError('empty output directory required')
    a.output.mkdir(parents=True,exist_ok=True)
    if a.from_2004:
        src=ROOT/'data/v1_18/handoff2004';blob=(src/'WORLD_2005_OPENING_ORIGINAL.json').read_text()
        w,report=migrate_checkpoint(blob,reconciliation=json.loads((src/'RECONCILIATION_INPUT.json').read_text()))
        (a.output/'MIGRATION_DRY_RUN.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        (a.output/'ORIGINAL_WORLD_2005_OPENING.json').write_text(blob)
    else:
        card=Card.make_ma18();w=WorldSession.create([card],2006,start_date='2006-02-01',seed=118001)
    pid=w.data['main_player_id'];start=w.dump();(a.output/'START_WORLD_V1_18.json').write_text(start)
    (a.output/'COMPLETE_CARD_V1_18.json').write_text(json.dumps(w.card(pid),ensure_ascii=False,indent=2))
    if a.demo:
        s=w.data['players'][pid]
        w.train_phase(pid,dict(month=s['month'],phase=s['training_release']['phase'],technical=[dict(group='read',specialize=['opponent_read','choice']),dict(group='bh')],body='stamina'),'demo:training')
        (a.output/'DEMO_WORLD_V1_18.json').write_text(w.dump())
    print(json.dumps(dict(output=str(a.output),date=w.data['current_date'],valid=w.consistency_check(deep=True)['valid'],
        initial_checkpoint_sha256=hashlib.sha256(start.encode()).hexdigest(),matches=len(w.data['matches'])),ensure_ascii=False))
if __name__=='__main__':main()
