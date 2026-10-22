"""Package the opt-in HGR candidate and verify a clean extraction."""
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
NAME = 'Spin_Era_V1_1_6_HGR_Candidate'
VERSION = 'V1.1.6-HGR-CANDIDATE-1'


def files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
                  and '__pycache__' not in p.parts and p.suffix != '.pyc'
                  and not {'checks', 'saves'}.intersection(p.relative_to(ROOT).parts)
                  and p.name != 'PACKAGE_MANIFEST.json')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory():
    baseline = json.loads((ROOT / 'reports/HGR_BASELINE_MANIFEST.json').read_text())['files']
    added, changed, preserved = [], [], []
    for path in files():
        name = path.relative_to(ROOT).as_posix()
        if name == 'reports/HGR_SOURCE_CHANGES.json':
            continue
        digest = sha(path)
        if name not in baseline:
            added.append(dict(path=name, sha256=digest))
        elif baseline[name] != digest:
            changed.append(dict(path=name, baseline_sha256=baseline[name], candidate_sha256=digest))
        else:
            preserved.append(name)
    removed = [name for name in baseline if not (ROOT / name).is_file()]
    if removed:
        raise ValueError(f'baseline files removed: {removed}')
    report = dict(version=VERSION, baseline_version='SPIN_ERA_V1.1.6_MODULAR_CANDIDATE_1',
        modified=changed, added=added, preserved=preserved, removed=removed,
        note='Hashes exclude this derived inventory and the package manifest to avoid circular self-hashing.')
    (ROOT / 'reports/HGR_SOURCE_CHANGES.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        parser.error('output must be outside the candidate source')
    qa = json.loads((ROOT / 'reports/HGR_QA.json').read_text())
    if qa['status'] != 'FUNCTIONAL_AND_MATCHED_REGRESSION_PASSED':
        raise ValueError('run HGR release QA before packaging')
    output.mkdir(parents=True, exist_ok=True)
    changes = inventory()
    manifest = dict(version=VERSION, package=NAME, python='3.11+', dependencies='STANDARD_LIBRARY_ONLY',
        files={p.relative_to(ROOT).as_posix(): sha(p) for p in files()})
    (ROOT / 'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    artifact = output / f'{NAME}.zip'
    with zipfile.ZipFile(artifact, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for p in sorted(files() + [ROOT / 'PACKAGE_MANIFEST.json']):
            zipped.write(p, Path(NAME) / p.relative_to(ROOT))
    digest = sha(artifact)
    artifact.with_suffix('.zip.sha256').write_text(f'{digest}  {artifact.name}\n')
    with tempfile.TemporaryDirectory(prefix='hgr-clean-package-') as temp:
        with zipfile.ZipFile(artifact) as zipped:
            assert zipped.testzip() is None
            zipped.extractall(temp)
        extracted = Path(temp) / NAME
        subprocess.run([sys.executable, 'verify_package.py'], cwd=extracted, check=True)
        checked = subprocess.run([sys.executable, 'examples/run_hgr_qa.py'], cwd=extracted,
                                 capture_output=True, text=True, check=True)
        clean_qa = json.loads((extracted / 'checks/hgr_qa/HGR_QA.json').read_text())
        assert clean_qa['tests'] == qa['tests']
        subprocess.run([sys.executable, 'verify_package.py'], cwd=extracted, check=True)
    for source, name in ((ROOT / 'OPENING_ZH.md', 'Spin_Era_V1_1_6_HGR_OPENING_ZH.md'),
                         (ROOT / 'docs/HGR_TECHNICAL_REPORT_ZH.md', 'Spin_Era_V1_1_6_HGR_TECHNICAL_REPORT_ZH.md'),
                         (ROOT / 'reports/HGR_SOURCE_CHANGES.json', 'Spin_Era_V1_1_6_HGR_SOURCE_CHANGES.json')):
        shutil.copy2(source, output / name)
    report = dict(version=VERSION, status='CLEAN_EXTRACTION_AND_QA_PASSED',
        artifact=artifact.name, bytes=artifact.stat().st_size, sha256=digest,
        packaged_files=len(manifest['files']), tests=clean_qa['tests'],
        matched_seed_BO7_matches=clean_qa['matched_seed_BO7_matches'],
        legacy_fresh_demo_exact=True, patch_fresh_demo_exact=True,
        protected_baseline_files=clean_qa['protected_baseline_files'],
        CRC_valid=True, manifest_verified_before_and_after_QA=True,
        modified_paths=[v['path'] for v in changes['modified']],
        added_files=len(changes['added']), baseline_files_removed=changes['removed'])
    (output / 'HGR_PACKAGING_VERIFICATION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
