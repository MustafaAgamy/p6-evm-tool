"""Logic (relationship) register — one row per CHANGED relationship between two revisions.

Neutral evidence, no verdict: it lists every predecessor→successor link that was added,
removed, retyped or re-lagged between Rev.00 and Rev.01, spells the relationship type in
full, and flags whether the link touches the revised critical path or is a lead (negative
lag). It keys relationships exactly as ``compare._logic_stats`` does — through
``MatchedSchedules.baseline_rels`` / ``update_rels``, which map ``(pred_code, succ_code)``
to ``{type, lag_days, pred_name, succ_name}`` — so the register and the summary logic
counts can never disagree.

Pure: reads the matched maps + the revised critical-code set, returns JSON-serialisable
rows. Every path is guarded — missing data yields an empty list, never an exception.
"""

# Full-word relationship type labels (P6 uses the two-letter codes internally).
_TYPE_FULL = {
    'FS': 'Finish-to-Start (FS)',
    'SS': 'Start-to-Start (SS)',
    'FF': 'Finish-to-Finish (FF)',
    'SF': 'Start-to-Finish (SF)',
}

_NO_LINK = '— no link'
_LINK_REMOVED = '— link removed'


def _lag_days(rel):
    try:
        return float(rel.get('lag_days') or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _fmt(rel):
    """'Finish-to-Start (FS) · +0 d' — full type name and signed whole-day lag."""
    if not rel:
        return _NO_LINK
    t = rel.get('type') or 'FS'
    label = _TYPE_FULL.get(t, t)
    lag = int(round(_lag_days(rel)))
    return f"{label} · {lag:+d} d"


def _name(matched, code):
    """Resolve an activity code to a display name via the revised map first, then the
    original, then fall back to the code itself."""
    a = None
    try:
        a = (matched.update_by_code.get(code) if matched.update_by_code else None) \
            or (matched.baseline_by_code.get(code) if matched.baseline_by_code else None)
    except AttributeError:
        a = None
    return (a.get('name') if a else None) or code


def build_logic_register(matched, crit1):
    """One row per CHANGED relationship between ``matched.baseline_rels`` (Rev.00) and
    ``matched.update_rels`` (Rev.01).

    Args:
        matched: a ``MatchedSchedules`` (or anything exposing ``baseline_rels`` /
                 ``update_rels`` keyed by ``(pred_code, succ_code)`` and the
                 ``baseline_by_code`` / ``update_by_code`` name maps).
        crit1:   set of activity codes on the revised (Rev.01) critical path.

    Returns a list of dicts:
        {pred_id, pred_name, succ_id, succ_name, before, after,
         change: 'Type changed'|'Lag changed'|'Link added'|'Link removed',
         on_cp: bool, is_lead: bool}
    Rows touching the critical path are sorted first.
    """
    if matched is None:
        return []
    e0 = getattr(matched, 'baseline_rels', None) or {}
    e1 = getattr(matched, 'update_rels', None) or {}
    crit = set(crit1) if crit1 else set()

    rows = []
    k0, k1 = set(e0), set(e1)

    def emit(pc, sc, before, after, change, after_rel):
        rows.append({
            'pred_id': pc, 'pred_name': _name(matched, pc),
            'succ_id': sc, 'succ_name': _name(matched, sc),
            'before': before, 'after': after,
            'change': change,
            'on_cp': (pc in crit) or (sc in crit),
            'is_lead': bool(after_rel is not None and _lag_days(after_rel) < 0),
        })

    # Links added in Rev.01.
    for key in (k1 - k0):
        pc, sc = key
        u = e1[key]
        emit(pc, sc, _NO_LINK, _fmt(u), 'Link added', u)

    # Links removed in Rev.01.
    for key in (k0 - k1):
        pc, sc = key
        b = e0[key]
        emit(pc, sc, _fmt(b), _LINK_REMOVED, 'Link removed', None)

    # Links present in both — type change wins over lag change (mirrors _logic_stats).
    for key in (k0 & k1):
        b, u = e0[key], e1[key]
        pc, sc = key
        if (b.get('type') or 'FS') != (u.get('type') or 'FS'):
            emit(pc, sc, _fmt(b), _fmt(u), 'Type changed', u)
        elif abs(_lag_days(b) - _lag_days(u)) > 1e-9:
            emit(pc, sc, _fmt(b), _fmt(u), 'Lag changed', u)

    # Changed-on-critical-path first; then stable, deterministic ordering.
    rows.sort(key=lambda r: (not r['on_cp'], r['pred_id'], r['succ_id']))
    return rows
