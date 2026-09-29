"""Every online service the tool calls fails SAFELY when the internet is down (common on the
owner's PC): a clear in-page message, no hang, and never an invented result.

  * Bad Weather (Open-Meteo forecast / ERA5 history / air-quality) — an empty download is
    never presented or saved as a zero-impact estimate; the last good estimate is kept; when
    the PC is offline only ONE call is attempted (no minutes of waiting); partial gaps
    (forecast / dust) are listed with the source reference.
  * Place search / pin naming (OpenStreetMap Nominatim) — plain offline message, typed
    coordinates work with no internet, a dropped pin keeps its coordinates as its name.

No real network: p6_calendar.weather._get_json and server._nominatim_get are stubbed.
"""
import http.client
import json
import socket
import urllib.error
import urllib.parse
from datetime import date, timedelta

import pytest

import db


def _post(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=60)
    conn.request('POST', path, body=json.dumps(payload).encode(),
                 headers={'Content-Type': 'application/json'})
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read())


OFFLINE = urllib.error.URLError(socket.gaierror(11001, 'getaddrinfo failed'))


def _daily(start, end, rain=0.0):
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return {'daily': {'time': [x.isoformat() for x in days],
                      'precipitation_sum': [rain] * len(days),
                      'temperature_2m_max': [30.0] * len(days),
                      'wind_speed_10m_max': [10.0] * len(days)}}


def _fake_open_meteo(fail=(), calls=None, error=None):
    """A stand-in for Open-Meteo: 'forecast' / 'archive' / 'air' fail when listed in `fail`."""
    def get_json(url, timeout=20):
        kind = 'archive' if 'archive-api' in url else 'air' if 'air-quality' in url else 'forecast'
        if calls is not None:
            calls.append(kind)
        if kind in fail:
            raise (error or OFFLINE)
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        if kind == 'archive':
            return _daily(date.fromisoformat(q['start_date']), date.fromisoformat(q['end_date']), rain=12.0)
        if kind == 'air':
            return {'hourly': {'time': [], 'pm10': [], 'dust': []}}
        today = date(2024, 7, 2)
        return _daily(today, today + timedelta(days=15))
    return get_json


# ── build_daily_weather (unit) ───────────────────────────────────────────────
def test_offline_stops_after_the_first_call(monkeypatch):
    from p6_calendar import weather
    calls = []
    monkeypatch.setattr(weather, '_get_json', _fake_open_meteo(fail=('forecast', 'archive', 'air'), calls=calls))
    net = {}
    daily, climate, _h, _m = weather.build_daily_weather(1.0, 2.0, date(2024, 7, 1), date(2024, 12, 31), net=net)
    assert daily == {} and climate == {}
    assert net['offline'] is True
    assert calls == ['forecast'], 'offline → no waiting on the other calls'
    assert set(net['errors']) == {'forecast', 'history', 'dust'}


def test_forecast_http_error_falls_back_to_climate_for_every_date(monkeypatch):
    from p6_calendar import weather
    err = urllib.error.HTTPError('https://api.open-meteo.com', 503, 'Unavailable', {}, None)
    monkeypatch.setattr(weather, '_get_json', _fake_open_meteo(fail=('forecast',), error=err))
    net = {}
    daily, climate, horizon, _m = weather.build_daily_weather(1.0, 2.0, date(2024, 7, 1), date(2024, 12, 31), net=net)
    assert net['offline'] is False
    assert 'forecast' in net['errors'] and 'history' not in net['errors']
    assert horizon == date(2024, 7, 1), 'no forecast → the climate history covers the near term too'
    assert date(2024, 7, 2) in climate, 'the next days are not left uncounted'


def test_unreadable_answer_is_caught_not_raised(monkeypatch):
    from p6_calendar import weather

    def bad(url, timeout=20):
        raise http.client.IncompleteRead(b'')
    monkeypatch.setattr(weather, '_get_json', bad)
    net = {}
    weather.build_daily_weather(1.0, 2.0, date(2024, 7, 1), date(2024, 12, 31), net=net)
    assert net['offline'] is True


def test_weather_user_agent_is_the_brand_not_a_stale_name():
    from p6_calendar import weather
    import utils
    assert weather._USER_AGENT == utils.USER_AGENT
    assert 'nPace' not in weather._USER_AGENT


# ── /api/weather (route) ─────────────────────────────────────────────────────
@pytest.fixture
def imported(test_server, xml_path):
    _, d = _post(test_server, '/api/parse', {'path': str(xml_path)})
    assert d.get('ok'), d
    return test_server, d


def _weather(port, d, **kw):
    body = {'lat': 26.96, 'lon': 49.57, 'place_name': 'Jubail', 'xml_path': d.get('cached_path'),
            'cached_path': d.get('cached_path'), 'snapshot_id': d['snapshot_id']}
    body.update(kw)
    return _post(port, '/api/weather', body)[1]


def _settings(d):
    return db.get_project_settings(db.get_project_id_for_snapshot(d['snapshot_id'])) or {}


def test_route_offline_says_so_and_never_invents_a_zero_estimate(imported, monkeypatch):
    port, d = imported
    from p6_calendar import weather
    calls = []
    monkeypatch.setattr(weather, '_get_json', _fake_open_meteo(fail=('forecast', 'archive', 'air'), calls=calls))
    r = _weather(port, d, site_type='marine')
    assert r['ok'] is False and r['offline'] is True
    assert r['error'].startswith('No internet connection')
    assert 'saved' in r['error']
    assert 'weather' not in r, 'no estimate is returned'
    s = _settings(d)
    assert 'last_weather' not in s, 'an empty download is never saved as the estimate'
    assert s['location']['name'] == 'Jubail' and s['site_type'] == 'marine', 'settings are kept'
    assert calls == ['forecast']


def test_route_offline_keeps_the_last_good_estimate(imported, monkeypatch):
    port, d = imported
    from p6_calendar import weather
    monkeypatch.setattr(weather, '_get_json', _fake_open_meteo())
    ok = _weather(port, d)
    assert ok['ok'] is True, ok
    before = _settings(d)['last_weather']
    monkeypatch.setattr(weather, '_get_json', _fake_open_meteo(fail=('forecast', 'archive', 'air')))
    r = _weather(port, d)
    assert r['ok'] is False and r['kept_previous'] is True
    assert _settings(d)['last_weather'] == before


def test_route_history_down_is_an_error_not_a_partial_guess(imported, monkeypatch):
    port, d = imported
    from p6_calendar import weather
    err = urllib.error.HTTPError('https://archive-api.open-meteo.com', 503, 'Unavailable', {}, None)
    monkeypatch.setattr(weather, '_get_json', _fake_open_meteo(fail=('archive',), error=err))
    r = _weather(port, d)
    assert r['ok'] is False
    assert 'temporarily unavailable' in r['error'] and 'no estimate was made' in r['error']


def test_route_lists_partial_gaps_with_the_source(imported, monkeypatch):
    port, d = imported
    from p6_calendar import weather
    err = urllib.error.HTTPError('https://x', 502, 'Bad gateway', {}, None)
    monkeypatch.setattr(weather, '_get_json', _fake_open_meteo(fail=('forecast', 'air'), error=err))
    r = _weather(port, d)
    assert r['ok'] is True, r
    gaps = r['weather']['climate_reference']['gaps']
    assert any(g.startswith('Live forecast unavailable') for g in gaps)
    assert any(g.startswith('Dust forecast unavailable') for g in gaps)


def test_route_online_has_no_gaps(imported, monkeypatch):
    port, d = imported
    from p6_calendar import weather
    monkeypatch.setattr(weather, '_get_json', _fake_open_meteo())
    r = _weather(port, d)
    assert r['ok'] is True and r['weather']['climate_reference']['gaps'] == []


# ── /api/geocode (route) ─────────────────────────────────────────────────────
def test_place_search_offline_is_a_plain_message(test_server, monkeypatch):
    import server as srv

    def offline(endpoint, params, timeout=15):
        raise OFFLINE
    monkeypatch.setattr(srv, '_nominatim_get', offline)
    _, r = _post(test_server, '/api/geocode', {'q': 'Jubail'})
    assert r['ok'] is False and r['offline'] is True
    assert r['error'].startswith('No internet connection')
    assert 'coordinates' in r['error']
    assert 'getaddrinfo' not in r['error']


def test_typed_coordinates_need_no_internet(test_server, monkeypatch):
    import server as srv

    def boom(*a, **k):
        raise AssertionError('no network call for typed coordinates')
    monkeypatch.setattr(srv, '_nominatim_get', boom)
    _, r = _post(test_server, '/api/geocode', {'q': '26.9598, 49.5687'})
    assert r['ok'] is True
    assert r['results'] == [{'name': '26.9598, 49.5687', 'lat': 26.9598, 'lon': 49.5687}]


@pytest.mark.parametrize('text,expected', [
    ('26.9598, 49.5687', (26.9598, 49.5687)),
    ('26.9598 49.5687', (26.9598, 49.5687)),
    ('-33.86;151.21', (-33.86, 151.21)),
    ('Jubail', None),
    ('95, 10', None),              # latitude out of range
    ('10, 190', None),             # longitude out of range
    ('Route 66, 12', None),
])
def test_parse_coordinates(text, expected):
    import server as srv
    assert srv._parse_coordinates(text) == expected


def test_pin_naming_offline_keeps_the_coordinates(test_server, monkeypatch):
    import server as srv

    def offline(endpoint, params, timeout=15):
        raise OFFLINE
    monkeypatch.setattr(srv, '_nominatim_get', offline)
    _, r = _post(test_server, '/api/geocode', {'lat': 26.9598, 'lon': 49.5687})
    assert r['ok'] is False and r['offline'] is True
    assert r['name'] == '26.9598, 49.5687'


def test_place_search_online_shape(test_server, monkeypatch):
    import server as srv
    seen = []

    def fake(endpoint, params, timeout=15):
        seen.append((endpoint, params))
        return [{'display_name': 'Jubail, Saudi Arabia', 'lat': '27.0', 'lon': '49.6'}, {'bad': 1}]
    monkeypatch.setattr(srv, '_nominatim_get', fake)
    _, r = _post(test_server, '/api/geocode', {'q': 'Jubail'})
    assert r == {'ok': True, 'results': [{'name': 'Jubail, Saudi Arabia', 'lat': 27.0, 'lon': 49.6}]}
    assert seen[0][0] == 'search' and seen[0][1]['q'] == 'Jubail'


def test_nominatim_sends_the_brand_user_agent(monkeypatch):
    import server as srv
    import utils
    import urllib.request
    got = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'[]'

    def fake_urlopen(req, timeout=None):
        got['ua'] = req.get_header('User-agent')
        got['url'] = req.full_url
        got['timeout'] = timeout
        return Resp()
    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    assert srv._nominatim_get('search', {'q': 'x', 'format': 'json'}) == []
    assert got['ua'] == utils.USER_AGENT
    assert got['url'].startswith('https://nominatim.openstreetmap.org/search?')
    assert got['timeout'] and got['timeout'] <= 20
