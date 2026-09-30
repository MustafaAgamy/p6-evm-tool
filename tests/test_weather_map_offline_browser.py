"""[startup:F5] NET-3 browser check (real server + real UI in headless Chromium, no internet):
Bad Weather ▸ location map.

  * the OpenStreetMap tile server unreachable from the start → a plain note over the map
    (not a silent grey box);
  * tiles come back → the note clears; the connection drops AGAIN after the map has drawn and
    the planner zooms/pans somewhere new → the note returns (the old check only fired when no
    tile had ever loaded);
  * clicking the map's 'Leaflet' attribution link never navigates the app window away — it is
    handed to the desktop bridge (Api.open_external, faked here) for the default browser.

Tiles are served by a Playwright route (a 1-px PNG when "online", an aborted request when
"offline"), so nothing leaves the machine. Skipped without Playwright.
"""
import base64
import http.client
import json
import threading

import pytest

import db

sync_api = pytest.importorskip('playwright.sync_api')

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==')


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
def served(tmp_path, monkeypatch, xml_path):
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    monkeypatch.setattr(db, 'schedules_dir', lambda: str(tmp_path / 'schedules'))
    (tmp_path / 'schedules').mkdir()
    import server as srv
    httpd = srv.make_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=120)
    conn.request('POST', '/api/parse', body=json.dumps({'path': str(xml_path)}).encode(),
                 headers={'Content-Type': 'application/json'})
    parsed = json.loads(conn.getresponse().read())
    assert parsed.get('ok'), parsed
    pid = db.get_project_id_for_snapshot(parsed['snapshot_id'])
    try:
        yield port, pid, tmp_path
    finally:
        httpd.shutdown()
        httpd.server_close()


def _click(page, sel):
    page.wait_for_selector(sel, state='attached', timeout=30000)
    page.eval_on_selector(sel, 'e => e.click()')


def _zoom_in(page, times=1):
    for _ in range(times):
        page.eval_on_selector('#cal-map .leaflet-control-zoom-in', 'b => b.click()')
        page.wait_for_timeout(700)


def test_map_says_offline_and_attribution_never_leaves_the_app(served, browser):
    port, pid, tmp = served
    online = {'tiles': False}

    def tiles(route):
        if online['tiles']:
            route.fulfill(status=200, content_type='image/png', body=PNG)
        else:
            route.abort('internetdisconnected')

    ctx = browser.new_context(viewport={'width': 1400, 'height': 950})
    ctx.route('**://tile.openstreetmap.org/**', tiles)
    ctx.route('**://www.openstreetmap.org/**', lambda r: r.abort())   # (later routes win in Playwright)
    ctx.route('**://leafletjs.com/**', lambda r: r.abort())
    ctx.add_init_script(
        "window.__opened = []; window.pywebview = { api: { open_external: (u) => "
        "{ window.__opened.push(u); return Promise.resolve(true); } } };")
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(f'http://localhost:{port}/', wait_until='domcontentloaded')
    page.wait_for_function('window.__cxStartup && window.__cxStartup.phase === "ready"', timeout=30000)
    _click(page, '.tnode[data-nav="recent"]')
    _click(page, f'.open-btn[data-project-id="{pid}"]')
    page.wait_for_timeout(1500)
    _click(page, '.tnode[data-nav="weather"]')
    page.wait_for_selector('#cal-map.leaflet-container', timeout=30000)

    # 1. Offline from the start → a plain note over the map.
    page.wait_for_selector('#cal-map .cal-map-offline', timeout=20000)
    note = page.inner_text('#cal-map .cal-map-offline')
    assert 'need an internet connection' in note and 'coordinates' in note
    page.screenshot(path=str(tmp / 'map_offline.png'))

    # 2. Tiles come back → the note clears …
    online['tiles'] = True
    _zoom_in(page)
    page.wait_for_selector('#cal-map .cal-map-offline', state='detached', timeout=10000)
    # … and the connection drops again after the map drew → the note returns.
    online['tiles'] = False
    _zoom_in(page, 2)
    page.wait_for_selector('#cal-map .cal-map-offline', timeout=10000)

    # 3. The 'Leaflet' attribution link goes to the default browser, the app stays put.
    before = page.url
    hrefs = page.eval_on_selector_all('#cal-map .leaflet-control-attribution a', 'as => as.map(a => a.href)')
    assert 'https://leafletjs.com/' in hrefs
    page.click('#cal-map .leaflet-control-attribution a[href*="leafletjs"]')
    page.wait_for_function('window.__opened.length > 0', timeout=5000)
    page.wait_for_timeout(500)
    assert page.url == before, 'the app window must never navigate to an outside site'
    assert page.evaluate('window.__opened') == ['https://leafletjs.com/']
    assert page.is_visible('#cal-map'), 'the Bad Weather screen is still showing'
    assert not errors, errors
    ctx.close()
