"""E1 Log (drawings register) reader + summary.

Reproduces the client's "E1 Log Status" summary: per Trade x Submittal Type,
count Total Req (distinct drawings), Submitted rows, Approved (Action Code A/B),
Not Approved (C), Under Review (P); percentages are on a distinct-drawing basis
(a drawing counts once regardless of resubmissions). Reading the .xlsx uses
openpyxl; the aggregation (summarize_e1) is pure and unit-tested.
"""
APPROVED_CODES = ('A', 'B')


def _has(v):
    return v not in (None, '', ' ')


def summarize_e1(rows, cutoff=None):
    """rows: list of dicts with keys trade, submittal_type, building, description,
    submitted (date|None), planned (date|None), action_code (str).
    Returns { (trade, submittal_type): {req, planned, submitted_rows, approved_rows,
    not_approved_rows, under_review_rows, submitted_pct, approved_pct, planned_pct} }.
    """
    groups = {}
    for r in rows:
        trade = (r.get('trade') or '').strip()
        typ = (r.get('submittal_type') or '').strip()
        if not trade or not typ:
            continue
        key = (trade, typ)
        g = groups.setdefault(key, {
            'drawings': set(), 'planned_draw': set(),
            'submitted_rows': 0, 'approved_rows': 0, 'not_approved_rows': 0, 'under_review_rows': 0,
        })
        draw = (str(r.get('building') or '').strip(), str(r.get('description') or '').strip())
        g['drawings'].add(draw)

        if _has(r.get('submitted')):
            g['submitted_rows'] += 1

        act = str(r.get('action_code') or '').strip().upper()
        if act in APPROVED_CODES:
            g['approved_rows'] += 1
        elif act == 'C':
            g['not_approved_rows'] += 1
        elif act == 'P':
            g['under_review_rows'] += 1

        planned = r.get('planned')
        if _has(planned) and (cutoff is None or planned <= cutoff):
            g['planned_draw'].add(draw)

    result = {}
    for key, g in groups.items():
        req = len(g['drawings']) or 0
        pct = lambda n: round(100.0 * n / req, 1) if req else 0.0
        # % Submitted nets out rejected revisions: (submitted rows - not approved) / req
        net_submitted = g['submitted_rows'] - g['not_approved_rows']
        result[key] = {
            'req': req,
            'planned': len(g['planned_draw']),
            'submitted_rows': g['submitted_rows'],
            'approved_rows': g['approved_rows'],
            'not_approved_rows': g['not_approved_rows'],
            'under_review_rows': g['under_review_rows'],
            'submitted_pct': pct(net_submitted),
            'approved_pct': pct(g['approved_rows']),
            'planned_pct': pct(len(g['planned_draw'])),
        }
    return result


E1_FIELDS = ('trade', 'building', 'description', 'submittal_type', 'submitted', 'planned', 'action_code')


def read_e1_rows(path):
    """Read every E1 Log sheet into flat row dicts (uses openpyxl).

    Columns are matched by MEANING (see classify.match_e1_field), not exact spelling,
    so any E1 Log format reads — Discipline == Descipline == Trade == Division, etc.
    A sheet's header row is the first row that carries both a Discipline/Trade column
    and a Drawing/Submittal-Type column.
    """
    import openpyxl
    from p6_evm.classify import match_e1_field
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

    rows = []
    for ws in wb.worksheets:
        sheet = list(ws.iter_rows(values_only=True))
        hdr_i, ci = None, None
        for i, r in enumerate(sheet):
            fields = {}
            for j, cell_val in enumerate(r):
                f = match_e1_field(cell_val)
                if f and f not in fields:        # first column wins for a field
                    fields[f] = j
            if 'trade' in fields and 'submittal_type' in fields:
                hdr_i, ci = i, fields
                break
        if hdr_i is None:
            continue
        for r in sheet[hdr_i + 1:]:
            def cell(k):
                j = ci.get(k)
                return r[j] if (j is not None and j < len(r)) else None
            if not cell('trade') or not cell('submittal_type'):
                continue
            rows.append({k: cell(k) for k in E1_FIELDS})
    return rows
