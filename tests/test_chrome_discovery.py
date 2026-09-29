"""Tool-wide Chrome discovery (p6_export.pdf): probe once, cache the first browser that
prints, fall back past a broken one — and every PDF route prints through that ONE helper.

On the owner's PC the Playwright full Chromium cannot start at all ("[WinError 14001] …
side-by-side configuration is incorrect"); server._find_chrome() used to return it FIRST
with no fallback, so every per-feature PDF could fail. These tests pin the fix with a fake
broken first candidate (simulated, and — where a real browser exists — a real one)."""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from p6_export import pdf as P  # noqa: E402

SXS = OSError(14001, 'The application has failed to start because its side-by-side '
                     'configuration is incorrect')


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setattr(P, '_WORKING', None)         # monkeypatch restores the session cache
    monkeypatch.setattr(P, '_BROKEN', set())


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as fh:
        fh.write(b'')
    return path


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A fake Windows machine: Chrome, Edge, Playwright headless shell + full Chromium."""
    pf, pf86, local = (str(tmp_path / n) for n in ('pf', 'pf86', 'local'))
    m = {
        'chrome': _touch(os.path.join(pf, 'Google', 'Chrome', 'Application', 'chrome.exe')),
        'edge': _touch(os.path.join(pf86, 'Microsoft', 'Edge', 'Application', 'msedge.exe')),
        'shell': _touch(os.path.join(local, 'ms-playwright', 'chromium_headless_shell-1234',
                                     'chrome-headless-shell-win64', 'chrome-headless-shell.exe')),
        'pw': _touch(os.path.join(local, 'ms-playwright', 'chromium-1234', 'chrome-win64',
                                  'chrome.exe')),
    }
    monkeypatch.setenv('ProgramFiles', pf)
    monkeypatch.setenv('ProgramFiles(x86)', pf86)
    monkeypatch.setenv('LOCALAPPDATA', local)
    monkeypatch.delenv('PLAYWRIGHT_BROWSERS_PATH', raising=False)
    monkeypatch.setattr(P, '_app_paths', lambda name: [])
    monkeypatch.setattr(P, '_on_path', lambda: [])
    return m


@pytest.fixture
def browsers(monkeypatch):
    """Fake subprocess.run: ``behaviour[exe]`` = ok | sxs | fail | silent | hang.
    'ok' writes the --print-to-pdf / --screenshot target like a real browser."""
    state = {'behaviour': {}, 'calls': []}

    def run(cmd, **kw):
        exe = cmd[0]
        state['calls'].append(exe)
        b = state['behaviour'].get(exe, 'ok')
        if b == 'sxs':
            raise SXS
        if b == 'fail':
            raise subprocess.CalledProcessError(1, cmd)
        if b == 'hang':
            raise subprocess.TimeoutExpired(cmd, kw.get('timeout'))
        if b == 'ok':
            for a in cmd:
                for flag in ('--print-to-pdf=', '--screenshot='):
                    if a.startswith(flag):
                        with open(a[len(flag):], 'wb') as fh:
                            fh.write(b'%PDF-1.4 fake')
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(P.subprocess, 'run', run)
    return state


def test_candidate_order_prefers_installed_chrome_then_edge_then_headless_shell(machine):
    assert P.chrome_candidates() == [machine['chrome'], machine['edge'], machine['shell'],
                                     machine['pw']]
    # an explicit pick leads; missing paths are dropped
    assert P.chrome_candidates(machine['pw'])[0] == machine['pw']
    assert 'C:/nope/chrome.exe' not in P.chrome_candidates('C:/nope/chrome.exe')


def test_probe_once_and_cache_the_first_that_prints(machine, browsers):
    assert P.find_working_chrome() == machine['chrome']
    assert P.find_working_chrome() == machine['chrome']
    assert browsers['calls'] == [machine['chrome']]           # probed ONCE, then cached


def test_broken_first_candidate_is_skipped_by_the_probe(machine, browsers):
    browsers['behaviour'] = {machine['chrome']: 'sxs', machine['edge']: 'fail'}
    assert P.find_working_chrome() == machine['shell']
    assert machine['chrome'] in P._BROKEN                     # cannot start → never retried
    assert machine['edge'] not in P._BROKEN                   # a failed run may be transient
    browsers['calls'].clear()
    assert P.find_working_chrome() == machine['shell'] and browsers['calls'] == []


def test_owner_pc_playwright_chromium_first_falls_back_and_prints(machine, browsers, tmp_path):
    """The exact field failure: the old finder handed the Playwright Chromium to the route;
    it cannot start (side-by-side). The print must still land, on the next browser."""
    browsers['behaviour'] = {machine['pw']: 'sxs'}
    out = str(tmp_path / 'report.pdf')
    used = P.run_chrome(machine['pw'], [f'--print-to-pdf={out}', 'file:///x.html'])
    assert used == machine['chrome'] and os.path.getsize(out) > 0
    assert machine['pw'] in P._BROKEN and P._WORKING == machine['chrome']
    browsers['calls'].clear()
    P.run_chrome(machine['pw'], [f'--print-to-pdf={out}', 'file:///x.html'])
    assert browsers['calls'] == [machine['chrome']]          # the broken one is not re-tried


def test_run_chrome_skips_a_browser_that_exits_ok_but_writes_nothing(machine, browsers, tmp_path):
    browsers['behaviour'] = {machine['chrome']: 'silent', machine['edge']: 'fail'}
    out = str(tmp_path / 'r.pdf')
    assert P.run_chrome(machine['chrome'], [f'--print-to-pdf={out}', 'file:///x']) == machine['shell']
    assert os.path.getsize(out) > 0


def test_an_existing_output_file_is_not_mistaken_for_a_fresh_print(machine, browsers, tmp_path):
    out = tmp_path / 'r.pdf'
    out.write_bytes(b'%PDF old export')
    browsers['behaviour'] = {machine['chrome']: 'silent'}
    assert P.run_chrome(machine['chrome'], [f'--print-to-pdf={out}', 'file:///x']) == machine['edge']


def test_an_output_file_open_in_another_program_is_a_clear_message(machine, browsers, tmp_path,
                                                                   monkeypatch):
    out = tmp_path / 'r.pdf'
    out.write_bytes(b'%PDF old export')

    def locked(path):
        raise PermissionError(13, 'The process cannot access the file', str(path))
    monkeypatch.setattr(P.os, 'remove', locked)
    with pytest.raises(RuntimeError, match='open in another program'):
        P.run_chrome(machine['chrome'], [f'--print-to-pdf={out}', 'file:///x'])
    assert browsers['calls'] == []


def test_timeout_is_a_clear_error_not_a_retry_on_every_browser(machine, browsers, tmp_path):
    browsers['behaviour'] = {machine['chrome']: 'hang'}
    with pytest.raises(RuntimeError, match='did not finish printing within 5 s'):
        P.run_chrome(machine['chrome'], [f'--print-to-pdf={tmp_path / "r.pdf"}', 'file:///x'],
                     timeout=5)
    assert browsers['calls'] == [machine['chrome']]


def test_no_working_browser_is_a_clear_error(machine, browsers, tmp_path):
    browsers['behaviour'] = {e: 'sxs' for e in machine.values()}
    assert P.find_working_chrome() is None
    with pytest.raises(RuntimeError, match='No working Chrome, Edge or Chromium'):
        P.run_chrome(None, [f'--print-to-pdf={tmp_path / "r.pdf"}', 'file:///x'])


def test_base_flags_and_profile_are_added_unless_the_caller_sets_them(machine, browsers, tmp_path):
    seen = []
    real = P.subprocess.run

    def spy(cmd, **kw):
        seen.append(cmd)
        return real(cmd, **kw)
    P.subprocess.run = spy
    try:
        P.run_chrome(machine['chrome'], ['--headless=new', f'--screenshot={tmp_path / "s.png"}',
                                         'file:///x'])
        P.run_chrome(machine['chrome'], ['--user-data-dir=C:/mine',
                                         f'--print-to-pdf={tmp_path / "p.pdf"}', 'file:///x'])
    finally:
        P.subprocess.run = real
    shot, pdf = seen
    assert '--headless' not in shot and '--headless=new' in shot
    assert '--disable-gpu' in shot and '--no-sandbox' in shot
    assert sum(a.startswith('--user-data-dir=') for a in shot) == 1
    assert [a for a in pdf if a.startswith('--user-data-dir=')] == ['--user-data-dir=C:/mine']


def test_a_vanished_cached_browser_is_re_probed(machine, browsers):
    assert P.find_working_chrome() == machine['chrome']
    os.remove(machine['chrome'])
    assert P.find_working_chrome() == machine['edge']


def test_server_find_chrome_uses_the_probed_cache(machine, browsers):
    import server
    browsers['behaviour'] = {machine['chrome']: 'sxs'}
    assert server._find_chrome() == machine['edge']
    browsers['behaviour'] = {e: 'sxs' for e in machine.values()}
    P.reset_chrome_cache()
    with pytest.raises(RuntimeError, match='Install Google Chrome or Microsoft Edge'):
        server._find_chrome()


def test_cli_script_uses_the_probed_browser_not_playwright_first(machine, browsers, monkeypatch):
    """[startup:F3] PDF-1: generate_report.py (the terminal report) asked Playwright for its
    full Chromium FIRST (spawning its Node driver) — the binary that cannot start on the
    owner's PC. It now takes the probed browser and only asks Playwright when none works."""
    import types
    import generate_report
    asked = []
    fake = types.ModuleType('playwright.sync_api')

    def _driver():
        asked.append(1)
        raise RuntimeError('Playwright driver must not be started when a browser works')
    fake.sync_playwright = _driver
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', fake)
    browsers['behaviour'] = {machine['chrome']: 'sxs'}
    assert generate_report.find_chrome() == machine['edge']
    assert asked == []


def test_every_pdf_print_in_the_code_goes_through_the_one_helper():
    """No module may spawn Chrome itself: the only subprocess call with --print-to-pdf /
    --screenshot is p6_export/pdf.py (where the fallback + cache live)."""
    root = os.path.join(os.path.dirname(__file__), '..')
    offenders = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(('.', '_')) and d not in
                   ('tests', 'mockups', 'build', 'dist', 'node_modules', 'scripts')]
        for f in files:
            if not f.endswith('.py'):
                continue
            path = os.path.join(dirpath, f)
            if os.path.normpath(path) == os.path.normpath(P.__file__):
                continue
            with open(path, encoding='utf-8', errors='replace') as fh:
                src = fh.read()
            if 'subprocess' in src and "'--headless" in src:
                offenders.append(os.path.relpath(path, root))
    assert offenders == []


# ── a REAL route with a REAL broken first candidate (needs a browser on this machine) ──

def _real_browser():
    for exe in P.chrome_candidates():
        if 'ms-playwright' not in exe and P.probe_chrome(exe):
            return exe
    return None


def _consultant_report():
    return {'baseline_file': 'b.xer', 'update_file': 'u.xml',
            'dashboard': {'changed_activities': 0, 'logic_changed': 0, 'duration_only': 0,
                          'finish_slip_days': None},
            'change_summary': {'items': []}, 'logic': {'rows': []}, 'durations': {'rows': []}}


def test_real_pdf_route_survives_a_broken_first_browser(test_server, tmp_path, monkeypatch):
    real = _real_browser()
    if not real:
        pytest.skip('no working Chrome/Edge on this machine')
    import json
    import http.client
    import pymupdf
    P.reset_chrome_cache()
    broken = tmp_path / 'broken' / 'chrome.exe'           # a file Windows cannot start
    broken.parent.mkdir()
    broken.write_bytes(b'this is not a program')
    orig = P._installed_paths
    monkeypatch.setattr(P, '_installed_paths', lambda: [str(broken), *orig()])
    out = str(tmp_path / 'consultant.pdf')
    conn = http.client.HTTPConnection('127.0.0.1', test_server, timeout=120)
    conn.request('POST', '/api/compare/report',
                 body=json.dumps({'report': _consultant_report(), 'impact': None,
                                  'output_path': out}),
                 headers={'Content-Type': 'application/json'})
    data = json.loads(conn.getresponse().read())
    assert data['ok'] is True, data
    assert str(broken) in P._BROKEN and P._WORKING and P._WORKING != str(broken)
    doc = pymupdf.open(out)
    assert doc.page_count >= 1
    doc.close()


def test_real_side_by_side_playwright_chromium_falls_back(tmp_path):
    """Only where the known-broken Playwright Chromium exists (the owner's PC)."""
    local = os.environ.get('LOCALAPPDATA') or ''
    import glob
    pw = sorted(glob.glob(os.path.join(local, 'ms-playwright', 'chromium-*', 'chrome-win*',
                                       'chrome.exe')))
    if not pw:
        pytest.skip('no Playwright Chromium here')
    try:
        subprocess.run([pw[-1], '--version'], capture_output=True, timeout=30)
        pytest.skip('this Playwright Chromium starts fine here — nothing to fall back from')
    except OSError:
        pass
    if not _real_browser():
        pytest.skip('no working Chrome/Edge on this machine')
    html = tmp_path / 'r.html'
    html.write_text('<!DOCTYPE html><meta charset="utf-8"><p>Fallback works</p>', encoding='utf-8')
    out = tmp_path / 'r.pdf'
    used = P.print_html_file(str(html), str(out), chrome=pw[-1], timeout=120)
    assert used != pw[-1] and pw[-1] in P._BROKEN and out.stat().st_size > 0
