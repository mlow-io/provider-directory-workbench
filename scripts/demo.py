"""One offline demo launcher; defaults to fresh, owned local storage."""
import argparse
import os
import signal
import socket
from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from demo_fixtures import generate


def check_ports():
    """Fail before preparing storage when a demo port is already occupied."""
    with ExitStack() as stack:
        for port in (8000, 5173):
            listener = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind(('127.0.0.1', port))
            except OSError as exc:
                raise RuntimeError(f'Demo port {port} is unavailable; stop its existing service before launching') from exc


def stop_services(processes):
    for process in processes:
        # A launcher (such as npm) can exit while descendants remain. Stop each
        # service group created by this invocation, including that failed group.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, help='Resume an explicit demo root; never cleans it')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args(argv)
    if not args.prepare_only:
        try:
            check_ports()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    Path('.runtime').mkdir(exist_ok=True)
    root = (args.root or Path(tempfile.mkdtemp(prefix='employer-demo-', dir='.runtime'))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Never replace a resumed demo's original input files.
    if not (root/'inputs').exists():
        generate(root/'inputs')
    env = dict(os.environ, PDTL_ROOT=str(root), PDTL_DB=str(root/'directory.sqlite3'),
               PYTHONPATH='src', PDTL_API='http://127.0.0.1:8000', PDTL_DEMO='1')
    # Seed legacy evidence only if this explicitly selected demo root is new.
    if not (root/'directory.sqlite3').exists():
        subprocess.run([sys.executable, '-m', 'provider_directory_truth_layer.cli', 'run', '--as-of',
                        '2026-06-26', '--payer-listings', 'data/raw/synthetic_payer_directory_listings.csv'], env=env, check=True)
    from provider_directory_truth_layer.intake_store import IntakeStore
    IntakeStore(root/'directory.sqlite3', root)
    print(f'Demo root: {root}\nInputs: {root / "inputs"}\nOpen http://127.0.0.1:5173/?view=intake', flush=True)
    if args.prepare_only:
        return 0
    processes = []
    try:
        commands = [
            ('API', [sys.executable, '-m', 'provider_directory_truth_layer.intake_api']),
            ('UI', ['npm', 'run', 'dev', '--prefix', 'web', '--', '--host', '127.0.0.1', '--port', '5173', '--strictPort']),
        ]
        for _, command in commands:
            processes.append(subprocess.Popen(command, env=env, start_new_session=True))
        while True:
            for (name, _), process in zip(commands, processes):
                code = process.poll()
                if code is not None:
                    print(f'Demo {name} service exited unexpectedly (status {code}); stopping the demo. Storage is retained.', file=sys.stderr)
                    return 1
            time.sleep(0.1)
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print(f'Could not start demo services: {exc}. Storage is retained.', file=sys.stderr)
        return 1
    finally:
        stop_services(processes)


if __name__ == '__main__':
    sys.exit(main())
