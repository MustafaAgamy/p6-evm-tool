"""[startup:F3] Browser check (real server + real index.html in headless Chromium, a fresh
browser context per launch = the app's private WebView2 on a new random port).

* SET-2: the Appearance mode, Report Contents picks, WBS columns, Period critical-path style
  and Lag & Lead text size set in one launch are there in the next launch — the saved
  Appearance is already on the page before any module runs (no Light flash) — and the
  Baseline Narrative project setup typed in one launch is pre-filled in the next.
* BLACK-6: Help ▸ Contact & Support 'Safe graphics' switch saves the choice the next
  launch uses, and says so on the page.

Skipped when Playwright or its Chromium is not installed (CI only builds the exe).
"""
import http.client
import json
import threading
import time

import pytest

import db

sync_api = pytest.importorskip('playwright.sync_api')

AT_PARSE = '''document.addEventListener('readystatechange', () => {
  if (document.readyState === 'interactive' && !('__apAtParse' in window)) {
    window.__apAtParse = document.documentElement.getAttribute('data-appearance');
    window.__modulesRanAtParse = !!(window.__cxStartup && window.__cxStartup.phase === 'ready');
  }
});'''

PREFS = {
    'p6_report_registry::evm': '{"kpi":true,"trend":false}',
    'p6_report_sel_calendar': '["summary","histogram"]',
    'p6evm_wbs_cols': '["code","name","planned"]',
    'per_cp_style': 'bars',
    'p6_lag_just_fs': '15',
}


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


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """One per-user data folder shared by every 'launch' in the test."""
    import app_startup
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    monkeypatch.setattr(db, 'schedules_dir', lambda: str(tmp_path / 'schedules'))
    monkeypatch.setattr(app_startup, 'data_dir', lambda: str(tmp_path))
    monkeypatch.delenv(app_startup.SAFE_GRAPHICS_ENV, raising=False)
    (tmp_path / 'schedules').mkdir()
    return tmp_path


def _launch():
    import server as srv
    httpd = srv.make_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _post(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=60)
    conn.request('POST', path, body=json.dumps(payload).encode(),
                 headers={'Content-Type': 'application/json'})
    return json.loads(conn.getresponse().read())


def _open(browser, port):
    ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
    ctx.add_init_script(AT_PARSE)
    page = ctx.new_page()
    page.goto(f'http://localhost:{port}/', wait_until='domcontentloaded')
    page.wait_for_function('window.__cxStartup && window.__cxStartup.phase === "ready"',
                           timeout=30000)
    return ctx, page


def _until(fn, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.1)
    return fn()


def _open_narrative(page, port, imported):
    page.evaluate('''async ([port, sid, xml, cached]) => {
      const { state } = await import('/ui/modules/state.js');
      state.serverPort = port; state.currentSnapshotId = sid;
      state.currentXmlPath = xml; state.currentCachedPath = cached;
      (await import('/ui/modules/narrative.js')).renderNarrativePanel();
    }''', [port, imported['snapshot_id'], imported['xml'], imported['cached_path']])
    page.wait_for_selector('#bn-chat-wrap input[data-k="location"]', state='attached',
                           timeout=30000)


def test_screen_settings_and_narrative_setup_survive_an_app_restart(data_dir, browser, xml_path):
    import ui_prefs
    first = _launch()
    port1 = first.server_address[1]
    try:
        parsed = _post(port1, '/api/parse', {'path': str(xml_path), 'overrides_path': None})
        assert parsed['ok'] is True
        imported = {'snapshot_id': parsed['snapshot_id'], 'xml': str(xml_path),
                    'cached_path': parsed.get('cached_path')}
        ctx, page = _open(browser, port1)
        assert page.evaluate('document.documentElement.getAttribute("data-appearance")') == 'light'
        page.select_option('#report-appearance', 'midnight')            # the toolbar control
        page.evaluate('''(prefs) => { for (const k in prefs) localStorage.setItem(k, prefs[k]);
                                      localStorage.setItem('gone_after_remove', '1');
                                      localStorage.removeItem('gone_after_remove'); }''', PREFS)
        _open_narrative(page, port1, imported)
        page.evaluate('''() => { const i = document.querySelector('#bn-chat-wrap input[data-k="location"]');
                                 i.value = 'Ras Al Khair, KSA'; i.dispatchEvent(new Event('input')); }''')
        want = dict(PREFS, p6_report_appearance='midnight')
        assert _until(lambda: all(ui_prefs.load(str(data_dir)).get(k) == v for k, v in want.items()))
        assert _until(lambda: (db.get_snapshot_ui_state(imported['snapshot_id'], 'narrative_setup')
                               or {}).get('location') == 'Ras Al Khair, KSA')
        ctx.close()
    finally:
        first.shutdown()
        first.server_close()

    saved = ui_prefs.load(str(data_dir))
    assert 'gone_after_remove' not in saved
    assert not any(k.startswith('bn_setup_') for k in saved)            # kept in the DB instead

    second = _launch()                                                   # the app opened again
    port2 = second.server_address[1]
    try:
        assert port2 != port1                                            # new origin, empty storage
        ctx, page = _open(browser, port2)
        assert page.evaluate('window.__apAtParse') == 'midnight'         # before any module ran
        assert page.evaluate('window.__modulesRanAtParse') is False
        assert page.evaluate('document.documentElement.getAttribute("data-appearance")') == 'midnight'
        assert page.eval_on_selector('#report-appearance', 'e => e.value') == 'midnight'
        got = page.evaluate('(keys) => Object.fromEntries(keys.map(k => [k, localStorage.getItem(k)]))',
                            list(PREFS))
        assert got == PREFS
        _open_narrative(page, port2, imported)
        page.wait_for_function('''() => { const i = document.querySelector('#bn-chat-wrap input[data-k="location"]');
                                          return i && i.value === 'Ras Al Khair, KSA'; }''', timeout=15000)
        ctx.close()
    finally:
        second.shutdown()
        second.server_close()


def test_help_safe_graphics_switch_in_the_page(data_dir, browser):
    import app_startup
    srv = _launch()
    port = srv.server_address[1]
    try:
        ctx, page = _open(browser, port)
        page.evaluate("async () => (await import('/ui/modules/help.js')).openHelp('contact')")
        page.wait_for_function('() => { const b = document.getElementById("hc-gfx-toggle"); return b && !b.disabled; }',
                               timeout=10000)
        assert page.is_visible('#hc-gfx')
        assert page.inner_text('#hc-gfx-status') == 'Off (normal graphics).'
        page.click('#hc-gfx-toggle')
        page.wait_for_function('() => document.getElementById("hc-gfx-status").textContent.startsWith("On since")',
                               timeout=10000)
        assert 'next time you open the app' in page.inner_text('#hc-gfx-status')
        assert app_startup.safe_graphics_enabled()
        env = {}
        assert app_startup.apply_graphics_mode(env) == 'safe' and '--disable-gpu' in \
            env['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS']
        page.screenshot(path=str(data_dir / 'help_safe_graphics.png'))
        page.click('#hc-gfx-toggle')
        page.wait_for_function('() => document.getElementById("hc-gfx-status").textContent.startsWith("Off")',
                               timeout=10000)
        assert not app_startup.safe_graphics_enabled()
        ctx.close()
    finally:
        srv.shutdown()
        srv.server_close()
