import sys
import os
import re

# ── Branding ────────────────────────────────────────────────────────────────
# Single source of truth for the product name shown to users (window title,
# headers, CLI banner). Some internal identifiers — the ``p6_evm`` package and
# the UI localStorage keys — intentionally keep their original names so imports
# and existing per-user UI state don't break. The per-user data folder is
# ``.controlyx`` (holding ``controlyx.db``), migrated automatically from the
# older ``P6EVMTool`` / ``Controlyx`` / ``.p6evmtool`` folders on first run.
APP_NAME = 'Controlyx'                     # brand / product name
APP_EDITION = '2026'                       # edition (year)
APP_TITLE = f'{APP_NAME} {APP_EDITION}'    # full display name, e.g. "Controlyx 2026"


_RELEASE_HEADING = re.compile(r'## \[v(\d+\.\d+\.\d+)\]')


def release_version(changelog_path=None):
    """Newest released version ("X.Y.Z") read from CHANGELOG.md — the ONE version source.

    The release process already starts by adding a ``## [vX.Y.Z] - date`` section to
    CHANGELOG.md, so the version is read from there rather than typed a second time.
    ``## [Unreleased]`` is skipped. By default the changelog is found at the project
    root — in the packaged one-file exe that is ``sys._MEIPASS`` (controlyx.spec ships
    CHANGELOG.md there). Returns '' when there is no changelog or no release heading:
    the UI then simply hides the version line rather than show an invented number.
    """
    try:
        with open(changelog_path or _changelog_path(), encoding='utf-8') as f:
            for line in f:
                m = _RELEASE_HEADING.match(line)
                if m:
                    return m.group(1)
    except (OSError, UnicodeDecodeError):
        pass
    return ''


def _changelog_path():
    # Project root in development; sys._MEIPASS in the one-file exe (the spec ships it).
    root = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, 'CHANGELOG.md')


# ── Help ▸ What's New: the headline changes of the newest release ────────────
_BLOCK_HEADING = re.compile(r'## \[(?:(Unreleased)|v(\d+\.\d+\.\d+))\](?:\s*-\s*(\S+))?', re.I)
_KIND_HEADING = re.compile(r'### +([A-Za-z]+)\s*(?:[—–-]+\s*(.*?))?\s*$')
_UNTITLED = {'Added': 'Additions', 'Changed': 'Changes', 'Fixed': 'Fixes'}


def _md_plain(text):
    """Markdown → plain words: [label](url) → label, `code` → code, **bold** → bold."""
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    return re.sub(r'\s+', ' ', text.replace('`', '').replace('**', '')).strip()


def _first_sentence(text):
    return re.split(r'(?<=[.!?])\s+', _md_plain(text), 1)[0]


def _note_point(bullet):
    """One line per bullet: its bold lead-in, else its first sentence.

    A short label lead-in ("**Cause:** the start-up screen …") says nothing on its own,
    so it keeps the first sentence after it: "Cause: the start-up screen …".
    """
    m = re.match(r'\*\*(.+?)\*\*\s*(.*)$', bullet)
    if m:
        point, rest = _md_plain(m.group(1)), _first_sentence(m.group(2))
        if point.endswith(':') and len(point.split()) <= 3 and rest:
            point = f'{point} {rest}'
    else:
        point = _first_sentence(bullet)
    point = point.rstrip('.:;,').strip()
    return point if len(point) <= 140 else point[:139].rstrip() + '…'


def _note_items(lines, max_points):
    items = []
    for line in lines:
        h = _KIND_HEADING.match(line)
        if h:
            kind = h.group(1).capitalize()
            title = _md_plain(h.group(2) or '') or _UNTITLED.get(kind, kind)
            items.append({'kind': kind, 'title': title, 'points': [], 'more': 0})
            continue
        b = re.match(r'- +(\S.*)$', line)          # top-level bullets only (no indent)
        if not b:
            continue
        if not items:
            items.append({'kind': 'Changed', 'title': 'Changes', 'points': [], 'more': 0})
        point, item = _note_point(b.group(1)), items[-1]
        if point and len(item['points']) < max_points:
            item['points'].append(point)
        elif point:
            item['more'] += 1
    return items


def release_notes(changelog_path=None, max_points=4):
    """What's New, read from CHANGELOG.md — the same source as release_version().

    ``{'version', 'date', 'items', 'upcoming'}``: ``items`` are the newest release's
    ``### Added/Changed/Fixed — title`` sections, each ``{'kind', 'title', 'points',
    'more'}`` (``points`` = up to *max_points* bullet lead-ins, ``more`` = how many
    further bullets). ``upcoming`` is the ``[Unreleased]`` section — work already in this
    build that the next release will carry. Nothing is typed twice, so Help can never
    show an old release as "new". Empty when there is no changelog.
    """
    blocks, cur = [], None
    try:
        with open(changelog_path or _changelog_path(), encoding='utf-8') as f:
            for line in f.read().splitlines():
                m = _BLOCK_HEADING.match(line)
                if m:
                    cur = {'unreleased': bool(m.group(1)), 'version': m.group(2) or '',
                           'date': m.group(3) or '', 'lines': []}
                    blocks.append(cur)
                elif line.startswith('## '):
                    cur = None
                elif cur is not None:
                    cur['lines'].append(line)
    except (OSError, UnicodeDecodeError):
        blocks = []
    release = next((b for b in blocks if not b['unreleased']), None)
    unreleased = next((b for b in blocks if b['unreleased']), None)
    if release and unreleased and blocks.index(unreleased) > blocks.index(release):
        unreleased = None                           # an [Unreleased] below a release is stale
    return {
        'version': release['version'] if release else '',
        'date': release['date'] if release else '',
        'items': _note_items(release['lines'], max_points) if release else [],
        'upcoming': _note_items(unreleased['lines'], max_points) if unreleased else [],
    }


# Release version shown in the UI (Help ▸ About, Help footer), /api/health and the
# User-Agent. Injected into every page as window.__APP_VERSION__ (server.py).
APP_VERSION = release_version()
# Help ▸ What's New, injected into every page as window.__APP_RELEASE_NOTES__ (server.py).
APP_RELEASE_NOTES = release_notes()

# ── External links ──────────────────────────────────────────────────────────
# The only web pages the app may hand to the user's default browser. The packaged WebView
# calls Api.open_external(url) (app.py) for every link click (ui/modules/external_links.js);
# anything not https on one of these hosts is refused, so page content can never make the
# app launch an arbitrary URL or a local program. Every host the UI links to:
#   * LinkedIn          — Help ▸ Contact / About profiles
#   * Leaflet           — the map's attribution ("Leaflet") in Bad Weather ▸ location
#   * OpenStreetMap     — the map's "© OpenStreetMap contributors" copyright link
#   * Open-Meteo        — Bad Weather ▸ "Where the numbers come from" (weather source)
EXTERNAL_LINK_HOSTS = frozenset({
    'www.linkedin.com', 'linkedin.com',
    'leafletjs.com', 'www.leafletjs.com',
    'www.openstreetmap.org', 'openstreetmap.org',
    'open-meteo.com', 'www.open-meteo.com',
})

# Identifies the app to the free online services it calls (OpenStreetMap Nominatim,
# Open-Meteo, the Hugging Face model download) — their usage policies ask for an honest,
# identifying User-Agent. Built from the brand constants, never hardcoded.
USER_AGENT = f'{APP_NAME}/{APP_VERSION or "dev"} (desktop P6 schedule analysis)'

# How long an online call may wait to CONNECT before the app says it cannot reach the
# service. Reaching a server normally takes well under a second; a network that silently
# drops the packets (firewall, captive portal, broken proxy) would otherwise hold the
# spinner for the whole READ timeout, which stays longer because a large answer (e.g.
# five years of weather history) can legitimately take a while to arrive.
CONNECT_TIMEOUT = 6

_QUICK_OPENERS = {}


def _quick_connect_opener(connect_timeout):
    """A urllib opener whose connections CONNECT (TCP + TLS handshake) within
    ``connect_timeout`` seconds, then read with the caller's own timeout. Proxies, TLS
    certificate checks and redirects behave exactly as with ``urllib.request.urlopen``."""
    opener = _QUICK_OPENERS.get(connect_timeout)
    if opener is not None:
        return opener
    import http.client
    import urllib.request

    def _quick(base):
        class QuickConnect(base):
            def connect(self):
                read_timeout = self.timeout
                numeric = isinstance(read_timeout, (int, float))
                self.timeout = min(connect_timeout, read_timeout) if numeric else connect_timeout
                try:
                    super().connect()
                finally:
                    self.timeout = read_timeout
                if numeric and self.sock is not None:
                    self.sock.settimeout(read_timeout)
        return QuickConnect

    quick_http, quick_https = _quick(http.client.HTTPConnection), _quick(http.client.HTTPSConnection)

    class QuickHTTPHandler(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(quick_http, req)

    class QuickHTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(quick_https, req, context=self._context)

    opener = urllib.request.build_opener(QuickHTTPHandler, QuickHTTPSHandler)
    _QUICK_OPENERS[connect_timeout] = opener
    return opener


def open_url(req, timeout=20, connect_timeout=CONNECT_TIMEOUT):
    """``urllib.request.urlopen`` for the app's online services, with a short CONNECT
    timeout (``connect_timeout``) and the longer READ timeout ``timeout`` — so an offline or
    black-holed network is reported in seconds, while a slow but working service still has
    time to answer. Raises exactly what ``urlopen`` raises (URLError / HTTPError /
    TimeoutError), which ``network_error_message`` turns into plain English."""
    return _quick_connect_opener(connect_timeout).open(req, timeout=timeout)


def network_error_message(exc, service='this online service', needs=''):
    """One plain-English sentence for an online call that failed — shown in the page.

    Distinguishes "no internet / cannot reach it" from "the service answered with an
    error" so the planner knows whether to check the connection or try later. ``needs``
    is appended as the reason the internet is needed (e.g. "the weather history")."""
    import socket
    import urllib.error
    import http.client
    code = getattr(exc, 'code', None)
    if isinstance(exc, urllib.error.HTTPError) or (isinstance(code, int) and 100 <= code < 600):
        if code == 429:
            return (f'{service} is busy (too many requests) — wait a minute and try again.')
        if code in (401, 403):
            return (f'{service} refused the request (HTTP {code}) — a firewall or proxy may be '
                    f'blocking it; try again later or from another network.')
        if code == 404:
            return f'{service} could not find the requested item (HTTP 404).'
        if isinstance(code, int) and code >= 500:
            return f'{service} is temporarily unavailable (HTTP {code}) — try again later.'
        return f'{service} answered with an error (HTTP {code}) — try again later.'
    reason = getattr(exc, 'reason', exc)
    why = f' {needs[0].upper()}{needs[1:]} needs the internet.' if needs else ''
    if isinstance(reason, (TimeoutError, socket.timeout)) or isinstance(exc, (TimeoutError, socket.timeout)):
        return (f'{service} did not answer in time — the internet connection looks slow or '
                f'blocked.{why} Check the connection and try again.')
    if isinstance(exc, (urllib.error.URLError, OSError, http.client.HTTPException)):
        return (f'No internet connection — could not reach {service}.{why} '
                f'Connect to the internet and try again.')
    if isinstance(exc, ValueError):
        return f'{service} sent an answer the app could not read — try again later.'
    return f'Could not reach {service} ({exc}).'


def is_allowed_external_url(url):
    """True only for a plain ``https://`` URL on an allow-listed host (no credentials, no
    custom port)."""
    from urllib.parse import urlsplit
    if not isinstance(url, str) or len(url) > 2048:
        return False
    try:
        u = urlsplit(url.strip())
        port = u.port
    except ValueError:
        return False
    return (u.scheme == 'https' and not u.username and not u.password and port is None
            and (u.hostname or '').lower() in EXTERNAL_LINK_HOSTS)


def resource_path(rel):
    """Resolve a path relative to the project root — works in dev and PyInstaller bundle."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)

def exe_dir():
    """Directory next to the .exe (prod) or project root (dev). Legacy — prefer app_data_dir()."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _migrate_data_dir(legacies, new):
    """Return the per-user data dir to use (`new`), migrating the first existing
    legacy folder (tried in `legacies` order) into it on first access. If `new`
    already exists, or no legacy folder is found, nothing moves. If the rename
    fails (e.g. the folder is in use), fall back to that legacy dir in place so
    existing data (DB, cached schedules, knowledge base, settings) is never
    lost — a whole-directory rename moves every sub-path together."""
    if os.path.isdir(new):
        return new
    for legacy in legacies:
        if os.path.isdir(legacy):
            try:
                os.rename(legacy, new)
                return new
            except OSError:
                return legacy
    return new


def app_data_dir():
    """Per-user app data directory. Each OS user gets an isolated folder.

    The folder is `.controlyx` (Windows: %APPDATA%/.controlyx; Mac/Linux:
    ~/.controlyx). Data from the older 'Controlyx' / 'P6EVMTool' / '.p6evmtool'
    folders is migrated into it automatically the first time this runs."""
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
        path = _migrate_data_dir([os.path.join(base, 'Controlyx'),
                                  os.path.join(base, 'P6EVMTool')],
                                 os.path.join(base, '.controlyx'))
    else:
        home = os.environ.get('HOME', os.path.expanduser('~'))
        path = _migrate_data_dir([os.path.join(home, '.p6evmtool')],
                                 os.path.join(home, '.controlyx'))
    os.makedirs(path, exist_ok=True)
    return path

def schedules_dir():
    """Folder where cached XML copies are stored."""
    path = os.path.join(app_data_dir(), 'schedules')
    os.makedirs(path, exist_ok=True)
    return path
