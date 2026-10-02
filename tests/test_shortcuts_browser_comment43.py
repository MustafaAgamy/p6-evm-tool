"""Comment 43 — every shortcut works, every feature has one, and it works in every feature.

The real server + the real page in headless Chromium, with a schedule imported by Ctrl+O (the
desktop file / save dialogs answered by a stand-in).  Every Alt / Alt+Shift jump opens its
feature, and the shortcuts that the 2 Oct key-by-key check found silent or wrong now act:

* Ctrl+E on Overview, WBS and Earned Value saved nothing ("This view exports to PDF" / "Run this
  module's analysis first") — their Excel button had moved into the preview.  Now: the view's own
  workbook, or the preview with its ⬇ Excel pressed.
* Ctrl+Shift+W / H on the Knowledge Base opened the preview and saved nothing.
* Ctrl+R / Ctrl+↵ on a Consultant Review result said "use the feature's own Run button".
* Ctrl+↵ on Bad Weather said "assign input files" — it needs a location.

Skipped when Playwright's Chromium is not available.
"""
import json
import os

import pytest

sync_api = pytest.importorskip('playwright.sync_api')

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'minimal.xml')
JUMPS = [('Alt+1', 'overview'), ('Alt+2', 'wbs'), ('Alt+3', 'schedule'), ('Alt+4', 'audit'), ('Alt+5', 'narrative'),
         ('Alt+6', 'lag'), ('Alt+7', 'evm'), ('Alt+8', 'oos'), ('Alt+9', 'update'), ('Alt+0', 'critpath'),
         ('Alt+Shift+Digit1', 'period'), ('Alt+Shift+Digit2', 'compare'), ('Alt+Shift+Digit3', 'revcompare'),
         ('Alt+Shift+Digit4', 'calendar'), ('Alt+Shift+Digit5', 'weather'), ('Alt+Shift+Digit6', 'special'),
         ('Alt+Shift+Digit7', 'prodintel'), ('Alt+Shift+Digit9', 'chat')]
MOCK = """
window.__calls = [];
window.pywebview = { api: {
  choose_file: async () => { window.__calls.push(['choose_file']); return %s; },
  choose_excel: async () => null, choose_open_path: async () => null,
  choose_save_path: async (name, type) => { window.__calls.push(['save', type]); return %s + '/' + Date.now() + '_' + name; },
  open_external: async () => true, open_log_folder: async () => true, quit: async () => true } };
"""


@pytest.fixture
def page(test_server, tmp_path):
    with sync_api.sync_playwright() as p:
        args = ['--host-resolver-rules=MAP localhost 127.0.0.1']      # the page calls http://localhost
        b = None
        for kw in ({}, {'executable_path': '/opt/pw-browsers/chromium'}):
            try:
                b = p.chromium.launch(headless=True, args=args, **kw)
                break
            except Exception:
                continue
        if b is None:
            pytest.skip('Playwright Chromium unavailable')
        pg = b.new_page(viewport={'width': 1500, 'height': 950})
        pg.add_init_script(MOCK % (json.dumps(FIXTURE), json.dumps(str(tmp_path))))
        reqs = []
        pg.on('request', lambda r: reqs.append(r.url) if '/api/' in r.url else None)
        pg.goto(f'http://localhost:{test_server}/')
        pg.wait_for_timeout(2500)
        pg.reqs = reqs
        try:
            yield pg
        finally:
            b.close()


def _state(pg):
    return pg.evaluate("""async () => { const m = await import('/ui/modules/state.js');
      const e = document.getElementById('error-banner');
      return { view: m.state.currentView, result: !!m.state.currentResult,
               error: e && !e.classList.contains('hidden') ? document.getElementById('error-text').textContent : '',
               calls: window.__calls.slice() }; }""")


def _press(pg, key, wait=2500):
    pg.evaluate("() => { window.__calls = []; document.getElementById('error-banner').classList.add('hidden'); }")
    n = len(pg.reqs)
    pg.keyboard.press(key)
    pg.wait_for_timeout(wait)
    pg.wait_for_load_state('networkidle')
    st = _state(pg)
    st['reqs'] = [u.split('/api/', 1)[1] for u in pg.reqs[n:]]
    return st


def _close_preview(pg):
    pg.keyboard.press('Escape')
    pg.evaluate("() => { document.querySelectorAll('.rpv-overlay').forEach(o => o.remove()); document.body.focus(); }")


def test_every_feature_has_a_jump_and_the_fixed_shortcuts_act(page):
    st = _press(page, 'Control+o', 5000)
    assert st['result'] and ['choose_file'] in st['calls']
    for key, view in JUMPS:                                          # one shortcut per feature, each opens it
        assert _press(page, key, 1200)['view'] == view, key
        _close_preview(page)

    for key, view, route in (('Alt+1', 'overview', 'overview/excel'), ('Alt+2', 'wbs', 'wbs/excel'),
                             ('Alt+7', 'evm', 'export/xlsx')):
        _press(page, key, 1500)
        _press(page, 'Control+Enter', 1500)                        # run it (the feature gate) first
        st = _press(page, 'Control+e', 8000)
        assert ['save', 'xlsx'] in st['calls'], (view, st)
        assert any(r.startswith(route) for r in st['reqs']), (view, st['reqs'])
        assert not st['error'], (view, st['error'])
        _close_preview(page)

    st = _press(page, 'Alt+Shift+Digit5', 1500)
    st = _press(page, 'Control+Enter', 1500)
    assert 'location' in st['error'], st                             # Bad Weather needs a location, not files

    _press(page, 'Alt+Shift+Digit2', 1500)                          # Consultant Review: file, run, run again
    page.evaluate("() => document.getElementById('cmp-choose-baseline').click()")
    page.wait_for_timeout(2000)
    assert any(r.startswith('compare') for r in _press(page, 'Control+Enter', 5000)['reqs'])
    st = _press(page, 'Control+r', 5000)
    assert any(r.startswith('compare') for r in st['reqs']) and 'own Run button' not in st['error'], st

    _press(page, 'Alt+Shift+Digit8', 3000)                          # Knowledge Base: Word / HTML save
    for key, kind in (('Control+Shift+W', 'docx'), ('Control+Shift+H', 'html')):
        st = _press(page, key, 8000)
        assert ['save', kind] in st['calls'] and any(r.startswith('export/' + kind) for r in st['reqs']), (kind, st)
        _close_preview(page)
