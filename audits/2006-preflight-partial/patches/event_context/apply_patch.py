"""Apply only to an explicit disposable/candidate engine, never the baseline."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import tempfile

HERE = Path(__file__).resolve().parent
BASELINE = Path('/workspace/spin-era-v1_18-github/spin_era_v1_18').resolve()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def apply_to(engine, *, commit=False):
    engine = Path(engine).resolve()
    if engine == BASELINE:
        raise ValueError('ORIGINAL_BASELINE_READ_ONLY')
    manifest = json.loads((HERE / 'PATCH_MANIFEST.json').read_text())
    target = engine / manifest['base_file']
    replacement = (HERE / manifest['base_file']).read_bytes()
    if digest(replacement) != manifest['patched_sha256']:
        raise ValueError('PATCH_PAYLOAD_HASH_MISMATCH')
    current = target.read_bytes()
    if digest(current) == manifest['patched_sha256']:
        return {'status': 'already_applied', 'path': str(target)}
    if digest(current) != manifest['base_sha256']:
        raise ValueError('BASELINE_HASH_MISMATCH')
    if not commit:
        return {'status': 'dry_run_valid', 'path': str(target),
                'checkpoint_migration_required': True,
                'release_manifest_rebuild_required': True}
    backup = target.with_name(target.name + '.before_event_context_patch')
    if backup.exists() and backup.read_bytes() != current:
        raise ValueError('BACKUP_CONFLICT')
    if not backup.exists():
        backup.write_bytes(current)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=engine, delete=False) as handle:
            name = handle.name
            handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, target.stat().st_mode)
        os.replace(name, target)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
    return {'status': 'applied_to_candidate', 'path': str(target),
            'checkpoint_migration_required': True,
            'release_manifest_rebuild_required': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate-engine', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(apply_to(args.candidate_engine, commit=args.apply), indent=2))
