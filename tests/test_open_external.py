"""Help ▸ Contact / About LinkedIn links open in the user's default browser from the packaged
app through Api.open_external(url) — and ONLY allow-listed https links do (utils)."""
import pytest

import utils


@pytest.mark.parametrize('url', [
    'https://www.linkedin.com/in/ibrahim-gebril-417a40270/',
    'https://www.linkedin.com/in/mostafaahmedagamy/',
    'https://linkedin.com/in/mostafaahmedagamy/',
    '  https://www.linkedin.com/in/mostafaahmedagamy/  ',
])
def test_allowed_links(url):
    assert utils.is_allowed_external_url(url)


@pytest.mark.parametrize('url', [
    'http://www.linkedin.com/in/mostafaahmedagamy/',          # not https
    'https://www.linkedin.com.evil.example/in/x',              # look-alike host
    'https://evil.example/?u=https://www.linkedin.com/',       # other host
    'https://user:pw@www.linkedin.com/in/x',                   # credentials
    'https://www.linkedin.com:8443/in/x',                      # custom port
    'file:///C:/Windows/System32/calc.exe',
    'javascript:alert(1)',
    'C:\\Windows\\notepad.exe',
    '',
    None,
    123,
    'https://www.linkedin.com/' + 'a' * 3000,
])
def test_refused_links(url):
    assert not utils.is_allowed_external_url(url)


def test_api_open_external_uses_default_browser_only_for_allowed(monkeypatch):
    app = pytest.importorskip('app')          # needs pywebview (bundled in the exe; installed here)
    opened = []
    monkeypatch.setattr(app.webbrowser, 'open', lambda u, new=0: opened.append((u, new)) or True)
    api = app.Api()
    assert api.open_external('https://www.linkedin.com/in/mostafaahmedagamy/') is True
    assert api.open_external('https://evil.example/') is False
    assert api.open_external('file:///C:/x.exe') is False
    assert opened == [('https://www.linkedin.com/in/mostafaahmedagamy/', 2)]


def test_api_open_external_survives_a_browser_failure(monkeypatch):
    app = pytest.importorskip('app')

    def boom(u, new=0):
        raise OSError('no browser')
    monkeypatch.setattr(app.webbrowser, 'open', boom)
    assert app.Api().open_external('https://www.linkedin.com/in/x/') is False


def test_help_links_are_on_the_allow_list():
    """Every external link Help renders must pass the allow-list, or it would silently do nothing."""
    import re
    src = open(utils.resource_path('ui/modules/help.js'), encoding='utf-8').read()
    urls = re.findall(r"url: '(https://[^']+)'", src)
    assert 'https://www.linkedin.com/in/mostafaahmedagamy/' in urls
    assert 'https://www.linkedin.com/in/ibrahim-gebril-417a40270/' in urls
    for u in urls:
        assert utils.is_allowed_external_url(u), u


@pytest.mark.parametrize('url', [
    'https://leafletjs.com',                                   # the map's "Leaflet" attribution
    'https://www.openstreetmap.org/copyright',                 # "© OpenStreetMap contributors"
    'https://open-meteo.com/',                                 # Bad Weather ▸ weather source
])
def test_every_linked_site_is_allowed(url):
    """Every site the UI links to opens in the default browser (external_links.js → open_external)."""
    assert utils.is_allowed_external_url(url)


@pytest.mark.parametrize('url', [
    'https://nominatim.openstreetmap.org/search?q=x',          # an API, not a page to open
    'https://tile.openstreetmap.org/1/1/1.png',
    'https://huggingface.co/Qwen/x.gguf',                      # a download, never a browser tab
    'https://api.open-meteo.com/v1/forecast',
    'https://openstreetmap.org.evil.example/',
])
def test_api_hosts_and_lookalikes_are_not_browser_links(url):
    assert not utils.is_allowed_external_url(url)


def test_user_agent_is_built_from_the_brand_constants():
    assert utils.USER_AGENT.startswith(f'{utils.APP_NAME}/{utils.APP_VERSION}')
    assert 'nPace' not in utils.USER_AGENT


def test_network_error_message_is_plain_english():
    import socket
    import urllib.error
    offline = utils.network_error_message(
        urllib.error.URLError(socket.gaierror(11001, 'getaddrinfo failed')), 'OpenStreetMap',
        needs='the place search')
    assert offline.startswith('No internet connection')
    assert 'The place search needs the internet' in offline
    assert 'getaddrinfo' not in offline
    slow = utils.network_error_message(urllib.error.URLError(TimeoutError('timed out')), 'Open-Meteo')
    assert 'did not answer in time' in slow
    busy = utils.network_error_message(
        urllib.error.HTTPError('https://x', 429, 'Too Many', {}, None), 'OpenStreetMap')
    assert 'busy' in busy
    down = utils.network_error_message(
        urllib.error.HTTPError('https://x', 503, 'Unavailable', {}, None), 'Open-Meteo')
    assert 'temporarily unavailable' in down and '503' in down
    assert 'could not read' in utils.network_error_message(ValueError('bad json'), 'Open-Meteo')
