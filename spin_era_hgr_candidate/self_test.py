"""Run only this package's supported public behavior tests."""
import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', choices=['Game', 'Card', 'Training', 'Area'])
    args = parser.parse_args()
    pattern = f'test_{args.module.lower()}.py' if args.module else 'test_*.py'
    tests = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=pattern)
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    if result.testsRun == 0:
        raise SystemExit('No tests executed')
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
