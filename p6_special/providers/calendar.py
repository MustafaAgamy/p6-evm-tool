"""Calendar & Weather provider.

Parse-free: calendar audit from ``ctx.calendar`` (db.get_calendar_audit) and the
weather estimate from ``ctx.weather`` (project_settings 'last_weather'). Weather
is only present once the user has set a project location in Calendar Audit.
"""
from p6_special import payloads as P
from p6_special import fmt
from p6_special.registry import Item
from p6_special.providers import _util as U

FEATURE = 'calendar'
FEATURE_TITLE = 'Calendar & Weather'


def _cal_ready(ctx):
    return 'ready' if ctx.calendar else 'no_data'


def _weather_ready(ctx):
    return 'ready' if ctx.weather else 'no_data'


def _summary(ctx):
    return U.kpi_from_dict((ctx.calendar or {}).get('dashboard') or {})


def _exceptions(ctx):
    exc = (ctx.calendar or {}).get('exceptions')
    if isinstance(exc, list):
        return U.table_from_dicts(exc)
    if isinstance(exc, dict):
        # a dict of category -> list; flatten to labelled rows
        rows = []
        for cat, lst in exc.items():
            if isinstance(lst, list):
                for e in lst:
                    if isinstance(e, dict):
                        rows.append({'category': cat, **{k: v for k, v in e.items()
                                                         if isinstance(v, (int, float, str))}})
        return U.table_from_dicts(rows) if rows else P.NO_DATA
    return P.NO_DATA


def _comparison(ctx):
    return U.table_from_dicts((ctx.calendar or {}).get('comparison') or [])


def _conflicts(ctx):
    c = (ctx.calendar or {}).get('conflicts')
    if isinstance(c, list) and c and isinstance(c[0], dict):
        return U.table_from_dicts(c)
    return P.NO_DATA


def _conclusion(ctx):
    txt = (ctx.calendar or {}).get('conclusion')
    return P.text(txt) if txt else P.NO_DATA


def _weather(ctx):
    w = ctx.weather
    if not w:
        return P.NO_DATA
    delay = w.get('net_finish_delay')
    items = [
        P.kpi('Bad-weather days', fmt.num(w.get('expected_bad_days_total')), tone='warn'),
        P.kpi('Weather delay', fmt.days(delay),
              tone='bad' if (delay or 0) > 0 else 'good'),
        P.kpi('Weather-adjusted finish', str(w.get('weather_adjusted_finish') or '—')),
    ]
    blocks = [P.kpi_group(items)]
    if w.get('conclusion'):
        blocks.append(P.text(w['conclusion']))
    return P.group(blocks)


def provide(ctx):
    R = _cal_ready
    return [
        Item('calendar:summary', FEATURE, FEATURE_TITLE, 'Calendar summary', 'kpi', _summary, R),
        Item('calendar:exceptions', FEATURE, FEATURE_TITLE, 'Calendar exceptions (holidays / shutdowns)', 'table', _exceptions, R),
        Item('calendar:comparison', FEATURE, FEATURE_TITLE, 'Calendar comparison', 'table', _comparison, R),
        Item('calendar:conflicts', FEATURE, FEATURE_TITLE, 'Calendar conflicts', 'table', _conflicts, R),
        Item('calendar:conclusion', FEATURE, FEATURE_TITLE, 'Calendar conclusion', 'text', _conclusion, R),
        Item('weather:impact', FEATURE, FEATURE_TITLE, 'Weather impact', 'kpi', _weather, _weather_ready),
    ]
