"""Build V1.18 total and four modules, then verify each clean extraction."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
ROOT=Path(__file__).resolve().parent;MODULES=('Game','Card','Training','Area')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def files(root):return sorted(p for p in root.rglob('*') if p.is_file() and not {'checks','saves','__pycache__'}.intersection(p.relative_to(root).parts) and p.suffix!='.pyc' and p.name!='PACKAGE_MANIFEST.json')
def write_json(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2))
def manifest(root,name):
    m=dict(version='V1.18-1',package=name,python='3.11+',dependencies='STANDARD_LIBRARY_ONLY',entry='OPENING_V1_18_ZH.md' if name=='Integrated' else 'README_ZH.md',files={str(p.relative_to(root)):sha(p) for p in files(root)})
    write_json(root/'PACKAGE_MANIFEST.json',m);return m

def inventory():
    old=json.loads((ROOT/'reports/v1_18/BASELINE_V117_MANIFEST.json').read_text())['files'];changed=[];missing=[]
    for name,d in old.items():
        p=ROOT/name
        if not p.exists():missing.append(name)
        elif sha(p)!=d:changed.append(name)
    if missing or set(changed)-{'README.md','simulator.py'}:raise ValueError(('legacy source changed',missing,changed))
    write_json(ROOT/'reports/v1_18/SOURCE_CHANGES.json',dict(baseline='V1.1.7-COMPREHENSIVE-1',modified_baseline_paths=changed,removed=missing,
        numerical_legacy_files_preserved=True,original_public_facade='legacy_v117/simulator.py',
        added=[str(p.relative_to(ROOT)) for p in files(ROOT) if str(p.relative_to(ROOT)) not in old]))

SMOKE=r'''import sys,json,copy,hashlib
from common import ROOT
m=sys.argv[1];c=json.loads((ROOT/'data/presets_normalized.json').read_text())['starters']['ma18']
if m=='Game':
 from Game import v1_18 as G
 d=copy.deepcopy(c);d['player_id']='module-peer'
 for mode in ('summary','full'):
  r=G.play_match([c,d],11899,'module-'+mode,best_of=3,detail_level=mode)
  assert G.verify_log(r) and G.verify_log(G.compact_log(r))
  assert G.replay(G.compact_log(r))['valid']
elif m=='Card':
 from Card import v1_18 as C
 x=C.public_view(C.normalize(c));assert x['children']==c['children'] and 'style_profile'in x and 'personality_profile'not in x
elif m=='Training':
 from Training import v1_18 as T
 import career_v116 as old
 s=T.initialize(c,seed=118);T.award_xp(s,'module-test',{'bh.spin':.25},source_kind='TEST',evidence_hash='0'*64)
 T.settle_phase(s,dict(month=0,phase=0,technical=[dict(group='read'),dict(group='bh')],body='stamina'),old.environment('club'),'module-phase')
 assert T.load_state(T.dump_state(s))==s
elif m=='Area':
 from Area import v1_18 as A
 assert A.validate_calendar(A.calendar_for_year(2028))['valid']
 assert A.HORIZON_END=='2028-07-30'
print(m+': independent V1.18 smoke passed')
'''

def stage(module,target):
    for folder in (module,'common','runtime','data'):
        for p in files(ROOT/folder):
            relative=p.relative_to(ROOT)
            if relative.parts[:2]==('data','v1_18'):continue
            d=target/relative;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,d)
    for name in ('self_test.py','verify_package.py',f'tests/test_{module.lower()}.py'):
        d=target/name;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,d)
    (target/'verify_v1_18_module.py').write_text(SMOKE)
    (target/'README_ZH.md').write_text(f'''# 旋球年代V1.18｜{module}分包

入口：`from {module} import v1_18 as {module}`。仅Python3.11+标准库。
只包含本模块及common/runtime/data依赖；持续生涯与2004存档迁移请使用总包的simulator.WorldSession。
旧默认模块是冻结依赖，不能替代V1.18结算，不要重复领取旧收益。

```bash
python verify_package.py
python self_test.py --module {module}
python verify_v1_18_module.py {module}
```

本分包不包含2004私有生涯档案。Game的实验反扑默认关闭，身体疲劳修复默认开启；兼容对照可显式physical_fatigue=False。
正式削球/颗粒summary仍有校准限制。详情见总包OPENING_V1_18_ZH.md和设计报告。
''')

def check(args,root):
    r=subprocess.run([sys.executable,*args],cwd=root,text=True,capture_output=True)
    if r.returncode:raise RuntimeError((r.stdout+r.stderr)[-6000:])
    return dict(command=args,returncode=r.returncode,output=(r.stdout+r.stderr)[-1000:])

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    if out.is_relative_to(ROOT) or out.exists() and any(out.iterdir()):raise ValueError('empty output outside source required')
    qa=json.loads((ROOT/'reports/v1_18/qa/V1_18_QA.json').read_text())
    if qa['status']!='FUNCTIONAL_QA_PASSED':raise ValueError('final QA required')
    from simulator import ruleset_fingerprint
    if qa['core_fingerprint']!=ruleset_fingerprint():raise ValueError('QA numerical source differs')
    for name,h in qa['source_sha256'].items():
        if sha(ROOT/name)!=h:raise ValueError('QA source changed:'+name)
    if set(qa['source_sha256'])!={str(p.relative_to(ROOT)) for p in files(ROOT) if p.suffix=='.py'}:raise ValueError('QA source inventory changed')
    inventory();out.mkdir(parents=True,exist_ok=True);result=dict(version='V1.18-1',status='CLEAN_EXTRACTION_PASSED',packages={})
    with tempfile.TemporaryDirectory() as t:
        for module in (*MODULES,'Integrated'):
            root=ROOT if module=='Integrated' else Path(t)/module
            if root!=ROOT:root.mkdir();stage(module,root)
            m=manifest(root,module);name=f'Spin_Era_V1_18_{module}';path=out/(name+'.zip')
            with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
                for f in files(root)+[root/'PACKAGE_MANIFEST.json']:z.write(f,Path(name)/f.relative_to(root))
            checks=[]
            with tempfile.TemporaryDirectory() as temp:
                with zipfile.ZipFile(path) as z:
                    if z.testzip()is not None:raise ValueError('ZIP CRC failure')
                    z.extractall(temp)
                clean=Path(temp)/name;checks.append(check(['verify_package.py'],clean))
                if module=='Integrated':checks.append(check(['run_v1_18_qa.py','--output',str(clean/'checks/clean_package')],clean))
                else:
                    if [x for x in MODULES if (clean/x).exists()]!=[module]:raise ValueError('unexpected module dependency')
                    checks.append(check(['self_test.py','--module',module],clean));checks.append(check(['verify_v1_18_module.py',module],clean))
                checks.append(check(['verify_package.py'],clean))
            result['packages'][module]=dict(file=path.name,bytes=path.stat().st_size,sha256=sha(path),checks=checks,CRC_valid=True,files=len(m['files']))
            path.with_suffix('.zip.sha256').write_text(sha(path)+'  '+path.name+'\n');print(module,'clean extraction passed',flush=True)
    for name in ('OPENING_V1_18_ZH.md','README_V1_18_ZH.md','docs/v1_18/DESIGN_AND_QA_ZH.md','docs/v1_18/ROLLBACK.md','reports/v1_18/qa/V1_18_QA.json','examples/v1_18_opening/MIGRATION_DRY_RUN.json'):
        shutil.copy2(ROOT/name,out/Path(name).name)
    write_json(out/'V1_18_PACKAGING_VERIFICATION.json',result);print(json.dumps({k:{x:v[x] for x in ('bytes','sha256')} for k,v in result['packages'].items()},indent=2))
if __name__=='__main__':main()
