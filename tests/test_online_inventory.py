"""Every web address the tool uses — one inventory, checked two ways.

1. Static (always runs): every http(s) address written in the app's own code (ui/ and the
   Python packages) must be accounted for below — a web page the planner opens in the
   default browser (utils.EXTERNAL_LINK_HOSTS, the open_external allow-list), an online
   service the app calls itself (with an offline message — see test_online_services.py),
   or something that is never contacted (XML namespaces, the local server). A new address
   that is none of these fails here, so no link or online call ships unchecked.
2. Live (opt-in: set CONTROLYX_LIVE_NET=1): each address is fetched and must answer.
   Off by default — the owner's PC and CI are often offline.
"""
import os
import re
import urllib.error
import urllib.request

import pytest

import utils

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Online services the app calls itself (never opened in a browser).
ONLINE_SERVICE_HOSTS = {
    'nominatim.openstreetmap.org',      # Bad Weather ▸ place search + pin naming (server.py)
    'tile.openstreetmap.org',           # Bad Weather ▸ location map tiles (calendar.js)
    'api.open-meteo.com',               # live 16-day forecast (p6_calendar/weather.py)
    'archive-api.open-meteo.com',       # multi-year weather history
    'air-quality-api.open-meteo.com',   # dust / sandstorm days
    'huggingface.co',                   # AI Chat ▸ offline brain download (p6_chat/llm.py)
}

# Written in the code but never contacted over the network.
NEVER_CONTACTED_HOSTS = {
    'localhost', '127.0.0.1',           # the app's own local server
    'schemas.openxmlformats.org', 'schemas.microsoft.com', 'www.w3.org',
    'xmlns.oracle.com',                 # XML namespace names (Word / Excel / SVG / P6)
    'xcap.invalid',                     # internal marker in the chart rasteriser (.invalid TLD)
    'api.anthropic.com',                # dormant p6_ai cloud review: no screen calls it
}

_URL = re.compile(r'''https?://([A-Za-z0-9.-]+|\{s\}\.[A-Za-z0-9.-]+)''')


def _code_files():
    for base, dirs, files in os.walk(ROOT):
        rel = os.path.relpath(base, ROOT).replace('\\', '/')
        top = rel.split('/')[0]
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in (
            'node_modules', '__pycache__', 'vendor', 'build', 'dist')]
        if rel == '.':
            dirs[:] = [d for d in dirs if d == 'ui' or d.startswith('p6_')]
            for f in files:
                if f.endswith('.py'):
                    yield os.path.join(base, f)
            continue
        if top != 'ui' and not top.startswith('p6_'):
            continue
        for f in files:
            if f.endswith(('.py', '.js', '.html', '.css', '.json')):
                yield os.path.join(base, f)


def _hosts_in_code():
    found = {}
    for path in _code_files():
        try:
            text = open(path, encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        for m in _URL.finditer(text):
            host = m.group(1).lower().rstrip('.')
            found.setdefault(host, os.path.relpath(path, ROOT))
    return found


def test_every_web_address_in_the_code_is_accounted_for():
    known = set(utils.EXTERNAL_LINK_HOSTS) | ONLINE_SERVICE_HOSTS | NEVER_CONTACTED_HOSTS
    unknown = {h: f for h, f in _hosts_in_code().items() if h not in known}
    assert not unknown, (
        'New web address(es) — add each to utils.EXTERNAL_LINK_HOSTS (a page opened in the '
        'browser) or ONLINE_SERVICE_HOSTS (an online call, with an offline message): '
        f'{unknown}')


def test_map_tiles_use_the_current_openstreetmap_address():
    """OSM deprecated the a/b/c.tile… subdomains — the map uses the single current host."""
    src = open(os.path.join(ROOT, 'ui', 'modules', 'calendar.js'), encoding='utf-8').read()
    assert "'https://tile.openstreetmap.org/{z}/{x}/{y}.png'" in src
    assert '{s}.tile.openstreetmap.org' not in src


def test_online_services_are_never_browser_links():
    for h in ONLINE_SERVICE_HOSTS:
        assert not utils.is_allowed_external_url(f'https://{h}/'), h


# ── live (opt-in) ───────────────────────────────────────────────────────────
_LIVE = os.environ.get('CONTROLYX_LIVE_NET') == '1'
_BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/140.0 Safari/537.36')


def _live_urls():
    from p6_chat import llm
    urls = [
        ('page', 'https://leafletjs.com'),
        ('page', 'https://www.openstreetmap.org/copyright'),
        ('page', 'https://open-meteo.com/'),
        ('service', 'https://nominatim.openstreetmap.org/search?q=Port%20Said&format=json&limit=1'),
        ('service', 'https://nominatim.openstreetmap.org/reverse?lat=31.26&lon=32.30&format=json'),
        ('service', 'https://tile.openstreetmap.org/3/4/3.png'),
        ('service', 'https://api.open-meteo.com/v1/forecast?latitude=31.26&longitude=32.30'
                    '&daily=precipitation_sum&forecast_days=3'),
        ('service', 'https://archive-api.open-meteo.com/v1/archive?latitude=31.26&longitude=32.30'
                    '&start_date=2025-01-01&end_date=2025-01-07&daily=precipitation_sum'),
        ('service', 'https://air-quality-api.open-meteo.com/v1/air-quality?latitude=31.26'
                    '&longitude=32.30&hourly=pm10&forecast_days=1'),
    ]
    for m in llm.MODELS.values():
        for p in m.get('parts') or [m]:
            urls.append(('download', p['url']))
    # Help ▸ Contact / About LinkedIn profiles (read from help.js so a changed address is
    # checked too). LinkedIn answers scripted requests with its anti-bot status 999 while
    # the same page opens normally in the planner's browser — 999 therefore proves the
    # host is up and reachable; anything else (404, DNS failure) is a broken link.
    help_js = open(os.path.join(ROOT, 'ui', 'modules', 'help.js'), encoding='utf-8').read()
    for u in sorted(set(re.findall(r"https://www\.linkedin\.com/in/[A-Za-z0-9_-]+/?", help_js))):
        urls.append(('linkedin', u))
    return urls


@pytest.mark.skipif(not _LIVE, reason='live network check: set CONTROLYX_LIVE_NET=1')
@pytest.mark.parametrize('kind,url', _live_urls() if _LIVE else [])
def test_live_address_answers(kind, url):
    # Pages open in the planner's browser → fetch like a browser. The app's own calls
    # identify themselves honestly (utils.USER_AGENT), as the services' policies ask.
    headers = {'User-Agent': _BROWSER_UA if kind in ('page', 'linkedin') else utils.USER_AGENT}
    req = urllib.request.Request(url, headers=headers, method='HEAD' if kind == 'download' else 'GET')
    # One retry on a connection-level failure (timeout / reset): a network blip on the
    # test machine is not a broken link. An HTTP status is final on the first answer.
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                status = r.status
            break
        except urllib.error.HTTPError as e:
            status = e.code
            break
        except (urllib.error.URLError, OSError):
            if attempt == 2:
                raise
    ok = {200, 999} if kind == 'linkedin' else {200}
    assert status in ok, f'{url} answered HTTP {status}'
