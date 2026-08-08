"""Weather Impact (Section 10) — estimate how many working days bad weather is
likely to cost the construction path, which milestones slip, and how to recover.

HONEST BY DESIGN:
  * This is a forward-looking ESTIMATE, never mixed into the exact P6 Delay.
  * A true daily forecast only reaches ~16 days; beyond that each day's status
    is "expected" from the location's historical climate for that calendar date.
  * Weather-lost days are applied to the CONSTRUCTION calendars only, and a bad
    day counts only if it falls on a day that calendar was going to work
    (weekends / holidays / shutdowns already off → never double-counted).

The pure functions here are unit-tested with injected weather; all network access
is isolated in fetch_* helpers (Open-Meteo, free / no key) and never unit-tested.
"""
import json
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta

# Sensible construction defaults — tunable later via config.
DEFAULT_THRESHOLDS = {
    'rain_mm': 10.0,      # heavy rain stops pours / earthworks
    'temp_max_c': 45.0,   # extreme heat → midday stoppage
    'wind_kmh': 40.0,     # high wind → no crane lifts / work at height
}
_DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
_MON = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ── classification ───────────────────────────────────────────────────────────

def classify_day(rec, thresholds=None):
    """(is_bad, label) for one daily record: rain_mm / temp_max_c / wind_kmh / dust."""
    t = thresholds or DEFAULT_THRESHOLDS
    labels = []
    if float(rec.get('rain_mm') or 0) >= t.get('rain_mm', DEFAULT_THRESHOLDS['rain_mm']):
        labels.append('Heavy rain')
    if rec.get('dust'):
        labels.append('Dust storm')
    if float(rec.get('temp_max_c') or 0) >= t.get('temp_max_c', DEFAULT_THRESHOLDS['temp_max_c']):
        labels.append('Extreme heat')
    if float(rec.get('wind_kmh') or 0) >= t.get('wind_kmh', DEFAULT_THRESHOLDS['wind_kmh']):
        labels.append('High wind')
    return (bool(labels), ' / '.join(labels))


def bad_weather_days(daily_weather, thresholds=None):
    """{date: label} for every day that classifies as bad weather."""
    out = {}
    for d, rec in (daily_weather or {}).items():
        is_bad, label = classify_day(rec, thresholds)
        if is_bad:
            out[d] = label
    return out


# ── impact ───────────────────────────────────────────────────────────────────

def _to_date(x):
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    try:
        return datetime.fromisoformat(str(x)[:10]).date()
    except ValueError:
        return None


def _shift_working_days(cal, start, n):
    """Return the date n working days after `start` on `cal` (no shift if cal is None)."""
    if not cal or n <= 0:
        return start
    d, added = start, 0
    while added < n:
        d += timedelta(days=1)
        if cal.is_working_day(d):
            added += 1
    return d


def weather_impact(*, calendars, construction_cal_ids, milestones, data_date,
                   project_finish, daily_weather, forecast_horizon,
                   thresholds=None, config=None):
    thresholds = thresholds or DEFAULT_THRESHOLDS
    data_date = _to_date(data_date)
    project_finish = _to_date(project_finish)
    forecast_horizon = _to_date(forecast_horizon) if forecast_horizon else data_date
    con_ids = [c for c in construction_cal_ids if c in calendars]
    primary_con = con_ids[0] if con_ids else None
    primary_cal = calendars.get(primary_con) if primary_con else None

    bad = bad_weather_days(daily_weather, thresholds)
    remaining = {d: lbl for d, lbl in bad.items() if data_date < d <= project_finish}

    def counts(cal, upto):
        total = net = 0
        for d in remaining:
            if d <= upto:
                total += 1
                if cal and cal.is_working_day(d):
                    net += 1
        return total, net

    # Milestones (weather affects construction; a non-construction milestone still
    # inherits delay from the construction path via the primary construction calendar).
    ms = []
    for m in milestones:
        mdate = _to_date(m['date'])
        cal = calendars.get(m.get('cal_id')) if m.get('cal_id') in construction_cal_ids else None
        eff = cal or (primary_cal if con_ids else None)
        total, net = counts(eff, mdate)
        ms.append({
            'name': m['name'], 'planned': mdate.isoformat(),
            'bad_days_before': total, 'already_allowed': total - net,
            'net_delay': net,
            'adjusted': _shift_working_days(eff, mdate, net).isoformat(),
        })

    _, net_finish = counts(primary_cal if con_ids else None, project_finish)
    adjusted_finish = _shift_working_days(primary_cal, project_finish, net_finish)

    # Daily expected list (forecast ≤ horizon, else historical-expected)
    day_hours = primary_cal.day_hours if primary_cal else 8.0
    bad_list = []
    for d in sorted(remaining):
        working = bool(primary_cal and primary_cal.is_working_day(d))
        bad_list.append({
            'date': d.isoformat(), 'day_name': _DAY_NAMES[d.weekday()],
            'condition': remaining[d],
            'confidence': 'forecast' if d <= forecast_horizon else 'expected',
            'effect': 'Non-working (construction)' if working else 'Falls on a non-working day',
        })

    # Monthly counts (raw expected bad days per month)
    monthly_map = {}
    for d in remaining:
        key = (d.year, d.month)
        monthly_map[key] = monthly_map.get(key, 0) + 1
    monthly = [{'label': f'{_MON[m]} {y}', 'count': monthly_map[(y, m)]}
               for (y, m) in sorted(monthly_map)]

    # Recovery recommendations (advisory) — per milestone that slips.
    recovery = []
    for m in ms:
        n = m['net_delay']
        if n <= 0:
            continue
        lost_h = n * day_hours
        recovery.append({
            'period': m['name'],
            'days': n,
            'option_longer_days': f'Add ~{lost_h:g} work-hours (longer days / overtime) before "{m["name"]}"',
            'option_extra_days': f'Work {n} extra day(s) (e.g. weekends)',
            'option_shift': 'Add a second shift over the affected weeks',
        })

    return {
        'bad_days': bad_list,
        'monthly': monthly,
        'milestones': ms,
        'expected_bad_days_total': len(remaining),
        'net_finish_delay': net_finish,
        'weather_adjusted_finish': adjusted_finish.isoformat(),
        'recovery': recovery,
        'is_estimate': True,
    }


def weather_inputs(data):
    """Derive the schedule-side inputs weather_impact needs, from a parsed ScheduleData:
    construction calendars (activities whose WBS phase means 'Construction'), milestone
    activities, the data date and the project finish. Pure (no network)."""
    from p6_evm.classify import build_wbs_classifier, classify_wbs_name
    from p6_evm.metrics import wbs_ancestor_names
    classify = build_wbs_classifier(data)

    construction_cal_ids = set()
    for a in data.activities.values():
        phase = classify(wbs_ancestor_names(a.get('wbs_id'), data.wbs))
        if classify_wbs_name(phase) == 'Construction':
            cid = a.get('calendar_id')
            if cid and cid in data.calendars:
                construction_cal_ids.add(cid)

    milestones = []
    for a in data.activities.values():
        if a.get('task_type') in ('FinishMilestone', 'StartMilestone'):
            d = a.get('planned_finish') or a.get('planned_start')
            if d:
                milestones.append({'name': a.get('name') or a.get('id'),
                                   'date': _to_date(d), 'cal_id': a.get('calendar_id')})
    milestones.sort(key=lambda m: m['date'])

    finishes = [_to_date(a['planned_finish']) for a in data.activities.values()
                if a.get('planned_finish')]
    project_finish = (_to_date(data.project.get('scheduled_finish'))
                      or (max(finishes) if finishes else None))
    return {
        'calendars': data.calendars,
        'construction_cal_ids': construction_cal_ids,
        'milestones': milestones,
        'data_date': _to_date(data.project.get('data_date')) if data.project.get('data_date') else None,
        'project_finish': project_finish,
    }


# ── network (Open-Meteo, free / no key) — isolated, not unit-tested ───────────

_ARCHIVE = 'https://archive-api.open-meteo.com/v1/archive'
_FORECAST = 'https://api.open-meteo.com/v1/forecast'
_DAILY_VARS = 'precipitation_sum,temperature_2m_max,wind_speed_10m_max'


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'nPace-CalendarAudit/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _parse_daily(payload):
    """Open-Meteo daily block → {date: {rain_mm, temp_max_c, wind_kmh}}."""
    daily = (payload or {}).get('daily') or {}
    times = daily.get('time') or []
    rain = daily.get('precipitation_sum') or []
    tmax = daily.get('temperature_2m_max') or []
    wind = daily.get('wind_speed_10m_max') or []
    out = {}
    for i, t in enumerate(times):
        d = datetime.fromisoformat(t).date()
        out[d] = {
            'rain_mm': rain[i] if i < len(rain) and rain[i] is not None else 0.0,
            'temp_max_c': tmax[i] if i < len(tmax) and tmax[i] is not None else 0.0,
            'wind_kmh': wind[i] if i < len(wind) and wind[i] is not None else 0.0,
        }
    return out


def fetch_forecast(lat, lon):
    """Next ~16 days of real forecast → {date: rec}. Returns {} on any failure."""
    try:
        url = (f'{_FORECAST}?latitude={lat}&longitude={lon}&daily={_DAILY_VARS}'
               f'&wind_speed_unit=kmh&timezone=auto&forecast_days=16')
        return _parse_daily(_get_json(url))
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
        return {}


def fetch_historical(lat, lon, start, end):
    """Actual daily weather for a PAST [start, end] → {date: rec}. {} on failure."""
    try:
        url = (f'{_ARCHIVE}?latitude={lat}&longitude={lon}'
               f'&start_date={start.isoformat()}&end_date={end.isoformat()}'
               f'&daily={_DAILY_VARS}&wind_speed_unit=kmh&timezone=auto')
        return _parse_daily(_get_json(url))
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
        return {}


def build_daily_weather(lat, lon, data_date, project_finish, today=None):
    """Assemble a {date: rec} across [data_date, project_finish]:
      * near term (≤ ~16 days from today) → live forecast
      * beyond → the SAME calendar dates from the most recent full past year
        (historical climate proxy), remapped onto the future dates.
    Returns (daily_weather, forecast_horizon). Network failures degrade to {}.
    """
    data_date = _to_date(data_date)
    project_finish = _to_date(project_finish)
    today = _to_date(today) if today else data_date
    horizon = min(today + timedelta(days=15), project_finish)

    daily = {}
    fc = fetch_forecast(lat, lon)
    for d, rec in fc.items():
        if data_date < d <= project_finish:
            daily[d] = rec

    # Future beyond the forecast horizon → prior-year actuals for the same dates.
    if project_finish > horizon:
        fut_start = max(horizon + timedelta(days=1), data_date + timedelta(days=1))
        # Use last year's window (shift back 1 year) as the climate proxy.
        hist = fetch_historical(lat, lon,
                                _shift_year(fut_start, -1), _shift_year(project_finish, -1))
        for hd, rec in hist.items():
            fd = _shift_year(hd, +1)
            if fut_start <= fd <= project_finish and fd not in daily:
                daily[fd] = rec
    return daily, horizon


def _shift_year(d, delta):
    try:
        return d.replace(year=d.year + delta)
    except ValueError:      # 29 Feb → 28 Feb
        return d.replace(year=d.year + delta, day=28)
