"""Update Analysis provider.

Single file, recomputed on demand from the imported schedule (nothing stored):
``data = ctx.parsed()``, ``metrics = ctx.computed()`` ->
``p6_update.analysis.build_report_from_data``. Memoized so it runs once per report.
Percentages here are already on a 0..100 scale (verified in analysis.py).
"""
from p6_special import payloads as P
from p6_special import fmt
from p6_special.registry import Item
from p6_special.providers import _util as U

FEATURE = 'update'
FEATURE_TITLE = 'Update Analysis'


def _ready(ctx):
    return 'ready' if ctx.has_xml() else 'no_data'


def _report(ctx):
    def build():
        data = ctx.parsed()
        if data is None:
            return None
        from p6_update.analysis import build_report_from_data
        return build_report_from_data(data, ctx.computed())
    return ctx.memo('update_report', build)


def _counts(ctx):
    """Planned Activities vs Actual Activities — the flagship item."""
    r = _report(ctx)
    if not r:
        return P.NO_DATA
    c = r.get('counts') or {}
    total = c.get('total') or 0
    blocks = []
    if total:
        pc = 100.0 * (c.get('planned_completed') or 0) / total
        ac = 100.0 * (c.get('actual_completed') or 0) / total
        blocks.append(P.bars(
            rows=[{'label': 'Activities completed',
                   'values': [pc, ac],
                   'display': [f"{c.get('planned_completed', 0)} planned",
                               f"{c.get('actual_completed', 0)} actual"]}],
            series=[{'label': 'Planned to be done', 'tone': 'neutral'},
                    {'label': 'Actually done', 'tone': 'good'}]))
    segs = [
        {'label': 'Completed', 'value': c.get('actual_completed', 0), 'tone': 'good'},
        {'label': 'In progress', 'value': c.get('actual_in_progress', 0), 'tone': 'warn'},
        {'label': 'Not started', 'value': c.get('actual_not_started', 0), 'tone': 'neutral'},
    ]
    blocks.append(P.segbar(segs, note=f'{total} construction activities in total'))
    return P.group(blocks) if blocks else P.NO_DATA


def _time(ctx):
    r = _report(ctx)
    if not r:
        return P.NO_DATA
    ts = r.get('time_status') or {}
    if not ts:
        return P.NO_DATA
    return P.kpi_group([
        P.kpi('Time elapsed', fmt.pct100(ts.get('elapsed_pct'))),
        P.kpi('Planned %', fmt.pct100(ts.get('planned_pct')), tone='accent'),
        P.kpi('Actual %', fmt.pct100(ts.get('actual_pct')), tone='neutral'),
    ])


def _bycode(ctx):
    r = _report(ctx)
    bc = (r or {}).get('by_code')
    if isinstance(bc, list) and bc and isinstance(bc[0], dict):
        return U.table_from_dicts(bc)
    return P.NO_DATA


def _driving(ctx):
    r = _report(ctx)
    cp = (r or {}).get('critical_path') or {}
    head = cp.get('headline')
    ms = cp.get('milestone') or {}
    blocks = []
    if head:
        blocks.append(P.text(head))
    if ms:
        blocks.append(P.keyvals([
            ('Governing milestone', ms.get('name') or ms.get('id') or '—'),
            ('Baseline finish', ms.get('baseline_finish') or '—'),
            ('Forecast finish', ms.get('forecast_finish') or ms.get('finish') or '—'),
        ]))
    return P.group(blocks) if blocks else P.NO_DATA


def _conclusion(ctx):
    r = _report(ctx)
    txt = (r or {}).get('conclusion')
    return P.text(txt) if txt else P.NO_DATA


def provide(ctx):
    R = _ready
    return [
        Item('update:counts', FEATURE, FEATURE_TITLE, 'Planned Activities vs Actual Activities', 'chart', _counts, R),
        Item('update:time', FEATURE, FEATURE_TITLE, 'Time status (planned % / actual %)', 'kpi', _time, R),
        Item('update:bycode', FEATURE, FEATURE_TITLE, 'Planned vs Actual by activity code', 'table', _bycode, R),
        Item('update:driving', FEATURE, FEATURE_TITLE, 'Driving path analyzer', 'text', _driving, R),
        Item('update:conclusion', FEATURE, FEATURE_TITLE, 'Executive read', 'text', _conclusion, R),
    ]
