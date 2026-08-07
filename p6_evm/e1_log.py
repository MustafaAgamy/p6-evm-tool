"""E1 Log (drawings register) reader + summary.

Reproduces the client's "E1 Log Status" summary: per Trade x Submittal Type,
count Total Req (distinct drawings), Submitted rows, Approved (Action Code A/B),
Not Approved (C), Under Review (P); percentages are on a distinct-drawing basis
(a drawing counts once regardless of resubmissions). Reading the .xlsx uses
openpyxl; the aggregation (summarize_e1) is pure and unit-tested.
"""
from p6_evm.classify import classify_action_code


def _has(v):
    return v not in (None, '', ' ')


def summarize_e1(rows, cutoff=None):
    """rows: list of dicts with keys trade, submittal_type, building, description,
    submitted (date|None), planned (date|None), action_code (str).
    Returns { (trade, submittal_type): {req, planned, submitted_rows, approved_rows,
    not_approved_rows, under_review_rows, submitted_pct, approved_pct, planned_pct} }.

    Counting is per DISTINCT drawing, not per submission row (Ibrahim's rule): a drawing
    is unique by title/name (building + description). Once it is Approved (A/B) at any
    revision, later resubmissions of the same drawing — methodology-change reissues — are
    NOT counted again. So every count is a distinct-drawing count and % never exceeds 100%.
    """
    groups = {}   # (trade, typ) -> { drawing_key -> {submitted, approved, rejected, under_review, planned} }
    for r in rows:
        trade = (r.get('trade') or '').strip()
        typ = (r.get('submittal_type') or '').strip()
        if not trade or not typ:
            continue
        dk = (str(r.get('building') or '').strip(), str(r.get('description') or '').strip())
        d = groups.setdefault((trade, typ), {}).setdefault(
            dk, {'submitted': False, 'approved': False, 'rejected': False,
                 'under_review': False, 'planned': False})

        if _has(r.get('submitted')):
            d['submitted'] = True
        act = classify_action_code(r.get('action_code'))
        if act == 'approved':
            d['approved'] = True
        elif act == 'not_approved':
            d['rejected'] = True
        elif act == 'under_review':
            d['under_review'] = True
        planned = r.get('planned')
        if _has(planned) and (cutoff is None or planned <= cutoff):
            d['planned'] = True

    result = {}
    for key, draws in groups.items():
        req = len(draws) or 0
        pct = lambda n: round(100.0 * n / req, 1) if req else 0.0
        approved = sum(1 for d in draws.values() if d['approved'])
        submitted = sum(1 for d in draws.values() if d['submitted'])
        # a drawing is "not approved" / "under review" only while it is NOT yet approved
        rejected = sum(1 for d in draws.values() if d['rejected'] and not d['approved'])
        under = sum(1 for d in draws.values() if d['under_review'] and not d['approved'] and not d['rejected'])
        planned = sum(1 for d in draws.values() if d['planned'])
        result[key] = {
            'req': req,
            'planned': planned,
            'submitted_rows': submitted,
            'approved_rows': approved,
            'not_approved_rows': rejected,
            'under_review_rows': under,
            'submitted_pct': pct(submitted - rejected),   # % Submitted = (Submitted − Rejected) ÷ Req
            'approved_pct': pct(approved),                # % Approved  = Approved ÷ Req
            'planned_pct': pct(planned),
        }
    return result


E1_FIELDS = ('trade', 'building', 'description', 'submittal_type', 'submitted', 'planned', 'action_code')


_SHEET_NOISE = ('drawing', 'drawings', 'log', 'logs', 'sheet', 'submittal', 'submittals',
                'register', 'status', 'e1', 'list', 'schedule', 'dwg', 'dwgs')


def _sheet_trade(title):
    """A per-discipline sheet ('Civil Drawings', 'Arch. Log') carries the discipline in
    its NAME. Strip the noise words, leaving the trade ('Civil', 'Arch.')."""
    if not title:
        return None
    words = [w for w in str(title).split() if w.strip().lower().strip('.') not in _SHEET_NOISE]
    name = ' '.join(words).strip()
    return name or None


def read_e1_rows(path):
    """Read every sheet of every E1 / Design / Shop log into flat row dicts (openpyxl).

    Robust to any format:
      * columns matched by MEANING (classify.match_e1_field), not exact spelling;
      * a header row is the first row carrying a Drawing/Submittal-Type column plus at
        least one more recognised column;
      * a per-discipline sheet with no Discipline column takes its trade from the SHEET
        NAME (so a workbook split into Civil / Arch / MEP sheets still reads).
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
            if 'submittal_type' in fields and len(fields) >= 2:
                hdr_i, ci = i, fields
                break
        if hdr_i is None:
            continue
        default_trade = _sheet_trade(ws.title) if 'trade' not in ci else None
        for r in sheet[hdr_i + 1:]:
            def cell(k):
                j = ci.get(k)
                return r[j] if (j is not None and j < len(r)) else None
            trade = cell('trade') or default_trade
            if not trade or not cell('submittal_type'):
                continue
            row = {k: cell(k) for k in E1_FIELDS}
            row['trade'] = trade
            rows.append(row)
    return rows
