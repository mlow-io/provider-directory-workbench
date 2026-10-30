"""Launcher failures must remain failures without touching unrelated service/storage."""
import importlib.util
import signal
import sqlite3
from pathlib import Path

import pytest

from provider_directory_truth_layer.intake_store import IntakeStore


@pytest.fixture
def launcher(monkeypatch):
    monkeypatch.syspath_prepend(str(Path('scripts').resolve()))
    spec = importlib.util.spec_from_file_location('pdtl_demo_launcher', 'scripts/demo.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def resumed_root(tmp_path):
    root = tmp_path/'demo'
    store = IntakeStore(root/'directory.sqlite3', root)
    (root/'inputs').mkdir()
    (root/'inputs'/'owner-original.txt').write_text('Retain this exact original')
    store.receive(b'[{}]', 'malformed.json')
    return root


def state(root):
    with sqlite3.connect(root/'directory.sqlite3') as conn:
        dump = '\n'.join(conn.iterdump())
    files = {str(p.relative_to(root)): p.read_bytes() for folder in ['inputs', 'artifacts']
             for p in (root/folder).iterdir() if p.is_file()}
    return dump, files


class Child:
    def __init__(self, pid, code=None):
        self.pid, self.code = pid, code

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        assert self.code is not None, 'Live child was not stopped'
        return self.code


def control_children(launcher, monkeypatch, children):
    pending = iter(children)
    signals = []
    monkeypatch.setattr(launcher, 'check_ports', lambda: None)
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *args, **kwargs: next(pending))

    def stop(pid, sig):
        child = next(child for child in children if child.pid == pid)
        if child.code is not None:
            raise ProcessLookupError
        signals.append((pid, sig))
        child.code = -sig

    monkeypatch.setattr(launcher.os, 'killpg', stop)
    return signals


def test_conflicting_port_fails_before_creating_a_root(launcher, monkeypatch, tmp_path, capsys):
    root = tmp_path/'not-created'

    def occupied():
        raise RuntimeError('Demo port 8000 is unavailable; stop its existing service before launching')

    monkeypatch.setattr(launcher, 'check_ports', occupied)
    assert launcher.main(['--root', str(root)]) == 1
    assert not root.exists()
    assert '8000 is unavailable' in capsys.readouterr().err


@pytest.mark.parametrize('failed_index,name', [(0, 'API'), (1, 'UI')])
@pytest.mark.parametrize('exit_code', [0, 23])
def test_unexpected_child_exit_fails_stops_sibling_and_preserves_data(
        launcher, monkeypatch, resumed_root, capsys, failed_index, name, exit_code):
    children = [Child(101), Child(102)]
    children[failed_index].code = exit_code
    signals = control_children(launcher, monkeypatch, children)
    before = state(resumed_root)
    assert launcher.main(['--root', str(resumed_root)]) == 1
    assert signals == [(children[1-failed_index].pid, signal.SIGTERM)]
    assert state(resumed_root) == before
    assert f'{name} service exited unexpectedly (status {exit_code})' in capsys.readouterr().err


def test_ctrl_c_is_success_and_stops_both_service_groups(launcher, monkeypatch, resumed_root):
    children = [Child(101), Child(102)]
    signals = control_children(launcher, monkeypatch, children)

    def ctrl_c(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(launcher.time, 'sleep', ctrl_c)
    before = state(resumed_root)
    assert launcher.main(['--root', str(resumed_root)]) == 0
    assert signals == [(101, signal.SIGTERM), (102, signal.SIGTERM)]
    assert state(resumed_root) == before


def test_failed_group_is_stopped_even_when_its_leader_has_exited(launcher, monkeypatch):
    # npm may exit while its Vite descendant still holds the service port.
    failed = Child(101, 23)
    signals = []
    monkeypatch.setattr(launcher.os, 'killpg', lambda pid, sig: signals.append((pid, sig)))
    launcher.stop_services([failed])
    assert signals == [(101, signal.SIGTERM)]


def test_missing_ui_executable_stops_started_api_and_returns_failure(launcher, monkeypatch, resumed_root, capsys):
    api = Child(101)
    signals = control_children(launcher, monkeypatch, [api])
    calls = []

    def launch(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            return api
        raise FileNotFoundError('npm unavailable')

    monkeypatch.setattr(launcher.subprocess, 'Popen', launch)
    before = state(resumed_root)
    assert launcher.main(['--root', str(resumed_root)]) == 1
    assert signals == [(101, signal.SIGTERM)]
    assert state(resumed_root) == before
    assert 'npm unavailable' in capsys.readouterr().err


def test_prepare_only_needs_no_free_ports_and_preserves_resumed_inputs(launcher, monkeypatch, resumed_root):
    def unexpected(*args, **kwargs):
        pytest.fail('prepare-only must not start services or check ports')

    monkeypatch.setattr(launcher, 'check_ports', unexpected)
    monkeypatch.setattr(launcher.subprocess, 'Popen', unexpected)
    before = state(resumed_root)
    assert launcher.main(['--prepare-only', '--root', str(resumed_root)]) == 0
    assert state(resumed_root) == before
