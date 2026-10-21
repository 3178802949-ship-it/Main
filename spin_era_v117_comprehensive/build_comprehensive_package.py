"""Build four independently usable modules and the integrated V1.1.7 candidate.

Every ZIP is extracted and verified; QA writes only outside immutable sources.
Large development experiments remain evidence with their original fingerprints.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = 'V1.1.7-COMPREHENSIVE-1'
MODULES = ('Game', 'Card', 'Training', 'Area')


def files(root):
    return sorted(p for p in root.rglob('*') if p.is_file()
        and not {'checks', 'saves', '__pycache__'}.intersection(p.relative_to(root).parts)
        and p.suffix != '.pyc' and p.name != 'PACKAGE_MANIFEST.json')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def manifest(root, name):
    result = dict(version=VERSION, package=name, python='3.11+', dependencies='STANDARD_LIBRARY_ONLY',
        entry='OPENING_COMPREHENSIVE_ZH.md' if name == 'Comprehensive' else 'README_ZH.md',
        files={p.relative_to(root).as_posix(): sha(p) for p in files(root)})
    write_json(root / 'PACKAGE_MANIFEST.json', result)
    return result


def source_inventory():
    baseline_path = ROOT / 'reports/v118/V117_BASELINE_MANIFEST.json'
    baseline = json.loads(baseline_path.read_text())['files']
    added, modified, preserved = [], [], []
    for path in files(ROOT):
        name = path.relative_to(ROOT).as_posix()
        if name == 'reports/comprehensive/SOURCE_CHANGES.json':
            continue
        digest = sha(path)
        if name not in baseline:
            added.append(dict(path=name, sha256=digest))
        elif baseline[name] != digest:
            modified.append(dict(path=name, baseline_sha256=baseline[name], candidate_sha256=digest))
        else:
            preserved.append(name)
    removed = [name for name in baseline if not (ROOT / name).is_file()]
    # The only replaced legacy document is the root README. All frozen engines,
    # fixtures and prior evidence retain their exact original bytes.
    unexpected = [row['path'] for row in modified if row['path'] != 'README.md']
    if removed or unexpected:
        raise ValueError(f'baseline changed: removed={removed}, modified={unexpected}')
    result = dict(version=VERSION, baseline='V1.1.7-CANDIDATE-1', modified=modified,
        added=added, preserved=preserved, removed=removed,
        note='Old sources/fixtures remain immutable; only root README changes the public entry.')
    write_json(ROOT / 'reports/comprehensive/SOURCE_CHANGES.json', result)
    return result


MODULE_SMOKE = r'''import copy
import json
import sys
from common import ROOT
module = sys.argv[1]
card = json.loads((ROOT/'data/presets_normalized.json').read_text())['starters']['ma18']
if module == 'Game':
    from Game import v118 as Game
    peer=copy.deepcopy(card); peer['player_id']='standalone-peer'
    for mode in ('summary','full'):
        result=Game.play_match([card,peer],117001,'standalone-'+mode,detail_level=mode)
        assert max(result['games_won'])==4 and Game.verify_log(result)
        assert Game.verify_log(Game.compact_log(result))
elif module == 'Card':
    from Card import v118 as Card
    value=Card.public_view(Card.normalize(card))
    assert value['children']==card['children'] and value['P6']==card['P6']
    assert 'style_profile' in value and 'personality_profile' not in value
    assert Card.audit_library()['snapshots_preserving_numeric_traits']==370
elif module == 'Training':
    from Training import v118 as Training
    import career_v116
    state=Training.initialize(card,seed=117001)
    plan=dict(month=0,phase=0,mode='train',body='stamina',technical=[dict(group='read'),dict(group='bh')])
    Training.settle_phase(state,plan,career_v116.environment('club'),'standalone-phase')
    assert Training.load_state(Training.dump_state(state))==state
    assert Training.performance_card(state)['CA']>=0
elif module == 'Area':
    from Area import v118 as Area
    assert Area.validate_calendar(Area.calendar_for_year(2028))['valid']
    assert Area.context_for_date('2028-07-30')['horizon_end']=='2028-07-30'
    try: Area.ensure_date('2028-07-31')
    except ValueError: pass
    else: raise AssertionError('horizon not enforced')
else: raise ValueError(module)
print(module+': independent comprehensive smoke passed')
''' 


def stage_module(module, target):
    for folder in (module, 'common', 'runtime', 'data'):
        for source in files(ROOT / folder):
            dest = target / source.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    for name in ('self_test.py', 'verify_package.py', f'tests/test_{module.lower()}.py'):
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dest)
    (target / 'verify_comprehensive_module.py').write_text(MODULE_SMOKE, encoding='utf-8')
    entries = dict(Game='from Game import v118 as Game；Game.play_match(..., detail_level="summary"或"full")',
        Card='from Card import v118 as Card；normalize / public_view / narrative_view / RankingBook',
        Training='from Training import v118 as Training；initialize / settle_phase / performance_card',
        Area='from Area import v118 as Area；calendar_for_year / validate_calendar / ensure_date')
    (target / 'README_ZH.md').write_text(f'''# 旋球年代 V1.1.7综合版｜{module} 分包

这是测试候选。仅依赖Python 3.11+标准库。入口：{entries[module]}。
本包只含此公开模块及common/runtime/data依赖，其他公开模块目录均不存在。

```bash
python verify_package.py
python self_test.py --module {module}
python verify_comprehensive_module.py {module}
```

独立模块用于检查与开发。持续生涯应使用Comprehensive总包的WorldSession，
由统一入口约束时间、训练资源、疲劳、比赛证据、积分和重复结算。
不要拼接不同版本的模块。旧runtime是冻结依赖，不应重复领取旧训练收益。
完整限制、实验结果与叙述要求请阅读总包OPENING_COMPREHENSIVE_ZH.md及技术报告。
''', encoding='utf-8')


def archive(root, name, output):
    archive_name = 'Spin_Era_V1_1_7_Comprehensive' if name == 'Comprehensive' else f'Spin_Era_V1_1_7_Comprehensive_{name}'
    path = output / f'{archive_name}.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for source in sorted(files(root) + [root / 'PACKAGE_MANIFEST.json']):
            zipped.write(source, Path(archive_name) / source.relative_to(root))
    path.with_suffix('.zip.sha256').write_text(f'{sha(path)}  {path.name}\n')
    return path, archive_name


def checked(command, root, log):
    result = subprocess.run([sys.executable, *command], cwd=root, text=True, capture_output=True)
    log.append(dict(command=command, returncode=result.returncode,
        stdout=result.stdout[-1200:], stderr=result.stderr[-1200:]))
    if result.returncode:
        raise RuntimeError(f'{command} failed: {(result.stdout + result.stderr)[-4000:]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT) or output.exists() and any(output.iterdir()):
        parser.error('output must be an empty directory outside the source')
    qa = json.loads((ROOT / 'reports/comprehensive/qa/COMPREHENSIVE_QA.json').read_text())
    if qa['status'] != 'FUNCTIONAL_QA_PASSED':
        raise ValueError('run final V1.1.7 QA first')
    for name, digest in qa['source_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError(f'QA source changed: {name}')
    from simulator import ruleset_fingerprint
    if qa.get('ruleset_fingerprint') != ruleset_fingerprint():
        raise ValueError('QA code/data fingerprint differs')
    current_py = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*.py')
        if not {'checks', 'saves', '__pycache__'}.intersection(p.relative_to(ROOT).parts)}
    if current_py != set(qa['source_sha256']):
        raise ValueError('QA Python inventory differs')
    changes = source_inventory()
    output.mkdir(parents=True, exist_ok=True)
    report = dict(version=VERSION, status='CLEAN_EXTRACTION_PASSED', packages={},
        modified_baseline_paths=[row['path'] for row in changes['modified']], baseline_files_removed=changes['removed'])
    with tempfile.TemporaryDirectory(prefix='v117-modules-') as temp:
        for module in (*MODULES, 'Comprehensive'):
            staged = ROOT if module == 'Comprehensive' else Path(temp) / module
            if staged != ROOT:
                staged.mkdir()
                stage_module(module, staged)
            mf = manifest(staged, module)
            path, dirname = archive(staged, module, output)
            logs = []
            with tempfile.TemporaryDirectory(prefix='v117-clean-extraction-') as extraction:
                with zipfile.ZipFile(path) as zipped:
                    if zipped.testzip() is not None:
                        raise ValueError('archive CRC error')
                    zipped.extractall(extraction)
                root = Path(extraction) / dirname
                checked(['verify_package.py'], root, logs)
                if module in MODULES:
                    if [m for m in MODULES if (root / m).exists()] != [module]:
                        raise ValueError('unexpected public module dependency')
                    checked(['self_test.py', '--module', module], root, logs)
                    checked(['verify_comprehensive_module.py', module], root, logs)
                else:
                    checked(['run_comprehensive_qa.py', '--output', str(root / 'checks/packaging')], root, logs)
                    clean = json.loads((root / 'checks/packaging/COMPREHENSIVE_QA.json').read_text())
                    if clean['tests'] != qa['tests']:
                        raise ValueError('clean extraction tests differ')
                checked(['verify_package.py'], root, logs)
            report['packages'][module] = dict(file=path.name, bytes=path.stat().st_size,
                sha256=sha(path), files=len(mf['files']), CRC_valid=True, checks=logs)
            print(f'{module}: clean extraction and checks passed', flush=True)
    for name in ('OPENING_COMPREHENSIVE_ZH.md', 'README_COMPREHENSIVE_ZH.md', 'docs/COMPREHENSIVE_QA_ZH.md',
                 'docs/V118_AUDIT_ZH.md', 'reports/comprehensive/qa/COMPREHENSIVE_QA.json'):
        shutil.copy2(ROOT / name, output / Path(name).name)
    write_json(output / 'COMPREHENSIVE_PACKAGING_VERIFICATION.json', report)
    print(json.dumps({k: dict(bytes=v['bytes'], sha256=v['sha256'])
        for k, v in report['packages'].items()}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
