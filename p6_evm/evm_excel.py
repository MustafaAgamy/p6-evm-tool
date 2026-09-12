"""Earned Value (EVM) Excel exporter.

Turns the EVM report/result the CLIENT holds into the `sheets` structure consumed by
`p6_evm.xlsx_writer.write_sections_xlsx`, so the workbook MIRRORS the on-screen / PDF
report sections (stacked titled tables) rather than a flat dump.

The client posts `report` = {
    'result':      the compute() result the screen is showing (categories already carry
                   any E1-applied actual_pct — evm.js mutates them in place),
    'weights':     {category: weight-fraction} the user edited (overrides cat.weight),
    'actual_cost': the user's Actual Cost override in EGP, or None → use P6 (result.ac),
    'gap':         current PV-EV gap block ({dimension, groups, total_gap}) or None,
    'engineering': {mode:'E1'|'P6', rows, overall?, by_trade?, gaps?} or None,
    'meta':        {project_name, data_date, report_date, source_file,
                    baseline_finish, expected_finish},
}

Every number source and formatting here mirrors ui/modules/evm.js (the authoritative
display) so the exported figures equal exactly what the planner sees when they click
Export — weighted SPI, effective-weight overall %, effective Actual Cost → CPI, and the
weight>0 category rule of the on-screen Category Weights table. Nothing is computed from
scratch — it only presents what evm.js already resolved.
"""
from datetime import datetime

# EVM_SECTIONS keys (mirror api.js) — the four core report sections this workbook covers.
_CORE_SECTIONS = ('progress', 'dashboard', 'value', 'category')


def _effective_weight(name, cat, weights):
    """User-edited weight wins over the auto-detected category weight (evm.js rule)."""
    if weights and weights.get(name) is not None:
        return weights.get(name) or 0
    return cat.get('weight') or 0


def _project_progress(cats, weights):
    """Overall Planned/Actual as the *unnormalised* weighted sum Σ weight×% — matches the
    Overall row of the Category Weights table and the top slicer (evm.js projectProgress)."""
    planned = actual = 0.0
    for name, c in (cats or {}).items():
        w = _effective_weight(name, c, weights)
        planned += w * (c.get('planned_pct') or 0)
        actual += w * (c.get('actual_pct') or 0)
    return planned, actual


def _egp_exact(n):
    """Exact money with thousands separators (evm.js egpExact) — '243,805,397'."""
    if n is None:
        return '—'
    try:
        return f'{round(n):,}'
    except Exception:
        return str(n)


def _as_pct(x):
    """Whole-percent (evm.js asPct) — 0.98 → '98%'."""
    if x is None:
        return '—'
    try:
        return f'{round(x * 100)}%'
    except Exception:
        return str(x)


def _pct2(x):
    """Two-decimal percent — 0.4235 → '42.35%' (evm.js slicer / progress band)."""
    if x is None:
        return '—'
    try:
        return f'{x * 100:.2f}%'
    except Exception:
        return str(x)


def _round2(x):
    """Numeric percent value for a data-table cell (header carries the % meaning)."""
    try:
        return round(x, 2)
    except Exception:
        return x


def _fmt_date(iso):
    """ISO/date → '09 Feb 2026' (matches the screen's fmtDate en-GB day/short-month/year)."""
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


def _spi_status(spi):
    """Schedule verdict shown beside the SPI tile (evm.js spiStatus)."""
    if spi is None:
        return 'n/a'
    if spi >= 1.0:
        return 'Ahead / On Schedule'
    if spi >= 0.95:
        return 'Slightly Behind'
    return 'Behind Schedule'


def _core_blocks(result, weights, actual_cost, meta):
    """The four EVM_SECTIONS as stacked titled tables (progress, dashboard, value, category)."""
    cats = result.get('categories') or {}
    planned, actual = _project_progress(cats, weights)
    spi = (actual / planned) if planned else None
    ev = result.get('ev')
    ac = actual_cost if actual_cost is not None else result.get('ac')
    cpi = (ev / ac) if (ac and ev is not None) else result.get('cpi')
    pv = result.get('pv')

    # ── progress ────────────────────────────────────────────────────────────
    var = actual - planned
    behind = var < 0
    var_txt = f"{'−' if behind else '+'}{abs(var) * 100:.2f}%"
    progress = {
        'title': 'Project Progress — Planned vs Actual',
        'headers': ['Metric', 'Value', 'Note'],
        'rows': [
            ['Planned %', _pct2(planned), 'Overall Planned Weight %'],
            ['Actual %', _pct2(actual), 'Overall Weighted Actual %'],
            ['Variance', var_txt, 'behind plan' if behind else 'ahead of plan'],
        ],
    }

    # ── dashboard (the 10 KPI tiles, in screen order) ─────────────────────────
    ac_note = 'entered' if actual_cost is not None else 'from P6'
    delay = result.get('delay_days')
    dashboard = {
        'title': 'Executive Dashboard',
        'headers': ['KPI', 'Value', 'Detail'],
        'rows': [
            ['SPI · Schedule', _as_pct(spi), _spi_status(spi)],
            ['Overall Planned %', _pct2(planned), 'weighted table'],
            ['Overall Actual %', _pct2(actual), 'weighted table'],
            ['Planned Value', _egp_exact(pv), 'EGP'],
            ['Earned Value', _egp_exact(ev), 'EGP'],
            ['Actual Cost', _egp_exact(ac), ac_note],
            ['CPI · Cost', _as_pct(cpi), 'auto from Actual Cost'],
            ['Baseline Finish', _fmt_date(meta.get('baseline_finish')), ''],
            ['Expected Finish', _fmt_date(meta.get('expected_finish')), ''],
            ['Delay', f'{delay} days' if delay is not None else '—', ''],
        ],
    }

    # ── value (PV vs EV) — kept numeric so the figures stay computable ─────────
    value = {
        'title': 'Planned Value vs Earned Value',
        'headers': ['Measure', 'Value (EGP)'],
        'rows': [
            ['Planned Value (PV)', pv if pv is not None else '—'],
            ['Earned Value (EV)', ev if ev is not None else '—'],
        ],
    }

    # ── category weights & overall progress (weight>0 rows, as the screen shows) ──
    cat_rows = []
    tot_pw = tot_wa = 0.0
    for name, c in cats.items():
        w = _effective_weight(name, c, weights)
        if not (w > 0):                       # 0%-weight WBS (milestones/summary) excluded — screen rule
            continue
        pp = c.get('planned_pct') or 0
        ap = c.get('actual_pct') or 0
        pw = w * pp * 100
        wa = w * ap * 100
        tot_pw += pw
        tot_wa += wa
        cat_rows.append([name, _round2(w * 100), _round2(pp * 100), _round2(ap * 100),
                         _round2(pw), _round2(wa)])
    if cat_rows:
        cat_rows.append(['Overall', '—', '—', '—', _round2(tot_pw), _round2(tot_wa)])
    else:
        cat_rows = [['No weighted categories', '—', '—', '—', '—', '—']]
    category = {
        'title': 'Category Weights & Overall Progress',
        'headers': ['WBS Category', 'Weight %', 'Planned %', 'Actual %',
                    'Planned Weight %', 'Weighted Actual %'],
        'rows': cat_rows,
    }

    return [progress, dashboard, value, category]


def _engineering_blocks(engineering):
    """Engineering Progress — Drawings by Trade (+ Totals by Trade + Design/Shop gaps).
    Empty list when no engineering data (section absent, like the report)."""
    if not engineering or not engineering.get('rows'):
        return []
    mode = engineering.get('mode', 'E1')
    blocks = []

    if mode == 'P6':
        note = ('Source: P6 (Mode B). A drawing counts Submitted/Approved once its activity has '
                'started. Planned = baseline finish on/before the data date.')
        rows = [[r.get('trade', ''), r.get('submittal_type', ''), r.get('req', ''),
                 r.get('planned_sub', ''), r.get('actual_sub', ''),
                 r.get('planned_appr', ''), r.get('actual_appr', ''),
                 r.get('actual_sub_pct', ''), r.get('actual_appr_pct', '')]
                for r in engineering['rows']]
        blocks.append({
            'title': 'Engineering Progress — Drawings by Trade',
            'note': note,
            'headers': ['Trade', 'Submittal Type', 'Req', 'Planned SUB', 'Actual SUB',
                        'Planned APP', 'Actual APP', 'Sub %', 'Appr %'],
            'rows': rows,
        })
    else:
        note = ('Source: E1 Log. Design = any non-Shop drawing; Engineering = Shop drawings. '
                '% Submitted = (Submitted − Not Approved) ÷ Req; % Approved = Approved ÷ Req.')
        rows = [[r.get('trade', ''), r.get('submittal_type', ''), r.get('req', ''),
                 r.get('planned', ''), r.get('submitted_rows', ''), r.get('approved_rows', ''),
                 r.get('not_approved_rows', ''), r.get('under_review_rows', ''),
                 r.get('planned_pct', ''), r.get('submitted_pct', ''), r.get('approved_pct', '')]
                for r in engineering['rows']]
        ov = engineering.get('overall') or {}
        for label, key in (('Overall — Design Drawings', 'design'),
                           ('Overall — Engineering (Shop) Drawings', 'engineering')):
            o = ov.get(key) or {}
            if o:
                rows.append([label, '', o.get('req', ''), o.get('planned', ''),
                             o.get('submitted_rows', ''), o.get('approved_rows', ''),
                             o.get('not_approved_rows', ''), o.get('under_review_rows', ''),
                             o.get('planned_pct', ''), o.get('submitted_pct', ''),
                             o.get('approved_pct', '')])
        blocks.append({
            'title': 'Engineering Progress — Drawings by Trade',
            'note': note,
            'headers': ['Trade', 'Submittal Type', 'Req', 'Planned', 'Submitted', 'Approved',
                        'Not Appr', 'Under Rev', 'Planned %', 'Submitted %', 'Approved %'],
            'rows': rows,
        })

    by_trade = engineering.get('by_trade') or []
    if by_trade:
        blocks.append({
            'title': 'Engineering — Totals by Trade',
            'headers': ['Trade', 'Req', 'Submitted', 'Approved', 'Not Appr', 'Sub %', 'Appr %'],
            'rows': [[f"Total {t.get('trade', '')}", t.get('req', ''), t.get('submitted_rows', ''),
                      t.get('approved_rows', ''), t.get('not_approved_rows', ''),
                      t.get('submitted_pct', ''), t.get('approved_pct', '')] for t in by_trade],
        })

    gaps = engineering.get('gaps') or {}
    for title, key in (('Engineering Gap — Design Drawings (Planned vs Approved by Trade)', 'design'),
                       ('Engineering Gap — Shop Drawings (Planned vs Approved by Trade)', 'engineering')):
        groups = gaps.get(key)
        if groups:
            blocks.append({
                'title': title,
                'headers': ['Trade', 'Planned', 'Approved', 'Gap', '% of Gap'],
                'rows': [[g.get('trade', ''), g.get('planned', ''), g.get('approved', ''),
                          g.get('gap', ''),
                          f"{abs(g.get('pct_of_gap', 0)):.0f}%"] for g in groups],
            })
    return blocks


def _gap_blocks(gap):
    """PV vs EV Gap Analysis — by <dimension>. Empty list when no gap (section absent)."""
    if not gap or not gap.get('groups'):
        return []

    def _gap_val(v):
        if v is None:
            return '—'
        return f'Ahead {_egp_exact(-v)}' if v < 0 else _egp_exact(v)

    rows = [[g.get('code', ''), g.get('pv', ''), g.get('ev', ''), _gap_val(g.get('gap')),
             f"{abs(g.get('pct_of_gap', 0)):.0f}%"] for g in gap['groups'][:15]]
    return [{
        'title': f"PV vs EV Gap Analysis — by {gap.get('dimension', '')}".rstrip(' —by'),
        'note': f"Total gap (PV − EV) = {_gap_val(gap.get('total_gap'))} EGP — where the slippage concentrates.",
        'headers': ['Group', 'PV', 'EV', 'Gap', '% of Gap'],
        'rows': rows,
    }]


def evm_excel(report):
    """(report dict the client holds) → `sheets` list for write_sections_xlsx.

    Sheet 1 'Earned Value' stacks the four EVM_SECTIONS (progress, dashboard, value,
    category), mirroring the single-page report body. Engineering and the PV-EV Gap are
    data-driven add-ons — each becomes its own sheet only when present (as they appear on
    the report). Never raises on empty/missing data: a 'No data' sheet is returned instead.
    """
    report = report or {}
    result = report.get('result') or {}
    weights = report.get('weights') or {}
    actual_cost = report.get('actual_cost')
    meta = report.get('meta') or {}
    gap = report.get('gap') or result.get('gap')
    engineering = report.get('engineering')

    has_any = bool(result.get('categories')) or result.get('pv') is not None or result.get('ev') is not None
    if not has_any:
        return [{'name': 'Earned Value',
                 'blocks': [{'title': 'Earned Value', 'headers': ['Metric', 'Value'],
                             'rows': [['No data', 'Import a P6 schedule and open Earned Value first.']]}]}]

    sheets = [{
        'name': 'Earned Value',
        'blocks': _core_blocks(result, weights, actual_cost, meta),
        'col_widths': {0: 34, 1: 20, 2: 26, 3: 16, 4: 18, 5: 18},
    }]

    eng_blocks = _engineering_blocks(engineering)
    if eng_blocks:
        sheets.append({'name': 'Engineering', 'blocks': eng_blocks,
                       'col_widths': {0: 26, 1: 20}})

    gap_blocks = _gap_blocks(gap)
    if gap_blocks:
        sheets.append({'name': 'PV-EV Gap', 'blocks': gap_blocks,
                       'col_widths': {0: 30, 1: 16, 2: 16, 3: 18, 4: 12}})

    return sheets
