"""[startup:F6] The start-up screens tell the truth and carry the name from one place.

* VER-2: index.html never hardcodes the product name — server.py fills every
  data-brand="name|edition|title" element from utils.APP_* before sending the page, so the
  menu bar, account block, landing page and <title> paint with it (an edition bump is one
  edit to utils.APP_EDITION).
* BLACK-9: the start-up cover says the REAL current step from the first paint
  ("Starting local server" until /api/health answers, then "Loading program files"), and
  the animated splash (ui/modules/boot.js) follows the real steps: its bar is held on a
  step still running and it only says 'Ready' once every step happened. Browser checks run
  the real server + index.html in headless Chromium (skipped without Playwright).
"""
import re
import time
import urllib.request

import pytest

import server
import utils


def _index(port):
    with urllib.request.urlopen(f'http://localhost:{port}/') as r:
        return r.read().decode('utf-8')


def test_served_index_fills_every_brand_span_from_utils(test_server):
    html = _index(test_server)
    t, n = re.escape(utils.APP_TITLE), re.escape(utils.APP_NAME)
    assert re.search(rf'<title data-brand="title">{t}</title>', html)
    assert re.search(rf'id="app-title" data-brand="title">{t}</span>', html)
    assert re.search(rf'<b id="acct-name">Planner</b><span data-brand="title">{t}</span>', html)
    assert re.search(rf'<span data-brand="name">{n}</span> reads a Primavera P6 file', html)
    assert not re.search(r'data-brand="\w+"></', html), 'no brand span left empty'


def test_index_file_itself_has_no_product_name():
    with open(utils.resource_path('ui/index.html'), encoding='utf-8') as f:
        assert 'controlyx' not in f.read().lower()


def test_brand_fill_follows_the_constants_and_escapes(monkeypatch):
    monkeypatch.setattr(server, 'APP_NAME', 'Brandly')
    monkeypatch.setattr(server, 'APP_EDITION', '2031')
    monkeypatch.setattr(server, 'APP_TITLE', 'Brandly <2031>')
    html = ('<title data-brand="title"></title><span class="a" data-brand="name">old</span>'
            '<i data-brand="edition"></i><span data-other="name">keep</span>')
    out = server._fill_brand(html)
    assert out == ('<title data-brand="title">Brandly &lt;2031&gt;</title>'
                   '<span class="a" data-brand="name">Brandly</span>'
                   '<i data-brand="edition">2031</i><span data-other="name">keep</span>')


def test_brand_is_filled_before_scripts_are_inlined():
    """Inlined scripts / saved preferences are never rewritten by the brand fill."""
    import inspect
    src = inspect.getsource(server.Handler._serve_index)
    assert src.index('_fill_brand(html)') < src.index('_inline_ui_prefs(html)')
    assert src.index('_fill_brand(html)') < src.index('_inline_startup_guard(html)')


def test_served_cover_names_the_first_real_step(test_server):
    html = _index(test_server)
    assert '<span id="cx-cover-stage">Starting local server…</span>' in html
    assert 'Starting…</div>' not in html


# ── browser checks ───────────────────────────────────────────────────────────
sync_api = None


@pytest.fixture
def browser():
    global sync_api
    sync_api = pytest.importorskip('playwright.sync_api')
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as exc:                          # no bundled Chromium here
            pytest.skip('Playwright Chromium unavailable: %s' % exc)
        try:
            yield b
        finally:
            b.close()


# Samples the start-up screens every 40 ms from the first script on: what the cover and
# the splash say, the bar, and which steps the guard says really happened.
SAMPLER = '''(() => {
  window.__samples = [];
  const t0 = performance.now();
  const tick = () => {
    const g = window.__cxStartup, b = document.getElementById('boot');
    const cov = document.getElementById('cx-cover-stage');
    window.__samples.push({
      ms: Math.round(performance.now() - t0),
      cover: cov && document.getElementById('brand-splash') ? cov.textContent : null,
      capt: b ? (b.querySelector('.capt') || {}).textContent : null,
      pct: b ? parseInt((b.querySelector('.pct') || {}).textContent, 10) : null,
      gone: b ? b.classList.contains('gone') : null,
      steps: g ? Object.assign({}, g.steps) : null, phase: g ? g.phase : null });
    if (window.__samples.length < 900) setTimeout(tick, 40);
  };
  tick();
})();'''

ORDER = ['server', 'program', 'screen', 'history']


def _done(steps):
    n = 0
    while n < len(ORDER) and steps and steps.get(ORDER[n]):
        n += 1
    return n


def _check_honest(samples):
    """Every splash frame: bar within the steps really done; 'Ready' only when all are."""
    shown = [s for s in samples if s['capt'] is not None]
    assert shown, 'the splash played'
    for s in shown:
        d = _done(s['steps'])
        assert s['pct'] <= 25 * d, s
        if s['capt'] == 'Ready':
            assert d == 4, s
    return shown


def test_splash_holds_on_project_history_until_it_answers(test_server, browser, monkeypatch):
    orig = server.Handler._handle_history

    def slow(self):
        time.sleep(9)                    # the history call outlasts ~3/4 of the presentation
        return orig(self)
    monkeypatch.setattr(server.Handler, '_handle_history', slow)
    ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
    page = ctx.new_page()
    page.add_init_script(SAMPLER)
    try:
        page.goto(f'http://localhost:{test_server}/', wait_until='commit')
        page.wait_for_function('document.getElementById("boot") === null && '
                               'window.__cxStartup && window.__cxStartup.steps.history',
                               timeout=30000)
        samples = page.evaluate('window.__samples')
    finally:
        ctx.close()
    shown = _check_honest(samples)
    held = [s for s in shown if s['capt'] == 'Opening project history' and s['pct'] == 75
            and not s['steps']['history']]
    assert len(held) >= 5, 'held on the real step while the history call ran'
    assert shown[-1]['capt'] == 'Ready' and shown[-1]['pct'] == 100
    ready_at = next(s['ms'] for s in shown if s['capt'] == 'Ready')
    history_at = next(s['ms'] for s in samples if s['steps'] and s['steps']['history'])
    assert ready_at >= history_at


def test_cover_says_the_real_step_while_the_program_loads(test_server, browser):
    ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
    page = ctx.new_page()
    page.add_init_script(SAMPLER)

    def slow_module(route):
        time.sleep(2.5)                  # a program file held up (antivirus scan)
        route.continue_()
    ctx.route('**/ui/modules/tooltip.js', slow_module)
    try:
        page.goto(f'http://localhost:{test_server}/', wait_until='commit')
        page.wait_for_function('window.__cxStartup && window.__cxStartup.phase === "ready"',
                               timeout=30000)
        page.wait_for_timeout(1500)
        samples = page.evaluate('window.__samples')
        shot = page.screenshot()
    finally:
        ctx.close()
    covers = [s for s in samples if s['cover']]
    assert covers, 'the cover was painted with a step'
    # it named the server step only until the health handshake answered, then program files
    assert all(s['cover'] == 'Starting local server…' for s in covers if not s['steps']['server'])
    loading = [s for s in covers if s['steps']['server'] and not s['steps']['program']]
    assert len(loading) >= 10, 'program files still loading after the server answered'
    assert all(s['cover'] == 'Loading program files…' for s in loading)
    assert covers[-1]['ms'] < next(s['ms'] for s in samples if s['capt'] is not None) + 100
    _check_honest(samples)
    assert shot
