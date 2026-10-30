"""An E2E server with invocation-owned storage and no server reuse."""
import os
from pathlib import Path
import subprocess
import tempfile

from demo_fixtures import generate
root = Path(tempfile.mkdtemp(prefix='browser-'))
# The Playwright invocation owns these inputs, as well as its separate database.
fixtures = Path(os.environ.get('PDTL_BROWSER_INPUTS', str(root/'inputs')))
generate(fixtures)
print(f'Browser root: {root}; inputs: {fixtures}', flush=True)
os.environ['PDTL_ROOT'] = str(root)
os.environ['PDTL_DB'] = str(root / 'directory.sqlite3')
os.environ['PYTHONPATH'] = 'src'
os.environ['PDTL_DEMO'] = '1'
subprocess.run(['python3','-m','provider_directory_truth_layer.cli','run','--as-of','2026-06-26','--payer-listings','data/raw/synthetic_payer_directory_listings.csv'], check=True)
from provider_directory_truth_layer.intake_api import create_workbench
import uvicorn
uvicorn.run(create_workbench(), host='127.0.0.1', port=8100)
