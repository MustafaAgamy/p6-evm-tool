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

# Ibrahim's stop-work rule (tunable per project in the app): a day is a lost
# construction day when it is dusty OR rainy OR hot (>= 42 C). Wind is OFF by
# default (set a number to enable it).
DEFAULT_THRESHOLDS = {
    'rain_mm': 5.0,       # a rainy day that stops outdoor work (light drizzle < 5mm ignored)
    'temp_max_c': 42.0,   # heat that stops work
    'wind_kmh': None,     # None = wind not counted; set a km/h to enable crane/height stops
    'dust': True,         # count dust / sandstorm days
}
_DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
_MON = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# ── Site-type presets ────────────────────────────────────────────────────────
# One pick loads the stop-work limits that fit that kind of work. Different jobs
# stop for different weather — the built-in default is desert-tuned (heat/dust,
# wind off), which reads a wind-driven coastal PORT as weather-free. The DESERT
# preset is byte-for-byte DEFAULT_THRESHOLDS, so a project that never picks a type
# behaves exactly as before. Mirrored in ui/modules/calendar.js (SITE_TYPES) for
# the picker; keep the two in sync (tests guard the numbers on each side).
SITE_TYPES = {
    'desert': {
        'label': 'Desert / inland civil',
        'blurb': 'Heat and dust drive stoppages; wind rarely halts inland civil work. (Today’s default.)',
        'thresholds': {'rain_mm': 5.0, 'temp_max_c': 42.0, 'wind_kmh': None, 'dust': True},
    },
    'marine': {
        'label': 'Marine / Port',
        'blurb': 'Cranes and marine works stop for high wind — the main weather risk for a port / terminal.',
        'thresholds': {'rain_mm': 5.0, 'temp_max_c': 40.0, 'wind_kmh': 35.0, 'dust': True},
    },
    'coastal': {
        'label': 'Coastal / general',
        'blurb': 'A mix of wind and rain; heat reaches the limit less often than inland.',
        'thresholds': {'rain_mm': 5.0, 'temp_max_c': 42.0, 'wind_kmh': 40.0, 'dust': True},
    },
    'building': {
        'label': 'Building / enclosed',
        'blurb': 'Least weather-exposed once enclosed; only heavy rain or extreme heat stops work.',
        'thresholds': {'rain_mm': 10.0, 'temp_max_c': 45.0, 'wind_kmh': None, 'dust': False},
    },
}
_THR_KEYS = ('rain_mm', 'temp_max_c', 'wind_kmh', 'dust')


def _limit_explanations(site_type):
    """Plain-language 'what work each limit stops', shown in full to the user and in
    the PDF. Wind is framed for marine work; the rest are generic."""
    marine = site_type == 'marine'
    return {
        'wind': ('High wind stops crane lifts, tower-crane and marine works'
                 if marine else 'High wind stops crane lifts and work at height'),
        'heat': 'Extreme heat halts outdoor labour',
        'rain': 'Work-stopping rain (light drizzle below the limit is ignored)',
        'dust': 'Sandstorm days (near-term air-quality PM10) counted as a lost day',
    }


def resolve_site_thresholds(site_type, overrides=None):
    """Stop-work limits for a site type, with any explicit per-limit edits applied on top.
    Unknown / None site_type → DEFAULT_THRESHOLDS (today's desert behaviour, unchanged).
    Always returns a fresh dict (never the shared catalog object)."""
    base = (SITE_TYPES.get(site_type) or {}).get('thresholds')
    out = dict(base if base is not None else DEFAULT_THRESHOLDS)
    if overrides:
        out.update({k: v for k, v in overrides.items() if k in _THR_KEYS})
    return out


def build_criteria(site_type, thresholds):
    """The 'criteria in full' rows — one per limit with its value, on/off state and the
    plain reason it stops work. Reflects the ACTUAL thresholds, so an edited 'Custom'
    set still shows true limits. Single source for the on-screen panel and the PDF.
    Order is wind → heat → rain → dust (wind first: the dominant driver on a port)."""
    t = thresholds or DEFAULT_THRESHOLDS
    ex = _limit_explanations(site_type)

    def numrow(key, icon, label, thr_key, unit, expl):
        v = t.get(thr_key)
        on = v is not None
        return {'key': key, 'icon': icon, 'label': label,
                'value': (f'≥ {v:g} {unit}' if on else 'off'),
                'on': on, 'explain': expl}

    return [
        numrow('wind', '\U0001F4A8', 'Wind', 'wind_kmh', 'km/h', ex['wind']),
        numrow('heat', '\U0001F321', 'Heat', 'temp_max_c', '°C', ex['heat']),
        numrow('rain', '\U0001F327', 'Rain', 'rain_mm', 'mm', ex['rain']),
        {'key': 'dust', 'icon': '\U0001F32B', 'label': 'Dust / sandstorm',
         'value': ('on' if t.get('dust', True) else 'off'),
         'on': bool(t.get('dust', True)), 'explain': ex['dust']},
    ]


def limit_performance(daily_weather, data_date, project_finish, thresholds):
    """Explain-the-result: for each limit, how many days it flagged over the window and
    the PEAK measured value seen — so a near-zero is never a silent black box
    ('heat limit never reached — peak 41.3 °C'). Pure; window is (data_date, finish]."""
    t = thresholds or DEFAULT_THRESHOLDS
    dd, pf = _to_date(data_date), _to_date(project_finish)
    window = [r for d, r in (daily_weather or {}).items()
              if (dd is None or d > dd) and (pf is None or d <= pf)]

    def peak(key):
        vals = [float(r.get(key) or 0) for r in window]
        return round(max(vals), 1) if vals else None

    def numperf(key, label, thr_key, meas_key, unit):
        lim = t.get(thr_key)
        on = lim is not None
        flagged = sum(1 for r in window if on and float(r.get(meas_key) or 0) >= lim)
        return {'key': key, 'label': label, 'on': on, 'limit': lim, 'unit': unit,
                'flagged': flagged, 'peak': peak(meas_key)}

    dust_on = bool(t.get('dust', True))
    return [
        numperf('wind', 'Wind', 'wind_kmh', 'wind_kmh', 'km/h'),
        numperf('heat', 'Heat', 'temp_max_c', 'temp_max_c', '°C'),
        numperf('rain', 'Rain', 'rain_mm', 'rain_mm', 'mm'),
        {'key': 'dust', 'label': 'Dust / sandstorm', 'on': dust_on, 'limit': None,
         'unit': None, 'flagged': sum(1 for r in window if dust_on and r.get('dust')),
         'peak': None},
    ]


# ── classification ───────────────────────────────────────────────────────────

def classify_day(rec, thresholds=None):
    """(is_bad, label, detail) for one daily record (rain_mm / temp_max_c / wind_kmh / dust).
    `detail` states WHY, with the measured value vs the limit — e.g.
    '🌡 45.5 °C ≥ 42 °C' — so every flagged day is verifiable. Wind is only
    tested when its threshold is a number (None = off)."""
    t = thresholds or DEFAULT_THRESHOLDS
    labels, details = [], []
    rain = float(rec.get('rain_mm') or 0)
    rain_thr = t.get('rain_mm', DEFAULT_THRESHOLDS['rain_mm'])
    if rain_thr is not None and rain >= rain_thr:
        labels.append('Rain'); details.append(f'🌧 {rain:g} mm ≥ {rain_thr:g} mm')
    if t.get('dust', True) and rec.get('dust'):
        pm = rec.get('pm10'); vis = rec.get('visibility_km')
        extra = (f' · PM10 {pm:g}' if pm else '') + (f' · visibility {vis:g} km' if vis else '')
        labels.append('Dust storm'); details.append(f'🌫 Dust storm{extra}')
    temp = float(rec.get('temp_max_c') or 0)
    temp_thr = t.get('temp_max_c', DEFAULT_THRESHOLDS['temp_max_c'])
    if temp_thr is not None and temp >= temp_thr:
        labels.append('Heat'); details.append(f'🌡 {temp:g} °C ≥ {temp_thr:g} °C')
    wind = float(rec.get('wind_kmh') or 0)
    wind_thr = t.get('wind_kmh')
    if wind_thr is not None and wind >= wind_thr:
        labels.append('High wind'); details.append(f'💨 {wind:g} km/h ≥ {wind_thr:g} km/h')
    return (bool(labels), ' / '.join(labels), ' · '.join(details))


def bad_weather_days(daily_weather, thresholds=None):
    """{date: detail} for every day that classifies as bad weather, where `detail`
    is the measured reason (value vs limit) so each day is verifiable."""
    out = {}
    for d, rec in (daily_weather or {}).items():
        is_bad, label, detail = classify_day(rec, thresholds)
        if is_bad:
            out[d] = detail or label
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


_ALL_WEEK = {'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'}


def _is_degenerate(cal):
    """A calendar whose standard week has NO working day (e.g. a 24-hour continuous
    calendar parsed as all-days-off) — is_working_day is always False, so it must never
    be the reference calendar or every bad-weather day looks 'non-working'."""
    nwd = set(getattr(cal, 'nonworking_days', set()) or set())
    return nwd >= _ALL_WEEK


def _pick_primary(calendars, con_ids, counts):
    """The single reference construction calendar: the DOMINANT valid one (most
    construction activities), preferring non-degenerate calendars, chosen deterministically
    (never by set-iteration order — that arbitrariness caused the day-list/finish/milestone
    contradiction on multi-calendar schedules)."""
    valid = [c for c in con_ids if c in calendars]
    if not valid:
        return None
    counts = counts or {}

    def key(cid):
        cal = calendars[cid]
        return (1 if _is_degenerate(cal) else 0,          # non-degenerate first
                -counts.get(cid, 0),                       # then most construction activities
                0 if getattr(cal, 'is_default', False) else 1,
                str(cid))                                  # stable final tie-break
    return sorted(valid, key=key)[0]


def weather_impact(*, calendars, construction_cal_ids, milestones, data_date,
                   project_finish, daily_weather, forecast_horizon,
                   thresholds=None, config=None, construction_activities=None,
                   site_type=None, construction_cal_counts=None,
                   climate_samples=None, climate_years=5, climate_meta=None):
    thresholds = thresholds or DEFAULT_THRESHOLDS
    data_date = _to_date(data_date)
    project_finish = _to_date(project_finish)
    forecast_horizon = _to_date(forecast_horizon) if forecast_horizon else data_date
    con_ids = [c for c in construction_cal_ids if c in calendars]
    # ONE reference construction calendar drives the day-list, the finish AND every
    # milestone, so the three never disagree. Pick the DOMINANT valid calendar (most
    # construction activities), skipping any degenerate all-days-off / 24h-continuous
    # calendar — using that as the reference made every bad day look "non-working" and
    # hid the real slip (the bug Ibrahim hit on the grain terminal).
    primary_con = _pick_primary(calendars, con_ids, construction_cal_counts)
    primary_cal = calendars.get(primary_con) if primary_con else None

    # Flag bad-weather days. NEAR-TERM (≤ forecast horizon) uses the live forecast; BEYOND
    # that, the estimate is grounded in MULTI-YEAR CLIMATE HISTORY (not one possibly-freak
    # year): we look across the last N years and drive the day-list from a REPRESENTATIVE
    # (typical) year — the one whose bad-day count is closest to the N-year average — and
    # report the N-year average + range per month. A strict exact-date match drastically
    # undercounts scattered wind/rain (it rarely repeats on the same date), so a typical
    # year is used instead (Ibrahim, Option A).
    has_climate = bool(climate_samples)
    flagged = {}
    for d, rec in (daily_weather or {}).items():
        if not (data_date < d <= project_finish):
            continue
        if has_climate and d > forecast_horizon:      # beyond-horizon comes from the climate history
            continue
        is_bad, label, detail = classify_day(rec, thresholds)
        if is_bad:
            flagged[d] = {'detail': detail or label, 'label': label,
                          'confidence': 'forecast' if d <= forecast_horizon else 'expected'}

    # Per-year bad-day sets over the whole window (for the representative year + monthly stats).
    years_seen = set()
    for s in (climate_samples or {}).values():
        years_seen.update(s.keys())
    years_list = sorted(years_seen)
    year_bad = {y: set() for y in years_list}      # {year: {dates bad that year}}
    for d, s in (climate_samples or {}).items():
        if not (data_date < d <= project_finish):
            continue
        for y, rec in s.items():
            if classify_day(rec, thresholds)[0]:
                year_bad[y].add(d)
    counts_by_year = {y: len(year_bad[y]) for y in years_list}
    climate_avg_total = (round(sum(counts_by_year.values()) / len(years_list))
                         if years_list else 0)
    rep_year = None
    if years_list:
        mean = sum(counts_by_year.values()) / len(years_list)
        rep_year = min(years_list, key=lambda y: (abs(counts_by_year[y] - mean), -y))

    # Representative year's bad days BEYOND the forecast horizon (near-term already covered).
    if rep_year is not None:
        for d in sorted(year_bad[rep_year]):
            if d > forecast_horizon and d not in flagged:
                _, lb, dt = classify_day(climate_samples[d][rep_year], thresholds)
                flagged[d] = {'detail': dt or lb, 'label': lb, 'confidence': 'expected'}

    remaining = flagged
    # Lost construction days = bad days landing on a WORKING day of the reference calendar.
    # Days already off (weekend / holiday / shutdown) carry no impact, so they never move a
    # milestone or trigger a recovery option (Ibrahim's rule).
    lost = {d for d in remaining if primary_cal and primary_cal.is_working_day(d)}

    # Milestones — same reference calendar as the finish, so a milestone can never show a
    # slip the headline finish doesn't (and vice-versa).
    ms = []
    for m in milestones:
        mdate = _to_date(m['date'])
        before = sum(1 for d in remaining if d <= mdate)
        net = sum(1 for d in lost if d <= mdate)
        ms.append({
            'name': m['name'], 'planned': mdate.isoformat(),
            'bad_days_before': before, 'already_allowed': before - net,
            'net_delay': net,
            'adjusted': _shift_working_days(primary_cal, mdate, net).isoformat(),
        })

    net_finish = len(lost)   # every lost day is within (data_date, project_finish]
    adjusted_finish = _shift_working_days(primary_cal, project_finish, net_finish)

    # Breakdown of the flagged days by cause (a day can hit more than one limit,
    # so the counts can sum to more than the day total).
    cause_count = {'Rain': 0, 'Heat': 0, 'Dust storm': 0, 'High wind': 0}
    for d in remaining:
        for part in (remaining[d].get('label') or '').split(' / '):
            if part in cause_count:
                cause_count[part] += 1
    by_cause = [
        {'label': 'Heat', 'count': cause_count['Heat']},
        {'label': 'Dust', 'count': cause_count['Dust storm']},
        {'label': 'Rain', 'count': cause_count['Rain']},
        {'label': 'Wind', 'count': cause_count['High wind'],
         'off': thresholds.get('wind_kmh') is None},
    ]

    # Daily expected list (forecast ≤ horizon, else historical-expected). Each working
    # bad-day also names the construction activities planned across that date (#07).
    con_act = construction_activities or []
    day_hours = primary_cal.day_hours if primary_cal else 8.0
    bad_list = []
    for d in sorted(remaining):
        working = d in lost
        # Brief by WBS / work package, de-duplicated (Ibrahim's rule): all the pile
        # activities under "Pile Works" show as "Pile Works" once, not one row each.
        wbs_brief = []
        if working:
            seen = set()
            for a in con_act:
                if a.get('start') and a['start'] <= d <= (a.get('finish') or a['start']):
                    label = (a.get('wbs') or a.get('name') or '').strip()
                    if label and label not in seen:
                        seen.add(label)
                        wbs_brief.append(label)
        meta = remaining[d]
        bad_list.append({
            'date': d.isoformat(), 'day_name': _DAY_NAMES[d.weekday()],
            'condition': meta['detail'],
            'confidence': meta.get('confidence', 'expected'),
            'effect': 'Non-working (construction)' if working else 'Falls on a non-working day',
            'activities': wbs_brief,          # every affected WBS (de-duplicated), not capped
            'activities_count': len(wbs_brief),
        })

    # Monthly bad-weather days. With climate history: the N-year AVERAGE per month plus the
    # range (fewest–most across those years). Without it (unit tests): a plain count of the
    # flagged days.
    if years_list:
        month_year = {}
        for y in years_list:
            for d in year_bad[y]:
                month_year.setdefault((d.year, d.month), {yy: 0 for yy in years_list})[y] += 1
        monthly = []
        for (y, m) in sorted(month_year):
            vals = list(month_year[(y, m)].values())
            avg = sum(vals) / len(vals) if vals else 0
            monthly.append({'label': f'{_MON[m]} {y}', 'count': round(avg),
                            'avg': round(avg, 1), 'lo': min(vals), 'hi': max(vals)})
    else:
        monthly_map = {}
        for d in remaining:
            monthly_map[(d.year, d.month)] = monthly_map.get((d.year, d.month), 0) + 1
        monthly = [{'label': f'{_MON[m]} {y}', 'count': c, 'avg': c, 'lo': c, 'hi': c}
                   for (y, m), c in sorted(monthly_map.items())]

    # 3-colour histogram per month (Feature 2 — Bad Weather tab): from the data date onward,
    # each month's NET working days (green), the working days lost to weather (amber) and the
    # non-working days (red). net = working days − weather-lost days; bar = calendar days.
    hcount = {}
    hd = data_date + timedelta(days=1)
    while hd <= project_finish:
        h = hcount.setdefault((hd.year, hd.month), {'working': 0, 'nonworking': 0, 'lost': 0})
        if primary_cal and primary_cal.is_working_day(hd):
            h['working'] += 1
            if hd in lost:
                h['lost'] += 1
        else:
            h['nonworking'] += 1
        hd += timedelta(days=1)
    histogram = [{'label': f'{_MON[m]} {y}',
                  'net': hcount[(y, m)]['working'] - hcount[(y, m)]['lost'],
                  'bad': hcount[(y, m)]['lost'],
                  'nonworking': hcount[(y, m)]['nonworking'],
                  'working': hcount[(y, m)]['working']}
                 for (y, m) in sorted(hcount)]

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

    conclusion = _weather_conclusion(
        total=len(remaining), net=net_finish, adjusted=adjusted_finish,
        by_cause=by_cause, monthly=monthly, milestones=ms)

    # For the "why this result" panel, fold the multi-year climate into a single per-date view
    # (the worst value seen across the years), so peaks like "hottest expected day" are real.
    daily_eff = dict(daily_weather or {})
    for d, samples in (climate_samples or {}).items():
        recs = list(samples.values())
        if d in daily_eff or not recs:
            continue
        daily_eff[d] = {
            'rain_mm': max((float(r.get('rain_mm') or 0) for r in recs), default=0.0),
            'temp_max_c': max((float(r.get('temp_max_c') or 0) for r in recs), default=0.0),
            'wind_kmh': max((float(r.get('wind_kmh') or 0) for r in recs), default=0.0),
        }

    meta = climate_meta or {}
    return {
        'bad_days': bad_list,
        'monthly': monthly,
        'histogram': histogram,      # per-month net / bad-weather / non-working days (Feature 2)
        'by_cause': by_cause,
        'milestones': ms,
        'expected_bad_days_total': len(remaining),
        'climate_avg_total': climate_avg_total,   # N-year average bad days over the window
        'net_finish_delay': net_finish,
        'weather_adjusted_finish': adjusted_finish.isoformat(),
        'recovery': recovery,
        'conclusion': conclusion,
        'thresholds': thresholds,          # the stop-work limits applied
        'site_type': site_type,            # the chosen site type (None = today's default)
        'site_type_label': (SITE_TYPES.get(site_type) or {}).get('label'),
        'criteria': build_criteria(site_type, thresholds),          # shown in full (screen + PDF)
        'limit_performance': limit_performance(daily_eff, data_date, project_finish, thresholds),
        # Where the numbers come from (shown to the user + in the PDF); the server adds location.
        'climate_reference': {
            'history_source': 'Open-Meteo ERA5 reanalysis',
            'history_url': 'archive-api.open-meteo.com',
            'forecast_source': 'Open-Meteo', 'forecast_url': 'open-meteo.com',
            'dust_source': 'Open-Meteo Air-Quality',
            'years': len(years_list) or climate_years,
            'year_start': meta.get('year_start'), 'year_end': meta.get('year_end'),
            'representative_year': rep_year, 'avg_total': climate_avg_total,
        },
        'from_date': data_date.isoformat(),  # the update's cutoff — window is (cutoff, finish]
        'source': 'Open-Meteo (forecast + ERA5 historical + air-quality)',
        'is_estimate': True,
    }


def _fmt_long(d):
    d = _to_date(d)
    return f'{d.day:02d} {_MON[d.month]} {d.year}' if d else '—'


def _weather_conclusion(*, total, net, adjusted, by_cause, monthly, milestones):
    """A short management paragraph, generated from the numbers — mirrors what the
    UI and PDF show. Degrades gracefully when there is no impact / no location."""
    if total == 0:
        return ('No material bad-weather days are expected on the remaining construction '
                'path to finish, so no weather delay is estimated. This is a forward-looking '
                'estimate, kept separate from the exact P6 Delay.')
    if net > 0:
        finish_txt = (f'Bad weather is estimated to cost about {net} working '
                      f'day{"s" if net != 1 else ""} to project finish, moving the '
                      f'weather-adjusted finish to {_fmt_long(adjusted)}.')
    else:
        finish_txt = ('The flagged bad-weather days fall on days already off (weekend / '
                      'holiday / shutdown), so no net delay to the project finish is estimated.')
    ranked = sorted([c for c in by_cause if c.get('count')], key=lambda c: -c['count'])
    dom_txt = ''
    if ranked:
        pct = round(ranked[0]['count'] / total * 100)
        dom_txt = f' The risk is driven mainly by {ranked[0]["label"].lower()} ({pct}% of the flagged days).'
    peak_txt = ''
    if monthly:
        mx = max(m['count'] for m in monthly)
        peaks = [m['label'] for m in monthly if m['count'] == mx and mx > 0]
        if peaks:
            peak_txt = f' Exposure concentrates around {", ".join(peaks[:2])}.'
    slipped = [m for m in milestones if m['net_delay'] > 0]
    ms_txt = ''
    if slipped:
        worst = max(slipped, key=lambda m: m['net_delay'])
        ms_txt = (f' {len(slipped)} milestone{"s" if len(slipped) != 1 else ""} '
                  f'exposed, the largest being “{worst["name"]}” (+{worst["net_delay"]} d).')
    return (finish_txt + dom_txt + peak_txt + ms_txt +
            ' This is a forward-looking estimate, kept separate from the exact P6 Delay.')


def weather_inputs(data):
    """Derive the schedule-side inputs weather_impact needs, from a parsed ScheduleData:
    construction calendars (activities whose WBS phase means 'Construction'), milestone
    activities, the data date and the project finish. Pure (no network)."""
    from p6_evm.classify import build_wbs_classifier, classify_wbs_name
    from p6_evm.metrics import wbs_ancestor_names
    classify = build_wbs_classifier(data)

    construction_cal_ids = set()
    construction_cal_counts = {}          # {cal_id: # real construction activities on it}
    construction_activities = []
    for a in data.activities.values():
        anc = wbs_ancestor_names(a.get('wbs_id'), data.wbs)   # nearest named WBS first, up to root
        if classify_wbs_name(classify(anc)) != 'Construction':
            continue
        cid = a.get('calendar_id')
        if cid and cid in data.calendars:
            construction_cal_ids.add(cid)
        # Real construction work (not milestones) — for the per-day "affected work" brief.
        if a.get('task_type') in ('StartMilestone', 'FinishMilestone'):
            continue
        # The reference calendar is the one MOST construction activities are assigned to
        # (Ibrahim's rule), so count real activities per calendar.
        if cid and cid in data.calendars:
            construction_cal_counts[cid] = construction_cal_counts.get(cid, 0) + 1
        s = _to_date(a.get('planned_start'))
        if s:
            # Brief by the NEAREST NAMED WBS / work package (P6 often leaves the activity's
            # direct WBS node unnamed, so anc[0] is the meaningful "Pile Works" level, not the
            # activity). Falls back to the activity name only when there is no named WBS at all.
            construction_activities.append({
                'name': a.get('name') or a.get('id'),
                'start': s, 'finish': _to_date(a.get('planned_finish')) or s,
                'wbs': anc[0] if anc else ''})

    # Only FINISH / completion milestones — a completion date is what weather pushes
    # (Ibrahim's rule: impact on all finish/completion milestones only).
    milestones = []
    for a in data.activities.values():
        if a.get('task_type') == 'FinishMilestone':
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
        'construction_cal_counts': construction_cal_counts,
        'construction_activities': construction_activities,
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


def build_daily_weather(lat, lon, data_date, project_finish, today=None, years=5):
    """Assemble the weather the estimate runs on:
      * near term (≤ ~16 days from today) → live FORECAST → `daily` {date: rec}
      * beyond the forecast → MULTI-YEAR CLIMATE HISTORY: the same calendar date across the
        last `years` full years of recorded weather (Open-Meteo ERA5), so a single freak
        year can't skew it → `climate_samples` {future_date: [rec, rec, ...]}.
    Returns (daily, climate_samples, forecast_horizon, climate_meta). Network failures
    degrade to empty dicts (offline-safe). climate_meta = {years, year_start, year_end}.
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

    # Multi-year climate for the WHOLE remaining window (so the monthly averages are complete):
    # for each future date, the same calendar date across the last `years` FULL calendar years
    # before the run starts, keyed by year → {future_date: {year: rec}}. Using full years (not
    # a span that bleeds into partial ones) keeps every date's sample count equal to `years`,
    # so the average/range and the "last N years" reference are honest.
    climate_samples = {}
    climate_meta = {'years': years, 'year_start': None, 'year_end': None}
    if project_finish > horizon:
        fut_start = data_date + timedelta(days=1)
        # First future date for each (month, day) in the remaining window.
        fut_by_md = {}
        d = fut_start
        while d <= project_finish:
            fut_by_md.setdefault((d.month, d.day), d)
            d += timedelta(days=1)
        # The `years` full calendar years ending just before the run begins.
        end_year = fut_start.year - 1
        start_year = end_year - years + 1
        # One archive call over those full years, then bucket each historical day onto its
        # matching future date by (month, day) → every date gets exactly `years` samples.
        hist = fetch_historical(lat, lon, date(start_year, 1, 1), date(end_year, 12, 31))
        for hd, rec in hist.items():
            fd = fut_by_md.get((hd.month, hd.day))
            if fd is not None and start_year <= hd.year <= end_year:
                climate_samples.setdefault(fd, {})[hd.year] = rec
        if hist:
            climate_meta['year_start'] = start_year
            climate_meta['year_end'] = end_year

    # Dust / sandstorm days for the near-term window (air-quality forecast), merged in.
    for d, aq in fetch_air_quality(lat, lon).items():
        if d in daily and aq.get('dust'):
            daily[d].update(aq)
    return daily, climate_samples, horizon, climate_meta


_AIR_QUALITY = 'https://air-quality-api.open-meteo.com/v1/air-quality'
DUST_PM10_THRESHOLD = 150.0   # µg/m³ daily-max → treat as a dust/sandstorm day


def fetch_air_quality(lat, lon):
    """Near-term dust from Open-Meteo air-quality (free). {date: {dust, pm10}}; {} on failure.
    A day counts as dust when its peak PM10 reaches DUST_PM10_THRESHOLD."""
    try:
        url = (f'{_AIR_QUALITY}?latitude={lat}&longitude={lon}'
               f'&hourly=pm10,dust&timezone=auto&forecast_days=5')
        payload = _get_json(url)
        hourly = (payload or {}).get('hourly') or {}
        times = hourly.get('time') or []
        pm10 = hourly.get('pm10') or []
        dust = hourly.get('dust') or []
        by_day = {}
        for i, t in enumerate(times):
            d = datetime.fromisoformat(t).date()
            p = pm10[i] if i < len(pm10) and pm10[i] is not None else 0.0
            du = dust[i] if i < len(dust) and dust[i] is not None else 0.0
            cur = by_day.setdefault(d, {'pm10': 0.0, 'dust_conc': 0.0})
            cur['pm10'] = max(cur['pm10'], p)
            cur['dust_conc'] = max(cur['dust_conc'], du)
        out = {}
        for d, v in by_day.items():
            if v['pm10'] >= DUST_PM10_THRESHOLD or v['dust_conc'] >= DUST_PM10_THRESHOLD:
                out[d] = {'dust': True, 'pm10': round(v['pm10'])}
        return out
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
        return {}


def _shift_year(d, delta):
    try:
        return d.replace(year=d.year + delta)
    except ValueError:      # 29 Feb → 28 Feb
        return d.replace(year=d.year + delta, day=28)
