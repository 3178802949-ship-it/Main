"""Verify packaged immutable source/data/examples; runtime saves are separate."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / 'PACKAGE_MANIFEST.json').read_text())
    for name, digest in manifest['files'].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError(f'missing or invalid package path: {name}')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'package file differs: {name}')
    print(f"Verified {len(manifest['files'])} files: {manifest['package']}")


if __name__ == '__main__':
    main()
