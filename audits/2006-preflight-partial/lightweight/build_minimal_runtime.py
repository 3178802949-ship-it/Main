"""Reversible packaging experiment; never mutates the source release."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys,zipfile,tempfile

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2))
def source_files(root):
 return sorted(p for p in root.rglob('*') if p.is_file() and not {'__pycache__','checks','saves'}.intersection(p.relative_to(root).parts) and p.suffix!='.pyc')
def run(root,code,*args):
 p=subprocess.run([sys.executable,'-c',code,*args],cwd=root,text=True,capture_output=True)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return json.loads(p.stdout)
PROBE=r'''
import copy,json,hashlib
from pathlib import Path
from simulator import WorldSession,Game,ruleset_fingerprint
from common import ROOT
p=ROOT/'examples/v1_18_opening/START_WORLD_V1_18.json'
blob=p.read_text();w=WorldSession.load(blob)
assert w.dump()==blob
assert w.consistency_check(deep=True)['valid']
c=json.loads((ROOT/'data/presets_normalized.json').read_text())['starters']['ma18']
a=copy.deepcopy(c);b=copy.deepcopy(c);a['player_id']='synthetic-lightweight-a';b['player_id']='synthetic-lightweight-b'
logs={}
for mode in ('summary','full'):
 r=Game.play_match([a,b],11820261022,'synthetic-lightweight-equivalence-'+mode,
   world_id='SYNTHETIC_PACKAGING_TEST_ONLY',best_of=3,detail_level=mode)
 assert Game.verify_log(r)
 assert Game.replay(Game.compact_log(r))['valid']
 logs[mode]=dict(log_sha256=r['log_sha256'],games_won=r['games_won'],points=r['points'])
print(json.dumps(dict(fingerprint=ruleset_fingerprint(),checkpoint_sha256=hashlib.sha256(blob.encode()).hexdigest(),
 checkpoint_roundtrip_exact=True,checkpoint_date=w.data['current_date'],matches=len(w.data['matches']),logs=logs)))
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 source=a.source.resolve();out=a.output.resolve()
 if out.exists() and any(out.iterdir()):raise ValueError('empty output required')
 out.mkdir(parents=True,exist_ok=True);stage=out/'Spin_Era_V1_18_MINIMAL_RUNTIME_EXPERIMENTAL';stage.mkdir()
 before=run(source,PROBE)
 all_files=source_files(source);included=[];excluded=[]
 module_dirs={'Game','Card','Training','Area','common','runtime','legacy_v117'}
 for f in all_files:
  r=f.relative_to(source);keep=(f.suffix=='.py' and (len(r.parts)==1 or r.parts[0] in module_dirs))
  keep=keep or (r.parts[0]=='data' and (len(r.parts)<2 or r.parts[1]!='v1_18'))
  keep=keep or (str(r) in ('examples/v1_18_opening/START_WORLD_V1_18.json','examples/v1_18_opening/COMPLETE_CARD_V1_18.json'))
  row=dict(path=str(r),sha256=sha(f),bytes=f.stat().st_size)
  if keep:
   dst=stage/r;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dst);included.append(row)
  else:excluded.append(row)
 for rel,h in before['fingerprint']['files'].items():
  if not (stage/rel).is_file() or sha(stage/rel)!=h:raise ValueError('fingerprint dependency missing or changed:'+rel)
 (stage/'README_MINIMAL_ZH.md').write_text('''# V1.18 最小运行包｜EXPERIMENTAL

这是已有V1.18源码的可逆分发实验，不是2004—2006新历史整合版，也不是替代全量史料的正式存档。新的完整历史ZIP超过输入读取限额，尚未读取其MASTER_PROMPT、SOURCE_MANIFEST和2005—2006原始比赛。本包的唯一预置生涯起点仍是2005-01-01；不能将它冒充2006年末恢复点。

Python3.11+，仅标准库。先运行：

```bash
python verify_package.py
```

恢复已有起点：

```python
from simulator import WorldSession
w=WorldSession.load_file('examples/v1_18_opening/START_WORLD_V1_18.json')
assert w.consistency_check(deep=True)['valid']
print(w.card(w.data['main_player_id']))
```

不要自动运行正式比赛，尤其不得擅自运行2007年赛事。预置起点2004赛果23场，只读保留，不重抽。

所有规则指纹文件及所需模块均与原V1.18字节一致，永久数值、随机调用和比赛算法没有改动。本实验只移除非运行必需的大型旧报告、重复演示、训练曲线、原始史料和全量审计证据；这些材料仍需保存在原完整包。删减清单逐项保留源路径、大小和SHA256。

本包保留一些历史迁移/构建Python文件作为冻结依赖或源码参考；由于原始史料和测试夹具不随本包分发，迁移、旧打包脚本和完整self_test.py不可在此独立运行，不把它们列为验收通过。若要重建2004迁移或写依据逐板日志的旧比赛叙述，请使用完整档案。精简包中的compact比分不能证明未随包保留的具体球路。

已经验证的范围：规则指纹一致；预置检查点load/dump字节一致并深度检查通过；同一合成输入、同seed的full/summary逐板日志hash分别与全包一致；两种日志可重播。该验证不构成新的历史、官方排名或竞技概率认证。

来源、逐项包含/删减清单见MINIMAL_SOURCE_INDEX.json。原始完整档案不要删除。
''')
 dump(stage/'MINIMAL_SOURCE_INDEX.json',dict(status='EXPERIMENTAL_RUNTIME_SPLIT',original_full_package='Spin_Era_V1_18_Integrated.zip',
   original_full_package_sha256='dd8b106f07c6133f371f59581e414a3916f075f01ea2b4bd182285e7260fdfad',
   source_fingerprint=before['fingerprint'],included=included,excluded=excluded,
   new_2006_history_status='NOT_READ_NOT_INTEGRATED',archival_truth_remains='ORIGINAL_FULL_PACKAGE_REQUIRED'))
 dump(stage/'PACKAGE_MANIFEST.json',dict(version='V1.18-1',package='MINIMAL_RUNTIME_EXPERIMENTAL',
   entry='README_MINIMAL_ZH.md',files={str(f.relative_to(stage)):sha(f) for f in source_files(stage)}))
 after=run(stage,PROBE)
 if before!=after:raise ValueError('packaging changed behavior')
 verify=subprocess.run([sys.executable,'verify_package.py'],cwd=stage,capture_output=True,text=True)
 if verify.returncode:raise ValueError(verify.stdout+verify.stderr)
 zpath=out/'Spin_Era_V1_18_MINIMAL_RUNTIME_EXPERIMENTAL.zip'
 with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for f in source_files(stage):
   info=zipfile.ZipInfo(str(Path(stage.name)/f.relative_to(stage)),date_time=(2026,10,22,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,f.read_bytes(),compresslevel=9)
 with tempfile.TemporaryDirectory() as tmp:
  with zipfile.ZipFile(zpath) as z:
   assert z.testzip() is None;z.extractall(tmp)
  extracted=Path(tmp)/stage.name
  if run(extracted,PROBE)!=before:raise ValueError('clean extraction behavior mismatch')
  subprocess.run([sys.executable,'verify_package.py'],cwd=extracted,check=True,capture_output=True)
 report=dict(status='MINIMAL_RUNTIME_SMOKE_PASSED',classification='EXPERIMENTAL',
   source_fingerprint_equal=True,checkpoint_roundtrip_exact=True,full_summary_same_seed_log_hashes_equal=True,
   original_full_zip_bytes=27587474,minimal_zip_bytes=zpath.stat().st_size,
   compressed_reduction_fraction=1-zpath.stat().st_size/27587474,
   original_source_file_count=len(all_files),included_source_file_count=len(included),excluded_source_file_count=len(excluded),
   source_uncompressed_bytes=sum(f.stat().st_size for f in all_files),minimal_uncompressed_bytes=sum(f.stat().st_size for f in source_files(stage)),
   zip_sha256=sha(zpath),zip_CRC_valid=True,clean_extract_reproduces=True,
   runtime_probe=before,full_unit_suite_run=False,
   full_unit_suite_reason='Full historical evidence, reports and test fixtures deliberately remain in full package; packaging smoke only.',
   no_official_matches_run=True,no_locked_historical_match_replayed=True,new_history_integrated=False)
 dump(out/'MINIMAL_RUNTIME_REPORT.json',report)
 zpath.with_suffix('.zip.sha256').write_text(sha(zpath)+'  '+zpath.name+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='runtime_probe'},indent=2))
if __name__=='__main__':main()
