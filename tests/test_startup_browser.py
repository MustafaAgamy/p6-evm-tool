"""[startup:F1] Browser check of the black-screen fixes (the real server + real index.html in
headless Chromium, a fresh context per scenario like the app's private WebView2).

* BLACK-1: a program file that never loads -> automatic reloads, then a visible
  "couldn't finish starting" card with Retry (never a silent black cover); Retry recovers.
* BLACK-2: index.html locked for a moment (antivirus) -> a visible self-retrying
  "Starting" page that recovers by itself.
* A failing first /api/history call -> Recent Projects says so with a Retry button, and
  Retry loads it.

Skipped when Playwright or its Chromium is not installed (CI only builds the exe).
"""
import builtins
import os

import pytest

sync_api = pytest.importorskip('playwright.sync_api')

PROBE = '''() => ({
  splash: !!document.getElementById('brand-splash'),
  nav: document.querySelectorAll('#nav-tree .tnode').length,
  phase: window.__cxStartup ? window.__cxStartup.phase : null,
  card: (document.getElementById('cx-startup') || {}).innerText || ''})'''


@pytest.fixture
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as exc:                          # no bundled Chromium here
            pytest.skip('Playwright Chromium unavailable: %s' % exc)
        try:
            yield b
        finally:
            b.close()


def _page(browser):
    ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
    return ctx, ctx.new_page()


def _ready(page, timeout=20000):
    page.wait_for_function('window.__cxStartup && window.__cxStartup.phase === "ready"',
                           timeout=timeout)
    return page.evaluate(PROBE)


def test_a_module_that_never_loads_shows_retry_and_recovers(test_server, browser):
    ctx, page = _page(browser)
    blocked = {'on': True}
    ctx.route('**/ui/modules/tooltip.js',
              lambda rt: rt.abort('connectionrefused') if blocked['on'] else rt.continue_())
    try:
        page.goto(f'http://localhost:{test_server}/', wait_until='domcontentloaded')
        page.wait_for_selector('#cx-startup-retry', timeout=25000)   # after 3 auto reloads
        st = page.evaluate(PROBE)
        assert st['phase'] == 'failed' and 'couldn’t finish starting' in st['card']
        assert st['nav'] == 0                               # the shell never ran ...
        assert page.is_visible('#cx-startup-retry')         # ... but the window says so
        blocked['on'] = False                               # the file is readable again
        page.click('#cx-startup-retry')
        st = _ready(page)
        assert st['nav'] > 0 and not st['splash'] and not st['card']
    finally:
        ctx.close()


def test_a_locked_index_page_retries_by_itself(test_server, browser, monkeypatch):
    real_open = builtins.open
    left = {'n': 5}                   # 4 in-server retries fail the first request

    def locked_once(path, *a, **k):
        if str(path).replace('\\', '/').endswith('ui/index.html') and left['n'] > 0:
            left['n'] -= 1
            raise PermissionError(13, 'being used by another process')
        return real_open(path, *a, **k)
    monkeypatch.setattr(builtins, 'open', locked_once)
    ctx, page = _page(browser)
    statuses = []
    page.on('response', lambda r: statuses.append(r.status)
            if r.url.rstrip('/').endswith(str(test_server)) else None)
    try:
        page.goto(f'http://localhost:{test_server}/', wait_until='domcontentloaded')
        assert 'Starting' in page.inner_text('body')        # visible, not raw JSON / black
        st = _ready(page)
        assert statuses[:2] == [503, 200] and st['nav'] > 0
    finally:
        ctx.close()


def test_a_failing_history_call_shows_retry_then_loads(test_server, browser, monkeypatch):
    import server
    orig = server.Handler._handle_history
    calls = {'n': 0}

    def flaky(self):
        calls['n'] += 1
        if calls['n'] <= 4:                                  # startup call + 3 retries
            return self._json(503, {'ok': False, 'error': 'database is locked'})
        return orig(self)
    monkeypatch.setattr(server.Handler, '_handle_history', flaky)
    ctx, page = _page(browser)
    try:
        page.goto(f'http://localhost:{test_server}/', wait_until='domcontentloaded')
        assert _ready(page)['nav'] > 0                      # the shell never waits on it
        page.wait_for_selector('#recent-retry', state='attached', timeout=15000)
        assert 'Couldn’t load recent projects' in page.evaluate(
            "document.getElementById('recent-tbody').innerText")
        page.evaluate("document.getElementById('recent-retry').click()")
        page.wait_for_function("!document.getElementById('recent-retry')", timeout=10000)
        assert calls['n'] == 5
        assert 'Couldn’t load' not in page.evaluate(
            "document.getElementById('recent-tbody').innerText")
    finally:
        ctx.close()


def test_a_damaged_history_db_says_why_and_can_be_set_aside(tmp_path, browser, monkeypatch):
    """S3: a DB whose data pages are damaged opens 'ok'; the page must say the real error
    (not just 'Couldn't load') and offer to set the damaged file aside; after the click
    Recent Projects loads from the fresh file (every readable row copied across)."""
    import gc
    import sqlite3
    import threading
    import db
    import server
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    monkeypatch.setattr(db, 'schedules_dir', lambda: str(tmp_path / 'schedules'))
    monkeypatch.setattr(db, 'BACKGROUND_CHECK_DELAY_S', 0.0)
    (tmp_path / 'schedules').mkdir()
    db.init_db()
    path = str(tmp_path / 'controlyx.db')
    conn = sqlite3.connect(path)
    conn.executemany('INSERT INTO projects (id, p6_project_id, name, created_at) VALUES (?,?,?,?)',
                     [(i, 'P%d' % i, 'Project %d %s' % (i, 'x' * 60), '2026-01-01') for i in range(1, 201)])
    conn.executemany('INSERT INTO snapshots (id, project_id, imported_at, original_path) VALUES (?,?,?,?)',
                     [(i, i, '2026-01-01T00:%02d:%02d' % (i // 60, i % 60), 'C:/x/p%d.xml' % i)
                      for i in range(1, 201)])
    conn.commit()
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    psz = conn.execute('PRAGMA page_size').fetchone()[0]
    conn.close()
    gc.collect()
    raw = bytearray(open(path, 'rb').read())
    page = raw.find(b'Project 100 ') // psz
    raw[page * psz:(page + 1) * psz] = b'\xde\xad\xbe\xef' * (psz // 4)
    open(path, 'wb').write(bytes(raw))

    httpd = server.make_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    ctx, page_ = _page(browser)
    try:
        page_.goto(f'http://localhost:{port}/', wait_until='domcontentloaded')
        assert _ready(page_)['nav'] > 0
        page_.wait_for_selector('#recent-recover', state='attached', timeout=15000)
        row = page_.evaluate("document.getElementById('recent-tbody').innerText")
        assert 'Couldn’t load recent projects' in row and 'malformed' in row   # the real error
        page_.wait_for_selector('#cx-db-notice', timeout=15000)                   # page-wide too
        assert 'damaged' in page_.inner_text('#cx-db-notice')
        page_.evaluate("document.getElementById('recent-recover').click()")
        page_.wait_for_function("!document.getElementById('recent-recover') && "
                                "document.querySelectorAll('#recent-tbody tr').length > 1",
                                timeout=15000)
        assert 'Couldn’t load' not in page_.evaluate(
            "document.getElementById('recent-tbody').innerText")
        notice = page_.inner_text('#cx-db-notice')
        assert 'corrupt-bak' in notice and 'every record that could still be read' in notice
        assert db.DB_STATUS['status'] == 'recovered'
    finally:
        ctx.close()
        httpd.shutdown()
        httpd.server_close()
