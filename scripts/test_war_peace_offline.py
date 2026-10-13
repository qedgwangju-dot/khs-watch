#!/usr/bin/env python3
"""Run War regressions with real network operations disabled in every process."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ('test_war_peace_runtime.py', 'test_war_peace_regression.py',
           'test_war_peace_oct04_regression.py', 'test_war_peace_integrity.py')
BOOTSTRAP = '''
import runpy, socket, sys, urllib.request
from pathlib import Path

def offline(*args, **kwargs):
    raise OSError("offline regression: network disabled")

urllib.request.urlopen = offline
socket.create_connection = offline
original_connect = socket.socket.connect
def offline_connect(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        return offline()
    return original_connect(sock, address)
socket.socket.connect = offline_connect
sys.path.insert(0, str(Path(sys.argv[1]).resolve().parent))
# Exercise the production wrapper with the full existing Oct04 guard fixtures.
if Path(sys.argv[1]).name == "test_war_peace_oct04_regression.py":
    import war_peace_reconstruction_watch_integrity
path = sys.argv[1]
sys.argv = [path]
runpy.run_path(path, run_name="__main__")
'''

if __name__ == '__main__':
    for script in SCRIPTS:
        subprocess.run([sys.executable, '-c', BOOTSTRAP, str(ROOT/'scripts'/script)],
                       cwd=ROOT, check=True)
    print('WAR_PEACE_OFFLINE_REGRESSIONS_OK')
