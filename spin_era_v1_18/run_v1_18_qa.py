"""Functional regression, reproducible migration and source-bound release checks."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from simulator import WorldSession,ruleset_fingerprint

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def call(args,out,name):
    r=subprocess.run([sys.executable,*args],cwd=ROOT,text=True,capture_output=True)
    (out/name).write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError((r.stdout+r.stderr)[-6000:])
    return r.stdout+r.stderr

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('fresh output directory required')
    out.mkdir(parents=True,exist_ok=True);fp=ruleset_fingerprint()
    tests=call(['self_test.py'],out,'TESTS.txt');count=int(re.search(r'Ran (\d+) tests?',tests)[1])
    for name in ('fresh_a','fresh_b'):call(['examples/start_v1_18.py','--from-2004','--output',str(out/name)],out,name+'.txt')
    files=('START_WORLD_V1_18.json','COMPLETE_CARD_V1_18.json','ORIGINAL_WORLD_2005_OPENING.json','MIGRATION_DRY_RUN.json')
    exact=all(sha(out/'fresh_a'/f)==sha(out/'fresh_b'/f) for f in files)
    if not exact:raise ValueError('same-input migrations differ')
    shipped=ROOT/'examples/v1_18_opening'
    if not all(sha(shipped/f)==sha(out/'fresh_a'/f) for f in files):raise ValueError('shipped checkpoint differs from fresh migration')
    saved=(out/'fresh_a/START_WORLD_V1_18.json').read_text();w=WorldSession.load(saved)
    if saved!=w.dump():raise ValueError('checkpoint roundtrip differs')
    if w.data['current_date']!='2005-01-01' or len(w.data['matches'])!=23 or any(m.get('classification')!='ARCHIVED_LEGACY_RESULT' for m in w.data['matches'].values()):raise ValueError('frozen opening was advanced')
    card=w.card(w.data['main_player_id'])
    if (card['CA'],card['PA'],card['fatigue'])!=(150,191,0):raise ValueError('locked attributes differ')
    matrix=json.loads((ROOT/'reports/v1_18/monte_carlo/MONTE_CARLO_REPORT.json').read_text())
    extra=json.loads((ROOT/'reports/v1_18/full_followup/REPORT.json').read_text())
    if matrix['samples_per_configuration']<1000 or matrix['total_matches']!=42000 or extra['total_matches']!=2000:raise ValueError('required stress coverage missing')
    reward=json.loads((ROOT/'reports/v1_18/REWARD_PROBES.json').read_text())
    for report in (matrix,extra,reward):
        for name,digest in report['source_sha256'].items():
            if sha(ROOT/name)!=digest:raise ValueError('stress source changed:'+name)
    for name in ('WORLD_HORIZON_STRESS.json','WORLD_2005_INTEGRATION_STRESS.json'):
        report=json.loads((ROOT/'reports/v1_18'/name).read_text())
        if report['source_fingerprint']!=fp:raise ValueError('world stress has outdated source')
    if fp!=ruleset_fingerprint():raise ValueError('runtime changed while testing')
    result=dict(version='V1.18-1',status='FUNCTIONAL_QA_PASSED',tests=count,core_fingerprint=fp,
        two_migrations_byte_exact=exact,shipped_opening_exact=True,checkpoint_roundtrip_exact=True,
        no_2004_match_replayed=True,no_2005_tournament_triggered=True,canonical_opening=dict(date='2005-01-01',CA=150,PA=191,fatigue=0,record=[14,9],matches=23),
        final_stress_matches=matrix['total_matches']+extra['total_matches'],selected_matrix_configurations=matrix['configurations']+2,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in ROOT.rglob('*.py') if not {'checks','saves','__pycache__'}.intersection(p.relative_to(ROOT).parts)},
        qualification='Functional and conditional-model evidence, not real historical calibration.')
    (out/'V1_18_QA.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','core_fingerprint')},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
