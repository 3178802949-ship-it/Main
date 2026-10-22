"""Predeclared full-engine chopper/fatigue follow-up, 1000 matches each."""
from pathlib import Path
import json
import hashlib
import time
from concurrent.futures import ProcessPoolExecutor
import stress_v1_18 as bench
ROOT=Path(__file__).resolve().parents[1]

def main():
    out=ROOT/'reports/v1_18/full_followup'
    if out.exists():raise ValueError('fresh evidence path required')
    out.mkdir();base=json.loads((ROOT/'reports/v1_18/monte_carlo/PREDECLARED_PLAN.json').read_text())
    ps=[]
    for name in ('chopper_patch0','fatigue_patch0'):
        p=dict(next(p for p in base['configurations'] if p['id']==name));p.update(id=name+'_full',mode='full');ps.append(p)
    hashes=bench.source_hashes();hashes[str(Path(__file__).relative_to(ROOT))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (out/'PREDECLARED_PLAN.json').write_text(json.dumps(dict(configurations=ps,source_sha256=hashes),ensure_ascii=False,indent=2))
    acc={};tick=time.perf_counter();jobs=[(p,i,50) for p in ps for i in range(0,1000,50)]
    with ProcessPoolExecutor(max_workers=2) as pool:
        for i,(pid,row) in enumerate(pool.map(bench.task,jobs),1):
            if pid not in acc:acc[pid]=row
            else:
                for k,v in row.items():acc[pid][k]=max(acc[pid][k],v) if k in ('max_delta','XP_max_path_ratio') else acc[pid][k]+v
            if i%10==0:print(i,'/',len(jobs),'batches',flush=True)
    for p,h in hashes.items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,'source changed'
    for row in acc.values():row.update(A_win_rate=row['A_wins']/row['samples'],A_win_Wilson95=bench.wilson(row['A_wins'],row['samples']),shutout_rate=row['shutouts']/row['games'])
    (out/'REPORT.json').write_text(json.dumps(dict(status='EXECUTED_NOT_CALIBRATION_CERTIFICATION',total_matches=2000,results=acc,source_sha256=hashes,elapsed_seconds=time.perf_counter()-tick),ensure_ascii=False,indent=2));print('Complete 2000 follow-up matches',flush=True)
if __name__=='__main__':main()
