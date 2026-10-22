"""Explicit, dry-run-first application to a separate baseline-matching engine."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import stat
import tempfile

BUNDLE = Path(__file__).resolve().parent
IMMUTABLE_BASELINE = Path('/workspace/spin-era-v1_18-github/spin_era_v1_18').resolve()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def apply(engine_dir, *, write=False):
    engine = Path(engine_dir).resolve()
    target = engine / 'Game/competition_v1_18.py'
    resolved_target = target.resolve()
    if engine == IMMUTABLE_BASELINE or IMMUTABLE_BASELINE in engine.parents or IMMUTABLE_BASELINE in resolved_target.parents:
        raise ValueError('IMMUTABLE_BASELINE_REFUSED_USE_SEPARATE_COPY')
    manifest = json.loads((BUNDLE / 'PATCH_MANIFEST.json').read_text())
    original = (BUNDLE / 'ORIGINAL_competition_v1_18.py').read_bytes()
    patched = (BUNDLE / 'PATCHED_competition_v1_18.py').read_bytes()
    if sha(original) != manifest['original_sha256'] or sha(patched) != manifest['patched_sha256']:
        raise ValueError('PATCH_BUNDLE_HASH_MISMATCH')
    current = target.read_bytes()
    current_hash = sha(current)
    if current_hash == manifest['patched_sha256']:
        return dict(status='ALREADY_APPLIED', written=False, target=str(target), sha256=current_hash)
    if current_hash != manifest['original_sha256']:
        raise ValueError('BASELINE_SHA256_MISMATCH_NO_CHANGES')
    result = dict(status='DRY_RUN_READY', written=False, target=str(target),
        original_sha256=current_hash, patched_sha256=manifest['patched_sha256'],
        history_changed=False, checkpoint_migration_required_before_resume=True)
    if not write:
        return result
    mode = stat.S_IMODE(target.stat().st_mode)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.draw-identity-', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(patched)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    if sha(target.read_bytes()) != manifest['patched_sha256']:
        raise ValueError('PATCH_POST_WRITE_HASH_MISMATCH')
    result.update(status='APPLIED_TO_SEPARATE_COPY', written=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='Write separate copy; default is dry-run')
    args = parser.parse_args()
    print(json.dumps(apply(args.engine_dir, write=args.apply), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
