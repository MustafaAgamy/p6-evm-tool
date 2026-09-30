"""The release version shown in the UI comes from ONE constant (utils.APP_VERSION).

Integration finding F5: the Help Center footer and About screen hardcoded
"v2.2.0" while the release was v2.8.0. The version now lives in utils.py next
to APP_NAME / APP_EDITION, is injected by server.py as window.__APP_VERSION__,
and help.js reads it — so it can never silently drift again.
"""
import glob
import json
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
    # About, the navigator footer and What's New build every version from APP_VERSION:
    # no literal version, edition or "Since vX.Y.Z" badge (c25: What's New said v2.2.0).
    assert not re.search(r'Version \d+\.\d+\.\d+', js)
    assert not re.search(r'\d{4} Edition', js)
    assert not re.search(r'· v\d+\.\d+\.\d+', js)
    assert 'hc-ver-pill' not in js, "What's New carries no hand-typed version badge"
    assert 'window.__APP_RELEASE_NOTES__' in js, "What's New is read from the changelog"


# ── [accept:c25:r1] No literal release version anywhere the user can see ─────
# "v2.8.0", "V2.8.0", "Version 2.8.0" — not SVG path data ("5.2.8"), IP addresses
# (127.0.0.1) or CDN URLs, which carry no v/Version prefix or sit inside a URL.
_VERSION_TEXT = re.compile(r'(?:\b[vV]|\b[Vv]ersion\s*)(\d+\.\d+\.\d+)\b')
_COMMENT = ('#', '//', '/*', '*', '<!--')


def _user_facing_sources():
    """Every first-party file that puts text on the screen or into a report/export."""
    pats = ['ui/*.html', 'ui/*.js', 'ui/*.css', 'ui/modules/**/*.js', 'ui/brand/*.svg',
            'packaging/*.html', 'p6_*/**/*.py', 'p6_*/**/*.html', 'p6_*/**/*.js']
    files = {os.path.join(ROOT, f) for f in ('server.py', 'app.py', 'cli.py', 'utils.py',
                                            'db.py', 'app_startup.py')}
    for pat in pats:
        files.update(glob.glob(os.path.join(ROOT, pat), recursive=True))
    # ui/vendor is third-party code (Leaflet); it is never version text of this app.
    return sorted(os.path.normpath(f) for f in files if os.path.isfile(f)
                  and os.sep + 'vendor' + os.sep not in os.path.normpath(f))


def version_literals(text):
    """(line no, version) for every literal release version in *text* (comments skipped)."""
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith(_COMMENT):
            continue
        line = re.sub(r'https?://\S+', '', line)
        hits += [(n, v) for v in _VERSION_TEXT.findall(line)]
    return hits


def test_version_scan_catches_what_the_user_would_see():
    assert version_literals('<span class="hc-ver-pill">Since v2.2.0</span>') == [(1, '2.2.0')]
    assert version_literals('<div class="ver">Version 2.2.0</div>') == [(1, '2.2.0')]
    assert version_literals("footer = f'Controlyx 2026 V2.9.0'") == [(1, '2.9.0')]
    # not version text: SVG path data, loopback IPs, CDN URLs, comments
    assert version_literals('<path d="m12 3 2.3 4.7 5.2.8-3.7 3.6.9"/>') == []
    assert version_literals("host = '127.0.0.1'") == []
    assert version_literals('<script src="https://cdn.x/leaflet/v1.9.4/l.js">') == []
    assert version_literals('# fixed in v2.8.0') == []


def test_no_literal_release_version_in_any_user_facing_source():
    files = _user_facing_sources()
    names = {os.path.relpath(f, ROOT).replace(os.sep, '/') for f in files}
    assert {'ui/index.html', 'ui/app.js', 'ui/modules/help.js', 'ui/modules/boot.js',
            'server.py', 'app.py', 'packaging/splash.html'} <= names
    assert any(n.startswith('p6_export/') for n in names)
    hits = []
    for f in files:
        with open(f, encoding='utf-8', errors='replace') as fh:
            hits += [f'{os.path.relpath(f, ROOT)}:{n}: v{v}' for n, v in version_literals(fh.read())]
    assert not hits, ('literal release version in a user-facing source — build it from '
                      'window.__APP_VERSION__ / utils.APP_VERSION instead:\n' + '\n'.join(hits))


# ── [accept:c25:r1] Help ▸ What's New is read from the newest CHANGELOG release ──
_NOTES_MD = """# Changelog

## [Unreleased]

### Added — Next thing
- **Coming soon.** Detail.

## [v3.1.4] - 2026-10-01

### Added — Big feature: read from your P6 file
- **15 questions instead of 182.** The library is regrouped.
  - nested detail is not a point
- **Nothing is lost.** Every question is kept.
- Plain first sentence here. And a second one.
- **Four.** x
- **Five.** x
- **Six.** x

### Changed — Something else
- See [the guide](https://example.com/guide) for `details`.

### Fixed
- **Answers no longer show "None"** in place of a date.

## [v3.1.3] - 2026-09-01

### Added — Old feature
- **Old.** x
"""


def test_release_notes_read_the_newest_release_and_the_unreleased_section(tmp_path):
    notes = utils.release_notes(_write(tmp_path, _NOTES_MD))
    assert notes['version'] == '3.1.4' and notes['date'] == '2026-10-01'
    kinds_titles = [(i['kind'], i['title']) for i in notes['items']]
    assert kinds_titles == [('Added', 'Big feature: read from your P6 file'),
                            ('Changed', 'Something else'), ('Fixed', 'Fixes')]
    big = notes['items'][0]
    assert big['points'] == ['15 questions instead of 182', 'Nothing is lost',
                             'Plain first sentence here', 'Four']
    assert big['more'] == 2                        # Five, Six — nested bullets never count
    assert notes['items'][1]['points'] == ['See the guide for details']
    assert notes['items'][2]['points'] == ['Answers no longer show "None"']
    assert [(i['kind'], i['title']) for i in notes['upcoming']] == [('Added', 'Next thing')]
    assert 'Old feature' not in str(notes)       # older releases are not "new"


def test_release_notes_missing_changelog_is_empty(tmp_path):
    empty = {'version': '', 'date': '', 'items': [], 'upcoming': []}
    assert utils.release_notes(str(tmp_path / 'nope.md')) == empty


def test_release_notes_follow_app_version_and_show_no_other_version():
    notes = utils.APP_RELEASE_NOTES
    assert notes['version'] == utils.APP_VERSION and notes['items'], notes
    text = json.dumps(notes, ensure_ascii=False)
    # What's New must never name a release other than the one the app is (c25).
    others = set(re.findall(r'\d+\.\d+\.\d+', text)) - {utils.APP_VERSION}
    assert not others, f"What's New would show another version: {sorted(others)}"


def test_index_injects_the_release_notes(test_server):
    html = urllib.request.urlopen(f'http://127.0.0.1:{test_server}/').read().decode()
    m = re.search(r'window\.__APP_RELEASE_NOTES__ = (\{.*?\});(?=window\.|document\.)', html)
    assert m, 'window.__APP_RELEASE_NOTES__ is injected with the other app globals'
    assert json.loads(m.group(1)) == json.loads(json.dumps(utils.APP_RELEASE_NOTES))
    assert '</' not in m.group(1), 'the injected JSON cannot close the <script>'
    assert html.index('__APP_RELEASE_NOTES__') < html.index('</head>')   # before app.js runs


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
    assert 'utils.APP_VERSION' in step and 'GITHUB_REF_NAME' in step and 'exit 1' in step, \
        'a tag that differs from the newest CHANGELOG release must fail the build'
