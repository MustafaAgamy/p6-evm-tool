"""Bad Weather Run speed (owner comment 36 — no slow wait after Run): the three downloads
run at the same time, and recorded history for full past years is downloaded once."""
import threading
import time
from datetime import date

from p6_calendar import weather as W


def _fake_payload(start, end):
    days = (end - start).days + 1
    times = [date.fromordinal(start.toordinal() + i).isoformat() for i in range(days)]
    return {'daily': {'time': times, 'precipitation_sum': [0.0] * days,
                      'temperature_2m_max': [30.0] * days, 'wind_speed_10m_max': [10.0] * days}}


def _install_fake(monkeypatch, delay=0.3):
    calls = []
    lock = threading.Lock()

    def fake_get_json(url, timeout=20):
        with lock:
            calls.append(url)
        time.sleep(delay)
        if 'archive-api' in url:
            q = dict(p.split('=', 1) for p in url.split('?', 1)[1].split('&'))
            return _fake_payload(date.fromisoformat(q['start_date']), date.fromisoformat(q['end_date']))
        if 'air-quality' in url:
            return {'hourly': {'time': [], 'pm10': [], 'dust': []}}
        return _fake_payload(date(2026, 1, 2), date(2026, 1, 17))

    monkeypatch.setattr(W, '_get_json', fake_get_json)
    monkeypatch.setattr(W, '_HIST_CACHE', {})
    return calls


def test_downloads_run_at_the_same_time(monkeypatch):
    calls = _install_fake(monkeypatch, delay=0.3)
    t = time.perf_counter()
    daily, climate, horizon, meta = W.build_daily_weather(31.26, 32.30, date(2026, 1, 1), date(2026, 12, 31))
    took = time.perf_counter() - t
    assert len(calls) == 3                                   # forecast + history + air quality
    assert took < 0.75, took                                 # ≈ one download, not three in a row
    assert climate and meta['year_start'] == 2021 and meta['year_end'] == 2025
    assert all(len(v) == 5 for v in climate.values())        # every date keeps exactly 5 years


def test_past_history_is_downloaded_once(monkeypatch):
    calls = _install_fake(monkeypatch, delay=0.0)
    a = W.build_daily_weather(31.26, 32.30, date(2026, 1, 1), date(2026, 12, 31))
    b = W.build_daily_weather(31.26, 32.30, date(2026, 1, 1), date(2026, 12, 31))
    assert sum('archive-api' in u for u in calls) == 1       # second Run reads the cache
    assert a[1] == b[1] and a[3] == b[3]                     # …and gets the same climate
    # a different place downloads its own history
    W.build_daily_weather(24.47, 54.37, date(2026, 1, 1), date(2026, 12, 31))
    assert sum('archive-api' in u for u in calls) == 2


def test_failed_history_is_not_cached(monkeypatch):
    calls = _install_fake(monkeypatch, delay=0.0)

    def boom(url, timeout=20):
        calls.append(url)
        raise W.urllib.error.URLError('offline')

    monkeypatch.setattr(W, '_get_json', boom)
    assert W.fetch_historical(31.26, 32.30, date(2021, 1, 1), date(2025, 12, 31)) == {}
    assert W._HIST_CACHE == {}
