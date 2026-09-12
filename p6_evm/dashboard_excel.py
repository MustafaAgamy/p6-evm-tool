"""Professional Dashboard Excel exporter.

Turns the dashboard read-model the CLIENT already rendered (the `/api/dashboard`
response — db.get_dashboard) into the `sheets` structure consumed by
`p6_evm.xlsx_writer.write_sections_xlsx`, so the workbook MIRRORS the on-screen
dashboard sections (stacked titled tables) rather than a flat dump.

Read-model shape (db.get_dashboard → server `_handle_dashboard`):
    {
      'ok': True,
      'portfolio': [ {project_id, name, snapshot_id, data_date, imported_at,
                      activity_count, snapshot_count, spi, cpi, delay_days,
                      overall_planned_pct, overall_actual_pct, pv, ev, ac}, … ],
                    # one row per project, its most recent snapshot, newest first
      'active':    {project_id, name, trend:[ {id, data_date, imported_at,
                      pv, ev, ac, spi, cpi, delay_days,
                      overall_planned_pct, overall_actual_pct}, … ]} | None,
    }

Mirrors ui/modules/dashboard.js (the authoritative display) so the exported figures
equal what the planner sees: overall_*_pct is a fraction (0–1) shown as a percent,
SPI/CPI to two decimals, delay in days, and the SPI≥1 / <1 on-track-vs-behind rule
of the portfolio cards + header chips. Numbers stay numeric (the header carries the %
meaning). This is a pure presenter — it computes nothing new, only what the DB stored.
DB is the read path: no XML is re-parsed here.
"""
from datetime import datetime


def _fmt_date(iso):
    """ISO/date → '09 Feb 2026' (matches dashboard.js fmtDate en-GB); '—' when absent."""
    if not iso:
        return '—'
    if hasattr(iso, 'strftime'):
        return iso.strftime('%d %b %Y')
    s = str(iso).strip()
    parsed = None
    try:
        parsed = datetime.fromisoformat(s.replace('Z', '').replace('T', ' ').strip())
    except ValueError:
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d-%b-%Y', '%d-%b-%y', '%m/%d/%Y'):
            try:
                parsed = datetime.strptime(s[:10] if fmt == '%Y-%m-%d' else s, fmt)
                break
            except ValueError:
                continue
    return parsed.strftime('%d %b %Y') if parsed else s[:11]


def _spi(v):
    """SPI/CPI numeric to 2 dp (dashboard.js spiFmt → toFixed(2)); '—' when null."""
    if v is None:
        return '—'
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return '—'


def _pct(v):
    """overall_*_pct fraction (0–1) → whole-number-of-percent value with 1 dp
    (dashboard.js pct1 → (v*100).toFixed(1)); '—' when null. Kept numeric; the header
    says '%'."""
    if v is None:
        return '—'
    try:
        return round(float(v) * 100, 1)
    except (TypeError, ValueError):
        return '—'


def _delay(v):
    """Finish delay in days, numeric (screen shows '+N d' / 'N d'); '—' when null."""
    if v is None:
        return '—'
    try:
        return int(v)
    except (TypeError, ValueError):
        return '—'


def _status(spi):
    """Portfolio card colour rule (dashboard.js): SPI≥1 on track, <1 behind."""
    if spi is None:
        return '—'
    try:
        return 'On track' if float(spi) >= 1 else 'Behind'
    except (TypeError, ValueError):
        return '—'


def _portfolio_blocks(portfolio):
    """Header-chip summary + the portfolio table (one row per project, latest snapshot)
    — mirrors the dashboard's chips and the portfolio card grid."""
    behind = sum(1 for r in portfolio if r.get('spi') is not None and float(r['spi']) < 1)
    on_track = sum(1 for r in portfolio if r.get('spi') is not None and float(r['spi']) >= 1)
    updates = sum(int(r.get('snapshot_count') or 1) for r in portfolio)

    summary = {
        'title': 'Portfolio Summary',
        'headers': ['Metric', 'Value'],
        'rows': [
            ['Projects', len(portfolio)],
            ['Updates (total)', updates],
            ['On track (SPI ≥ 1.00)', on_track],
            ['Behind (SPI < 1.00)', behind],
        ],
    }

    rows = []
    for r in portfolio:
        spi = r.get('spi')
        rows.append([
            r.get('name') or '(project)',
            _fmt_date(r.get('data_date')),
            int(r.get('snapshot_count') or 1),
            r.get('activity_count') if r.get('activity_count') is not None else '—',
            _spi(spi),
            _spi(r.get('cpi')),
            _delay(r.get('delay_days')),
            _pct(r.get('overall_planned_pct')),
            _pct(r.get('overall_actual_pct')),
            _status(spi),
        ])
    if not rows:
        rows = [['No data — import a P6 schedule and it will appear here.',
                 '—', '—', '—', '—', '—', '—', '—', '—', '—']]
    table = {
        'title': 'Portfolio — latest update per project',
        'note': 'Numbers read from the saved database (no re-parse). % columns are of total scope.',
        'headers': ['Project', 'Data date', 'Updates', 'Activities', 'SPI', 'CPI',
                    'Delay (days)', 'Planned %', 'Actual %', 'Status'],
        'rows': rows,
    }
    return [summary, table]


def _trend_blocks(active):
    """The active project's snapshot trend — the SPI / Overall-progress / Finish-delay
    series charted on screen, laid out as one table (oldest snapshot first)."""
    trend = (active or {}).get('trend') or []
    rows = []
    for t in trend:
        rows.append([
            _fmt_date(t.get('data_date')),
            _spi(t.get('spi')),
            _pct(t.get('overall_planned_pct')),
            _pct(t.get('overall_actual_pct')),
            _delay(t.get('delay_days')),
        ])
    if not rows:
        rows = [['No stored snapshots yet.', '—', '—', '—', '—']]
    name = (active or {}).get('name') or 'current project'
    n = len(trend)
    return [{
        'title': f'Trend — {name}',
        'note': f'{n} update{"" if n == 1 else "s"} · week-over-week SPI, overall progress and finish delay.',
        'headers': ['Data date', 'SPI', 'Planned %', 'Actual %', 'Delay (days)'],
        'rows': rows,
    }]


def dashboard_excel(dashboard):
    """(dashboard read-model dict the client holds) → `sheets` list for write_sections_xlsx.

    Sheet 1 'Portfolio' stacks the header-chip summary + the portfolio table (mirrors the
    card grid). Sheet 2 'Trend' is added only when an active project with stored snapshots
    is present (as the trend section appears on screen only then). Never raises on
    empty/missing data — an empty portfolio yields a single 'No data' row.
    """
    dashboard = dashboard or {}
    portfolio = dashboard.get('portfolio') or []
    active = dashboard.get('active') or None

    sheets = [{
        'name': 'Portfolio',
        'blocks': _portfolio_blocks(portfolio),
        'col_widths': {0: 34, 1: 14, 2: 10, 3: 11, 4: 8, 5: 8, 6: 12, 7: 11, 8: 11, 9: 12},
    }]

    if active and (active.get('trend') or []):
        sheets.append({
            'name': 'Trend',
            'blocks': _trend_blocks(active),
            'col_widths': {0: 16, 1: 8, 2: 11, 3: 11, 4: 12},
        })

    return sheets
