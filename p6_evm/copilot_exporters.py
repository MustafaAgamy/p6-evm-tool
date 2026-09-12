"""AI Copilot · TIA — Excel exporter.

Mirrors the on-screen / PDF report's deterministic core — the two printable
sections `copilotPrint()` emits (Time-Impact Analysis + prioritised Copilot
insights) — as titled tables stacked on one sheet via `write_sections_xlsx`,
matching the screen layout rather than a flat dump.

Computes nothing: it only formats the copilot report dict that `build_copilot()`
produced — `{'tia': {...}, 'insights': [...], 'has_forecast': bool}`. Every input
is guarded; empty/missing data yields a "No data" row, never a crash.
"""
from datetime import datetime

_SEV_LABEL = {'high': 'High', 'med': 'Medium', 'low': 'Low'}
_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# Three stacked tables, in the same order the screen shows them.
_FORECAST_HEADERS = ['Finish', 'Date', 'Slip vs baseline (days)']
_DRIVER_HEADERS = ['Component', 'Impact (days)', 'Basis']
_INSIGHT_HEADERS = ['Severity', 'Insight', 'Recommended action']


def _fdate(iso):
    """ISO date → '09-Feb.2027' (matches the update/period exporters)."""
    if not iso:
        return '—'
    try:
        d = datetime.strptime(str(iso)[:10], '%Y-%m-%d')
        return f'{d.day:02d}-{_MONTHS[d.month - 1]}.{d.year}'
    except Exception:
        return str(iso)


def _slip(v):
    """Keep the slip numeric so Excel can sort/sum it; blank when unknown."""
    return v if isinstance(v, (int, float)) else ''


def _total_note(total):
    if not isinstance(total, (int, float)):
        return None
    return f'Total impact {("+%d" % total) if total > 0 else str(total)} d — the finish slip decomposed below.'


def copilot_excel(report):
    """Copilot report dict → `sheets` for `write_sections_xlsx`.

    One sheet, three stacked titled tables mirroring the screen:
      1. Time-Impact Analysis — the finish-forecast summary (baseline → likely →
         worst case) with slip in days.
      2. What's driving the slip — the TIA component decomposition.
      3. Copilot insights — most severe first, each with its recommended action.
    """
    report = report or {}
    tia = report.get('tia') or {}
    comps = tia.get('components') or []
    insights = report.get('insights') or []

    # 1 · Time-Impact Analysis — the finish-forecast summary.
    forecast_rows = [
        ['Baseline finish', _fdate(tia.get('baseline_finish')), ''],
        ['Current forecast finish (best case)', _fdate(tia.get('forecast_finish')), ''],
        ['Likely finish (SPI continues)', _fdate(tia.get('likely_finish')), _slip(tia.get('likely_slip'))],
        ['Worst case (+ expected weather)', _fdate(tia.get('worst_finish')), _slip(tia.get('worst_slip'))],
    ]
    forecast_block = {'title': 'Time-Impact Analysis', 'headers': _FORECAST_HEADERS, 'rows': forecast_rows}
    note = _total_note(tia.get('likely_slip'))
    if note:
        forecast_block['note'] = note

    # 2 · What's driving the slip — the TIA components.
    if comps:
        driver_rows = [[c.get('label', ''), _slip(c.get('days')), c.get('basis', '')] for c in comps]
    else:
        driver_rows = [['No finish forecast — needs a finish milestone and a baseline '
                        'for a Time-Impact Analysis.', '', '']]
    driver_block = {'title': "What's driving the slip", 'headers': _DRIVER_HEADERS, 'rows': driver_rows}

    # 3 · Copilot insights — most severe first (as sorted by build_copilot).
    if insights:
        insight_rows = [[_SEV_LABEL.get(i.get('severity'), ''), i.get('title', ''), i.get('detail', '')]
                        for i in insights]
    else:
        insight_rows = [['', 'No data', 'Import a schedule with metrics to generate copilot insights.']]
    insight_block = {'title': 'Copilot insights', 'headers': _INSIGHT_HEADERS,
                     'rows': insight_rows, 'note': 'Most severe first.'}

    return [{
        'name': 'AI Copilot · TIA',
        'blocks': [forecast_block, driver_block, insight_block],
        'col_widths': {0: 36, 1: 18, 2: 62},
    }]
