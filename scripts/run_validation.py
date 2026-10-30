"""Each invocation owns a new directory; never clean working data."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

Path('.runtime').mkdir(exist_ok=True)
root = tempfile.mkdtemp(prefix='validation-', dir=Path('.runtime').resolve())
env = dict(os.environ, PDTL_ROOT=root, PDTL_DB=str(Path(root) / 'directory.sqlite3'), PYTHONPATH='src')
public = '--public' in sys.argv
command = ['python3', '-m', 'provider_directory_truth_layer.cli']
command += ['fetch-npi'] if public else ['run', '--payer-listings', 'data/raw/synthetic_payer_directory_listings.csv']
subprocess.run(command + ['--as-of', '2026-06-26'], env=env, check=True)
subprocess.run(['python3', 'scripts/validate_project.py'] + (['--public'] if public else []), env=env, check=True)
print('Retained validation root:', root)
