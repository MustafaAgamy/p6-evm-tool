"""[startup:F4] BLACK-8 browser check (real server + real index.html in headless Chromium):
Help ▸ Contact & Support shows the 'Open log folder' block, says where startup.log is
(from GET /api/health) and, through the desktop bridge (faked here — the real one is
app.py Api.open_log_folder), says the folder was opened. Skipped without Playwright.
"""
import os
import threading

import pytest

import db

sync_api = pytest.importorskip('playwright.sync_api')


@pytest.fixture
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip('Playwright Chromium unavailable: %s' % exc)
        try:
            yield b
        finally:
            b.close()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    import app_startup
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    monkeypatch.setattr(db, 'schedules_dir', lambda: str(tmp_path / 'schedules'))
    monkeypatch.setattr(app_startup, 'data_dir', lambda: str(tmp_path))
    (tmp_path / 'schedules').mkdir()
    return tmp_path


def test_help_open_log_folder(data_dir, browser):
    import server as srv
    httpd = srv.make_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    log_file = os.path.join(str(data_dir), 'logs', 'startup.log')
    try:
        ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
        ctx.add_init_script(
            "window.__opened = 0; window.pywebview = { api: { open_log_folder: () => "
            "{ window.__opened++; return Promise.resolve({ ok: true, path: %r }); } } };"
            % log_file.replace('\\', '/'))
        page = ctx.new_page()
        page.goto(f'http://localhost:{port}/', wait_until='domcontentloaded')
        page.wait_for_function('window.__cxStartup && window.__cxStartup.phase === "ready"',
                               timeout=30000)
        page.evaluate("async () => (await import('/ui/modules/help.js')).openHelp('contact')")
        page.wait_for_function('() => (document.getElementById("hc-log-status") || {}).textContent'
                               ' && document.getElementById("hc-log-status").textContent.startsWith("Log file:")',
                               timeout=10000)
        assert page.is_visible('#hc-log') and page.is_visible('#hc-log-open')
        assert page.inner_text('#hc-log-status') == 'Log file: ' + log_file
        assert 'startup.log' in page.inner_text('#hc-log')
        page.click('#hc-log-open')
        page.wait_for_function('() => document.getElementById("hc-log-status").textContent.startsWith("Opened.")',
                               timeout=10000)
        assert page.evaluate('window.__opened') == 1
        page.locator('#hc-log').scroll_into_view_if_needed()
        page.screenshot(path=str(data_dir / 'help_log_folder.png'))
        ctx.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
