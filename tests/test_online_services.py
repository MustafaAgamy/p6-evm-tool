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


# ── offline AI brain download (Hugging Face) ─────────────────────────────────
class _FakeResp:
    def __init__(self, data, length=None):
        self._data = data
        self._pos = 0
        self.headers = {'Content-Length': str(len(data) if length is None else length)}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        if self._pos >= len(self._data):
            return b''
        chunk = self._data[self._pos:self._pos + (n if n and n > 0 else len(self._data))]
        self._pos += len(chunk)
        return chunk


@pytest.fixture
def brain(tmp_path, monkeypatch):
    from p6_chat import llm
    monkeypatch.setattr(llm, 'app_data_dir', lambda: str(tmp_path))
    monkeypatch.setattr(llm, '_engine_ok', lambda: True)
    llm._DL.update({'active': False, 'pct': None, 'error': None, 'done': False, 'key': None})
    # tiny stand-in sizes so the test downloads bytes, not gigabytes
    small = {
        'fast': {**llm.MODELS['fast'], 'min': 10},
        'detailed': {**llm.MODELS['detailed'],
                     'parts': [{**p, 'min': 10} for p in llm.MODELS['detailed']['parts']]},
    }
    monkeypatch.setattr(llm, 'MODELS', small)
    llm.SLEPT = []                                   # retry waits, recorded instead of slept
    monkeypatch.setattr(llm, '_sleep', llm.SLEPT.append)
    return llm


def test_7b_brain_is_the_published_two_part_split():
    """The single-file 7B name returns HTTP 404 on Hugging Face (checked 2026-09-29); the
    publisher ships q4_k_m as -00001-of-00002 + -00002-of-00002. llama.cpp loads the split
    from part 1, so 'file' must be part 1 and both parts are downloaded."""
    from p6_chat import llm
    spec = llm.MODELS['detailed']
    files = [p['file'] for p in spec['parts']]
    assert files == ['qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf',
                     'qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf']
    assert spec['file'] == files[0]
    for p in spec['parts']:
        assert p['url'].startswith('https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/' + p['file'])
    assert llm.MODELS['fast']['url'].endswith('qwen2.5-3b-instruct-q4_k_m.gguf?download=true')


def test_brain_download_offline_is_a_plain_message_and_leaves_nothing(brain, tmp_path, monkeypatch):
    def offline(req, timeout=None):
        raise OFFLINE
    monkeypatch.setattr(brain.urllib.request, 'urlopen', offline)
    r = brain.setup('fast')
    assert r['ok'] is False
    assert r['error'].startswith('No internet connection')
    assert 'getaddrinfo' not in r['error']
    st = brain.status()
    assert st['downloading'] is False and st['error'] == r['error'] and st['ready'] is False
    models = tmp_path / 'ai' / 'models'
    assert not any(models.iterdir()), 'no partial file left behind'


def test_brain_download_cut_short_is_never_installed(brain, tmp_path, monkeypatch):
    monkeypatch.setattr(brain.urllib.request, 'urlopen',
                        lambda req, timeout=None: _FakeResp(b'x' * 40, length=100))
    r = brain.setup('fast')
    assert r['ok'] is False and 'cut short' in r['error']
    assert not brain._model_ready('fast')
    models = tmp_path / 'ai' / 'models'
    assert not (models / 'qwen2.5-3b-instruct-q4_k_m.gguf').exists(), 'never installed'
    # ...but the part already downloaded is kept for the next Set up (it resumes, see below)
    assert (models / 'qwen2.5-3b-instruct-q4_k_m.gguf.part').stat().st_size == 40
    assert 'is kept' in r['error'] and '40.0%' in r['error']
    assert brain.SLEPT == list(brain._RETRY_DELAYS), 'retried with backoff before giving up'


def test_brain_download_both_7b_parts_with_the_brand_user_agent(brain, tmp_path, monkeypatch):
    import utils
    seen = []

    def fake(req, timeout=None):
        seen.append((req.full_url, req.get_header('User-agent')))
        return _FakeResp(b'y' * 64)
    monkeypatch.setattr(brain.urllib.request, 'urlopen', fake)
    r = brain.setup('detailed')
    assert r == {'ok': True}
    assert [u.split('/')[-1].split('?')[0] for u, _ in seen] == [
        'qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf', 'qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf']
    assert all(ua == utils.USER_AGENT for _, ua in seen)
    assert brain._model_ready('detailed')
    assert brain._model_path('detailed').endswith('-00001-of-00002.gguf')


def test_brain_ready_needs_every_part(brain, tmp_path):
    models = tmp_path / 'ai' / 'models'
    models.mkdir(parents=True)
    (models / 'qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf').write_bytes(b'z' * 64)
    assert not brain._model_ready('detailed'), 'part 2 missing → not ready'
    (models / 'qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf').write_bytes(b'z' * 64)
    assert brain._model_ready('detailed')


def test_brain_download_refuses_without_disk_space(brain, tmp_path, monkeypatch):
    import collections
    monkeypatch.setattr(brain.urllib.request, 'urlopen',
                        lambda req, timeout=None: _FakeResp(b'x' * 10, length=5_000_000_000))
    Usage = collections.namedtuple('Usage', 'total used free')
    monkeypatch.setattr(brain.shutil, 'disk_usage', lambda p: Usage(10, 9, 1_000_000))
    r = brain.setup('fast')
    assert r['ok'] is False and 'Not enough free disk space' in r['error']
    assert not any((tmp_path / 'ai' / 'models').iterdir())


def test_brain_http_404_says_not_found(brain, monkeypatch):
    def nf(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)
    monkeypatch.setattr(brain.urllib.request, 'urlopen', nf)
    r = brain.setup('fast')
    assert r['ok'] is False and 'HTTP 404' in r['error']


# ── NET-1: the brain download resumes instead of restarting 2-4.7 GB from zero ─────────
FAST_FILE = 'qwen2.5-3b-instruct-q4_k_m.gguf'


class _RangeResp(_FakeResp):
    """A download-server answer: 200 with the whole file, or 206 from a Range start."""

    def __init__(self, data, start=0, etag='"v1"', cut=None):
        body = data[start:]
        if cut is not None:                          # the connection drops after `cut` bytes
            body = body[:cut]
        super().__init__(body, length=len(data) - start)
        self.status = 206 if start else 200
        self.headers['ETag'] = etag
        if start:
            self.headers['Content-Range'] = 'bytes %d-%d/%d' % (start, len(data) - 1, len(data))


class _Server:
    """Stands in for Hugging Face: honours Range, can drop the connection or go offline.
    `plan` holds one step per request: an int = drop after that many bytes, 'offline'."""

    def __init__(self, data, etag='"v1"', plan=()):
        self.data, self.etag, self.plan, self.ranges = data, etag, list(plan), []

    def __call__(self, req, timeout=None):
        rng = req.get_header('Range')
        self.ranges.append(rng)
        step = self.plan.pop(0) if self.plan else None
        if step == 'offline':
            raise OFFLINE
        start = int(rng.split('=')[1].rstrip('-')) if rng else 0
        if start >= len(self.data):
            raise urllib.error.HTTPError(req.full_url, 416, 'Range Not Satisfiable', {}, None)
        return _RangeResp(self.data, start, etag=self.etag,
                          cut=step if isinstance(step, int) else None)


def _models(tmp_path):
    return tmp_path / 'ai' / 'models'


def test_brain_download_resumes_from_the_part_already_downloaded(brain, tmp_path, monkeypatch):
    data = bytes(range(100))
    monkeypatch.setattr(brain.urllib.request, 'urlopen',
                        _Server(data, plan=[40, 'offline', 'offline', 'offline']))
    r = brain.setup('fast')
    assert r['ok'] is False and 'is kept' in r['error']
    st = brain.status()
    assert st['resume_pct'] == 40.0 and 'continues from there' in st['detail']
    # the internet is back: Set up again asks only for the rest and installs the whole file
    second = _Server(data)
    monkeypatch.setattr(brain.urllib.request, 'urlopen', second)
    assert brain.setup('fast') == {'ok': True}
    assert second.ranges == ['bytes=40-']
    assert (_models(tmp_path) / FAST_FILE).read_bytes() == data
    assert sorted(p.name for p in _models(tmp_path).iterdir()) == [FAST_FILE], 'no part/note left'
    assert brain.status()['resume_pct'] is None


def test_brain_download_retries_a_dropped_connection_in_the_same_setup(brain, tmp_path, monkeypatch):
    data = bytes(range(200))
    srv = _Server(data, plan=['offline', 90, 50])
    monkeypatch.setattr(brain.urllib.request, 'urlopen', srv)
    assert brain.setup('fast') == {'ok': True}
    assert srv.ranges == [None, None, 'bytes=90-', 'bytes=140-']
    # every try that got further resets the backoff, so a patchy line keeps going
    assert brain.SLEPT == [3, 3, 3]
    assert (_models(tmp_path) / FAST_FILE).read_bytes() == data


def test_brain_download_gives_up_after_the_backoff_when_offline(brain, tmp_path, monkeypatch):
    srv = _Server(b'z' * 100, plan=['offline'] * 10)
    monkeypatch.setattr(brain.urllib.request, 'urlopen', srv)
    r = brain.setup('fast')
    assert r['ok'] is False and r['error'].startswith('No internet connection')
    assert brain.SLEPT == [3, 10, 30] and len(srv.ranges) == 4
    assert not any(_models(tmp_path).iterdir()), 'nothing downloaded, nothing left behind'
    assert brain.status()['downloading'] is False


def test_brain_http_404_is_final_not_retried(brain, monkeypatch):
    def nf(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)
    monkeypatch.setattr(brain.urllib.request, 'urlopen', nf)
    assert brain.setup('fast')['ok'] is False
    assert brain.SLEPT == []


def test_brain_changed_file_is_never_stitched_onto_an_old_part(brain, tmp_path, monkeypatch):
    old = b'o' * 100
    monkeypatch.setattr(brain.urllib.request, 'urlopen',
                        _Server(old, etag='"v1"', plan=[40] + ['offline'] * 3))
    assert brain.setup('fast')['ok'] is False
    new = b'n' * 120                                 # the publisher replaced the file
    srv = _Server(new, etag='"v2"')
    monkeypatch.setattr(brain.urllib.request, 'urlopen', srv)
    assert brain.setup('fast') == {'ok': True}
    assert srv.ranges == ['bytes=40-', None], 'resume refused (other ETag/size), then from zero'
    assert (_models(tmp_path) / FAST_FILE).read_bytes() == new


def test_brain_part_past_the_end_of_the_file_starts_again(brain, tmp_path, monkeypatch):
    models = _models(tmp_path)
    models.mkdir(parents=True)
    url = brain.MODELS['fast']['url']
    (models / (FAST_FILE + '.part')).write_bytes(b'q' * 150)
    (models / (FAST_FILE + '.part.json')).write_text(json.dumps({'url': url, 'total': 150, 'etag': ''}))
    data = b'd' * 100
    srv = _Server(data)                              # resume point 150 >= 100 -> HTTP 416
    monkeypatch.setattr(brain.urllib.request, 'urlopen', srv)
    assert brain.setup('fast') == {'ok': True}
    assert srv.ranges == ['bytes=150-', None]
    assert (models / FAST_FILE).read_bytes() == data


def test_brain_part_from_another_address_is_not_resumed(brain, tmp_path, monkeypatch):
    models = _models(tmp_path)
    models.mkdir(parents=True)
    (models / (FAST_FILE + '.part')).write_bytes(b'q' * 30)
    (models / (FAST_FILE + '.part.json')).write_text(
        json.dumps({'url': 'https://example.invalid/x', 'total': 99}))
    data = b'd' * 100
    srv = _Server(data)
    monkeypatch.setattr(brain.urllib.request, 'urlopen', srv)
    assert brain.setup('fast') == {'ok': True}
    assert srv.ranges == [None]
    assert (models / FAST_FILE).read_bytes() == data


def test_brain_file_smaller_than_the_model_is_never_installed(brain, tmp_path, monkeypatch):
    monkeypatch.setattr(brain.urllib.request, 'urlopen', _Server(b'<html>'))  # min is 10 bytes
    r = brain.setup('fast')
    assert r['ok'] is False and 'smaller than expected' in r['error']
    assert not any(_models(tmp_path).iterdir())


def test_brain_status_while_retrying_says_so(brain):
    brain._DL.update({'active': True, 'pct': 12.5,
                      'note': 'The internet connection dropped — trying again in 10 s (try 3 of 4); '
                              'the part already downloaded is kept.'})
    try:
        st = brain.status()
        assert st['retrying'] is True and st['downloading'] is True
        assert 'trying again in 10 s' in st['detail'] and 'Downloaded so far: 12.5%' in st['detail']
        assert st['resume_pct'] is None
    finally:
        brain._DL.update({'active': False, 'pct': None, 'note': None})
