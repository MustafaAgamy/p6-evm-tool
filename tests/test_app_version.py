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


# ── One source: the version is READ from CHANGELOG.md, never typed twice ─────
# utils.APP_VERSION is derived from the newest `## [vX.Y.Z]` release heading, so a
# release only edits the changelog (the release process already starts there) and
# Help ▸ About / the Help footer / /api/health / the User-Agent follow automatically.

def _write(tmp_path, text):
    p = tmp_path / 'CHANGELOG.md'
    p.write_text(text, encoding='utf-8')
    return str(p)


def test_release_version_skips_unreleased_and_takes_newest(tmp_path):
    path = _write(tmp_path, '# Changelog\n\n## [Unreleased]\n### Added\n- wip\n\n'
                            '## [v3.1.4] - 2026-10-01\n- x\n\n## [v3.1.3] - 2026-09-01\n')
    assert utils.release_version(path) == '3.1.4'


def test_release_version_missing_or_headless_changelog_is_blank(tmp_path):
    # No invented number: the UI hides the version line when it is blank.
    assert utils.release_version(str(tmp_path / 'nope.md')) == ''
    assert utils.release_version(_write(tmp_path, '# Changelog\n\n## [Unreleased]\n')) == ''


def test_app_version_is_read_from_the_changelog_not_typed():
    src = _read('utils.py')
    assert not re.search(r"^APP_VERSION\s*=\s*['\"]\d", src, re.M), \
        'APP_VERSION must be read from CHANGELOG.md, not hardcoded'
    assert utils.APP_VERSION == utils.release_version()


def test_packaged_app_reads_the_bundled_changelog(tmp_path, monkeypatch):
    # In the one-file exe the project root is sys._MEIPASS — the changelog shipped there.
    _write(tmp_path, '## [Unreleased]\n\n## [v9.8.7] - 2027-01-01\n')
    monkeypatch.setattr(utils.sys, '_MEIPASS', str(tmp_path), raising=False)
    assert utils.release_version() == '9.8.7'


def test_spec_bundles_the_changelog():
    spec = _read('controlyx.spec')
    assert re.search(r"\(\s*'CHANGELOG\.md'\s*,\s*'\.'\s*\)", spec), \
        'controlyx.spec must ship CHANGELOG.md at the bundle root (version source)'


def test_getting_started_names_both_export_formats():
    js = _read('ui/modules/help.js')
    assert 'P6 XML or XER export' in js
    assert 'XML/XER export' not in js


# ── VER-1: a release can never ship a stale version ──────────────────────────
def test_release_workflow_checks_the_version_before_building():
    """build-release.yml runs this file and stops when the tag differs from the newest
    CHANGELOG release, BEFORE the exe is built (the exe shows utils.APP_VERSION)."""
    wf = _read('.github/workflows/build-release.yml')
    check = wf.find('python -m pytest tests/test_app_version.py')
    build = wf.find('pyinstaller controlyx.spec')
    assert check != -1, 'the release workflow must run tests/test_app_version.py'
    assert build != -1 and check < build, 'the version check must run before the exe is built'
    step = wf[wf.rfind('- name:', 0, check):build]
    # Compared with the tag the decide job chose — a pushed v* tag or, for an automatic release
    # on a push to master, the newest CHANGELOG heading (GITHUB_REF_NAME is then 'master').
    assert 'utils.APP_VERSION' in step and 'needs.decide.outputs.tag' in step and 'exit 1' in step, \
        'a tag that differs from the newest CHANGELOG release must fail the build'
