"""Run incident regressions with outbound networking disabled before imports."""
from pathlib import Path
import sys
import unittest


def deny_network(event, args):
    if event in {'socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'socket.gethostbyname'}:
        raise RuntimeError('Offline alert regression: outbound network forbidden')


if __name__ == '__main__':
    sys.addaudithook(deny_network)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / 'scripts'))
    suite = unittest.TestSuite()
    for pattern in ('test_bio_alert_regressions.py', 'test_texas_translation_regressions.py', 'test_clarity*.py', 'test_crcl_validation_regression.py', 'test_lng_parser_clock_regression.py', 'test_lng_collection_budget.py'):
        suite.addTests(unittest.defaultTestLoader.discover(str(root / 'tests'), pattern=pattern))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
