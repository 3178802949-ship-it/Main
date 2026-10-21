"""Build self-contained module archives and verify each in a clean directory."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
MODULES = ('Game', 'Card', 'Training', 'Area')
VERSION = 'SPIN_ERA_V1.1.6_MODULAR_CANDIDATE_1'
EXPECTED_TESTS = dict(Game=3, Card=22, Training=23, Area=22, Integrated=84)


def source_files(directory):
    return sorted(p for p in directory.rglob('*') if p.is_file()
                  and '__pycache__' not in p.parts and p.suffix != '.pyc'
                  and not {'checks', 'saves'}.intersection(p.relative_to(directory).parts)
                  and p.name != 'PACKAGE_MANIFEST.json')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(directory, package):
    value = dict(version=VERSION, package=package, python='3.11+', dependencies='STANDARD_LIBRARY_ONLY',
                 immutable_files_note='Keep mutable saves outside the shipped example files.',
                 files={p.relative_to(directory).as_posix(): digest(p) for p in source_files(directory)})
    (directory / 'PACKAGE_MANIFEST.json').write_text(json.dumps(value, ensure_ascii=False, indent=2))
    return value


def module_readme(module):
    details = {
        'Game': '''比赛入口：`Game.play_match([card_a, card_b], seed, match_id, world_id=...)`。
每张卡必须有完整43技术子值、P6及一致的G9/CA，两名球员身份不能重复。
本分包的 `data/presets_normalized.json` 提供 `starters.ma18` 可作为合成试验输入。
公开入口使用独立子进程并保留逐板日志；`Game.verify_log(log)`核对完整性。
比赛日志不是已结算排名，独立比赛也不会自动生成冠军或训练奖励。
不要在共享进程并发调用runtime底层旧比赛函数。''',
        'Card': '''完整卡入口：`Card.make_ma18()`、`Card.normalize(profile)`、`Card.get_preset(player_id, year)`。
`Card.recompute(card)`重算G9和CA；不能用PA或冠军史给当前比赛加G。
`Card.RankingBook`分别处理成人/青年Elo、单打/青年/团体赛事积分。
正式比赛调用settle_match，完整赛事结束调用record_event，ID不能重复。
默认world_ranking只报告样本排名；没有完整同期池时不得声称世界名次。
370张预设保留旧43子值、P6与CA，补齐发展档案属于模型评估。''',
        'Training': '''训练入口：`Training.initialize(card, seed=..., curve=...)`，随后按顺序调用settle_phase。
环境可用 `import career_v116; career_v116.environment('national')`；请先import Training以加载runtime路径。
每月两阶段。训练计划示例：
```python
plan = {'month': 0, 'phase': 0, 'mode': 'train', 'body': 'stamina',
        'technical': [{'group': 'read', 'specialize': ['self_read', 'choice']}, {'group': 'bh'}]}
receipt = Training.settle_phase(state, plan, env, 'unique-phase-id')
```
两种不同技术大类与一项体能特训，技术大类内可专精两子项；每专精一类多消耗3疲劳，不额外送骰。
其余大类低剂量一般训练，技术一般训练保留D100≤3卓越与受条件限制的教练纠错许可。
`mode='rest'`跳过训练并恢复。只能依序结算；用dump_state/load_state保存完整余额与阶段。
独立训练模块不负责正式比赛证据验证和世界账本，请使用总包整合入口实现生涯。''',
        'Area': '''时代入口：`Area.get_era(year)`，当前七时代覆盖2000—2027；2027没有已建人物池。
`list_presets`与`get_preset`默认精确年度；显式允许旧基线时仍不代表已补算成长。
`calendar_for_year`生成明确标记的沙盒配置/历史参考，`validate_calendar`检查结构与年份类别。
`check_entry`检查年龄、地区和报名日期冲突，不替代官方名额、选拔和资格赛。
用户已取消九大赛固定名单要求，普通大赛一般处理。全部模板日期须按模拟日期解释。
本分包没有NPC自动生涯、完整真实赛季和技术传播自动结算。'''
    }
    return f'''# 旋球年代 V1.1.6｜{module} 独立分包

本包为测试候选，包含{module}公开模块、匹配的common/runtime、数据及独立测试。
Python 3.11+，仅标准库。在本目录执行：

```bash
python verify_package.py
python self_test.py --module {module}
```

{details[module]}

runtime保留旧源作为依赖，不是另一套可以同时领取的生涯规则。请勿混用不同版本的分包文件。
本包用于模块检查与开发；要开始连续生涯，请使用Integrated总包中的WorldSession、开幕文档和完整存档。
一般训练、专精和疲劳已作功能与策略压力验证，历史级潜力兑现、完整史历及人口稀有率仍未通过独立验收。
'''


def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def stage_module(module, target):
    for directory in (module, 'common', 'runtime', 'data'):
        for path in source_files(ROOT / directory):
            copy_file(path, target / path.relative_to(ROOT))
    for name in ('self_test.py', 'verify_package.py', f'tests/test_{module.lower()}.py'):
        copy_file(ROOT / name, target / name)
    if module == 'Card':
        for name in ('reports/CARD_MIGRATION.json', 'docs/COMPLETE_CARD_MA18_ZH.md',
                     'examples/demo_output/COMPLETE_CARD_MA18.json'):
            copy_file(ROOT / name, target / name)
    if module == 'Game':
        for name in ('reports/GAME_BENCHMARK.json', 'reports/game_examples/ma_fan.json',
                     'reports/game_examples/zhang_joo.json'):
            copy_file(ROOT / name, target / name)
    if module == 'Training':
        copy_file(ROOT / 'reports/TRAINING_STRESS.json', target / 'reports/TRAINING_STRESS.json')
    (target / 'README_ZH.md').write_text(module_readme(module))


def archive(directory, package, output):
    path = output / f'Spin_Era_V1_1_6_{package}.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for source in sorted(source_files(directory) + [directory / 'PACKAGE_MANIFEST.json']):
            zipped.write(source, Path(f'Spin_Era_V1_1_6_{package}') / source.relative_to(directory))
    checksum = digest(path)
    path.with_suffix('.zip.sha256').write_text(f'{checksum}  {path.name}\n')
    return path, checksum


def verify_archive(path, package):
    with tempfile.TemporaryDirectory(prefix=f'spin-era-unpack-{package}-') as temp:
        with zipfile.ZipFile(path) as zipped:
            if zipped.testzip() is not None:
                raise AssertionError('zip CRC failed')
            zipped.extractall(temp)
        directory = Path(temp) / f'Spin_Era_V1_1_6_{package}'
        present_modules = [name for name in MODULES if (directory / name).is_dir()]
        if package in MODULES and present_modules != [package]:
            raise AssertionError('a standalone archive unexpectedly depends on other public modules')
        checked = subprocess.run([sys.executable, 'verify_package.py'], cwd=directory,
                                 capture_output=True, text=True, check=True)
        command = [sys.executable, 'self_test.py']
        if package in MODULES:
            command += ['--module', package]
        tested = subprocess.run(command, cwd=directory, capture_output=True, text=True, check=True)
        match = re.search(r'Ran (\d+) tests?', tested.stderr + tested.stdout)
        if not match or int(match[1]) != EXPECTED_TESTS[package]:
            raise AssertionError(f'unexpected test count: {tested.stderr}')
        item = dict(CRC_valid=True, manifest_valid=True, standalone_tests_passed=int(match[1]),
                    public_module_directories=present_modules,
                    verifier_stdout=checked.stdout.strip(), test_stdout=tested.stdout + tested.stderr)
        if package == 'Integrated':
            qa = subprocess.run([sys.executable, 'tests/run_release_qa.py'], cwd=directory,
                                capture_output=True, text=True, check=True)
            report = json.loads((directory / 'checks/release_qa/RELEASE_QA.json').read_text())
            item.update(fresh_demo_reproduced=report['fresh_demo_reproduced'],
                        checkpoint_continuation_exact=report['checkpoint_continuation_exact'],
                        release_qa_passed=True)
            subprocess.run([sys.executable, 'verify_package.py'], cwd=directory,
                           capture_output=True, text=True, check=True)
            item['manifest_still_valid_after_QA'] = True
        return item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or output.is_relative_to(ROOT):
        parser.error('output must be outside the source root')
    if not (ROOT / 'reports/RELEASE_QA.json').is_file():
        raise ValueError('run release QA before packaging')
    output.mkdir(parents=True, exist_ok=True)
    manifest(ROOT, 'Integrated')
    report = dict(version=VERSION, status='CLEAN_EXTRACTION_PASSED',
                  note='Each module verified without the other public module directories; no installation needed.',
                  packages={})
    with tempfile.TemporaryDirectory(prefix='spin-era-package-stage-') as stage:
        for package in (*MODULES, 'Integrated'):
            if package == 'Integrated':
                directory = ROOT
            else:
                directory = Path(stage) / package
                directory.mkdir()
                stage_module(package, directory)
                manifest(directory, package)
            path, sha256 = archive(directory, package, output)
            checks = verify_archive(path, package)
            report['packages'][package] = dict(file=path.name, bytes=path.stat().st_size,
                                              sha256=sha256, **checks)
            print(f'{package}: clean extraction and {checks["standalone_tests_passed"]} tests passed', flush=True)
    for source, name in ((ROOT / 'OPENING_ZH.md', 'Spin_Era_V1_1_6_OPENING_ZH.md'),
                         (ROOT / 'docs/COMPLETE_CARD_MA18_ZH.md', 'Spin_Era_V1_1_6_COMPLETE_CARD_ZH.md'),
                         (ROOT / 'docs/DIAGNOSIS_ZH.md', 'Spin_Era_V1_1_6_DIAGNOSIS_ZH.md')):
        shutil.copy2(source, output / name)
    (output / 'PACKAGING_VERIFICATION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: {'bytes': v['bytes'], 'passed': v['standalone_tests_passed']}
                      for k, v in report['packages'].items()}, indent=2))


if __name__ == '__main__':
    main()
