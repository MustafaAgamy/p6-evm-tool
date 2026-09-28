"""E1 Log (drawings register) reader + summary.

Reproduces the client's "E1 Log Status" summary: per Trade x Submittal Type,
count Total Req (distinct drawings), Submitted rows, Approved (Action Code A/B),
Not Approved (C), Under Review (P); percentages are on a distinct-drawing basis
(a drawing counts once regardless of resubmissions). Reading the .xlsx uses
openpyxl; the aggregation (summarize_e1) is pure and unit-tested.
"""
import re
from datetime import date, datetime, time

from p6_evm.classify import classify_action_code


def _has(v):
    return v not in (None, '', ' ')


def _rev_key(rev):
    """A revision label → a comparable key, or None when it can't be read.
    '0' / '01' / 'Rev.01' / 'R2' / 'T-00004 Rev.01' → (1, n); a lone letter ('A', 'Rev B') →
    (0, letter) — preliminary letter revisions come before numbered issues."""
    if rev is None:
        return None
    t = str(rev).strip()
    if not t:
        return None
    m = re.search(r'(\d+)\s*$', t)
    if m:
        return (1, int(m.group(1)))
    m = re.fullmatch(r'(?:rev(?:ision)?\.?\s*)?([a-z])', t, re.I)
    if m:
        return (0, ord(m.group(1).upper()))
    return None


def _as_dt(v):
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime.combine(v, time())
    return None


def _latest(subs):
    """The LATEST submission of one drawing. subs: [(revision key|None, sent datetime|None,
    input order, verdict)]. By revision when every submission has a readable revision, else by
    date sent when every one is dated, else by the order the rows appear in the log (which is
    also the last tie-breaker)."""
    if all(s[0] is not None for s in subs):
        return max(subs, key=lambda s: (s[0], s[1] or datetime.min, s[2]))
    if all(s[1] is not None for s in subs):
        return max(subs, key=lambda s: (s[1], s[2]))
    return max(subs, key=lambda s: s[2])


def summarize_e1(rows, cutoff=None):
    """rows: list of dicts with keys trade, submittal_type, building, description,
    submitted (date|None), planned (date|None), action_code (str).
    Returns { (trade, submittal_type): {req, planned, submitted_rows, approved_rows,
    not_approved_rows, under_review_rows, submitted_pct, approved_pct, planned_pct} }.

    Counting is per DISTINCT drawing, not per submission row (Ibrahim's rule): a drawing
    is unique by title/name (building + description). Once it is Approved (A/B) at any
    revision, later resubmissions of the same drawing — methodology-change reissues — are
    NOT counted again. So every count is a distinct-drawing count and % never exceeds 100%.

    Status of a drawing that is NOT approved (owner decision ELOG-4, 2026-09-27): its LATEST
    revision / submission decides —
      * latest still awaiting a reply (W / P / pending wording, or sent with no code and no
        reply yet) → UNDER REVIEW, and it stays in Submitted (it is not subtracted);
      * latest returned C / D / not-approved wording → NOT APPROVED.
    So a drawing returned C and then resubmitted is Under review, not Not approved.
    "Latest" = highest revision when every submission has one, else latest date sent, else the
    lower row in the log. Rows with no review status at all (not sent, an unrecognised code)
    do not decide the status.

    Optional per-row keys (set by the format-agnostic reader, p6_evm.elog_smart):
      * 'drawing_key' — the drawing's identity (e.g. its Drawing No.); rows without it keep
        the (building, description) key, so ROOTS-style logs count exactly as before;
      * 'verdict'     — the review code already classified with the log's own legend
        ('approved' | 'not_approved' | 'under_review' | None); else classify_action_code;
      * 'returned'    — the consultant's reply date;
      * 'revision'    — the revision label (orders the submissions of one drawing).
    A drawing SUBMITTED with no reply and no code yet counts as Under Review (owner-approved
    review-code rule, Tool-Wide Enhancement scope §2).
    """
    groups = {}   # (trade, typ) -> { drawing_key -> {submitted, approved, subs, planned} }
    for i, r in enumerate(rows):
        trade = str(r.get('trade') or '').strip()
        typ = str(r.get('submittal_type') or '').strip()
        if not trade or not typ:
            continue
        dk = r.get('drawing_key')
        if not dk:
            dk = (str(r.get('building') or '').strip(), str(r.get('description') or '').strip())
        d = groups.setdefault((trade, typ), {}).setdefault(
            dk, {'submitted': False, 'approved': False, 'subs': [], 'planned': False})

        submitted = _has(r.get('submitted'))
        if submitted:
            d['submitted'] = True
        act = r['verdict'] if 'verdict' in r else classify_action_code(r.get('action_code'))
        if (act is None and submitted and not _has(r.get('action_code'))
                and not _has(r.get('returned'))):
            act = 'under_review'                  # sent, no reply yet
        if act == 'approved':
            d['approved'] = True
        elif act in ('not_approved', 'under_review'):
            d['subs'].append((_rev_key(r.get('revision')), _as_dt(r.get('submitted')), i, act))
        planned = r.get('planned')
        if _has(planned) and (cutoff is None or planned <= cutoff):
            d['planned'] = True

    result = {}
    for key, draws in groups.items():
        req = len(draws) or 0
        pct = lambda n: round(100.0 * n / req, 1) if req else 0.0
        approved = sum(1 for d in draws.values() if d['approved'])
        submitted = sum(1 for d in draws.values() if d['submitted'])
        # once approved it stays approved; otherwise the latest revision decides
        state = [_latest(d['subs'])[3] for d in draws.values() if not d['approved'] and d['subs']]
        rejected = state.count('not_approved')
        under = state.count('under_review')
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
