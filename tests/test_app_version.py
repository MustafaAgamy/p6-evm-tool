"""The release version shown in the UI comes from ONE constant (utils.APP_VERSION).

Integration finding F5: the Help Center footer and About screen hardcoded
"v2.2.0" while the release was v2.8.0. The version now lives in utils.py next
to APP_NAME / APP_EDITION, is injected by server.py as window.__APP_VERSION__,
and help.js reads it — so it can never silently drift again.
"""
import os
import re
import urllib.request

import utils

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def test_app_version_matches_newest_changelog_release():
    m = re.search(r'^## \[v(\d+\.\d+\.\d+)\]', _read('CHANGELOG.md'), re.M)
    assert m, 'CHANGELOG.md has no ## [vX.Y.Z] heading'
    assert utils.APP_VERSION == m.group(1), (
        f'utils.APP_VERSION={utils.APP_VERSION!r} but newest CHANGELOG release is '
        f'v{m.group(1)} — bump APP_VERSION with the changelog')


def test_index_injects_app_version(test_server):
    html = urllib.request.urlopen(f'http://127.0.0.1:{test_server}/').read().decode()
    assert f'window.__APP_VERSION__ = "{utils.APP_VERSION}";' in html
    assert f'window.__APP_EDITION__ = "{utils.APP_EDITION}";' in html


def test_help_center_has_no_hardcoded_current_version():
    js = _read('ui/modules/help.js')
    assert 'window.__APP_VERSION__' in js
    # The About line and the navigator footer must not carry a literal version
    # or edition — only the historical "Since vX.Y.Z" What's New pill may.
    assert not re.search(r'Version \d+\.\d+\.\d+', js)
    assert not re.search(r'\d{4} Edition', js)
    assert not re.search(r'· v\d+\.\d+\.\d+', js)
    for pill in re.findall(r'hc-ver-pill">([^<]*)<', js):
        assert pill.startswith('Since v'), pill
