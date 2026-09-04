"""Guard the Recent Projects relocation (Decision 010, binding standard).

The Recent Projects list must live on its OWN sidebar page and never trail the
content flow of Home or any module report. These checks lock that in so a future
edit can't silently re-drop the recent list under a feature again.
"""
import os
import re

UI = os.path.join(os.path.dirname(__file__), '..', 'ui')


def _read(*parts):
    return open(os.path.join(UI, *parts), encoding='utf-8').read()


INDEX = _read('index.html')
APP = _read('app.js')
RECENT = _read('modules', 'recent.js')
DATABASE = _read('modules', 'database.js')


def _section_class():
    m = re.search(r'<section[^>]*class="([^"]*recent-section[^"]*)"', INDEX)
    return m.group(1) if m else None


def test_recent_section_hidden_by_default():
    cls = _section_class()
    assert cls is not None, 'no <section class="recent-section"> in index.html'
    assert 'hidden' in cls.split(), f'recent-section must start hidden, got class="{cls}"'


def test_recent_section_has_id():
    assert re.search(r'<section[^>]*id="recent-section"', INDEX), \
        'recent-section needs id="recent-section" for its page toggle'


def test_navigator_has_recent_entry():
    # The 2026 shell reaches Recent Projects from the Project Navigator (Library
    # group), not a dedicated sidebar button.
    assert re.search(r"\['recent'\s*,\s*'Recent Projects'", APP), \
        'navigator NAV must carry a Recent Projects entry'


def test_recent_module_exports_page_toggles():
    assert re.search(r'export function showRecent\b', RECENT), 'recent.js must export showRecent()'
    assert re.search(r'export function exitRecent\b', RECENT), 'recent.js must export exitRecent()'


def test_app_wires_recent_navigation():
    assert "id === 'recent'" in APP, 'navigator must route the recent node to showRecent'
    assert 'showRecent' in APP and 'exitRecent' in APP, 'app.js must use showRecent/exitRecent'


# ── binding-standard regression guards ────────────────────────────────────────
# Home (and the Database exit path) must NOT re-show the recent list. If the exit
# function re-reveals .recent-section, the list would trail Home again.

def _reshows_recent(js):
    return re.search(r"recent-section'\)\??\.classList\.remove\('hidden'\)", js)


def test_database_exit_does_not_reshow_recent():
    assert not _reshows_recent(DATABASE), \
        'exitDatabase re-shows .recent-section — it must not (recent lives on its own page)'
