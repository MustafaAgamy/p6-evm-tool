"""Schedule-quality diff across two baseline revisions — neutral, progress-free.

Reports the standard DCMA-style *health* metrics (open ends / dangling logic, leads,
relationship density, hard constraints, negative and near-critical float, the float
distribution) computed **per revision** and then diffed, so a planner can see whether
the revised baseline is tighter or looser than the original. Nothing here is a verdict:
a lead or an open end is surfaced as evidence for planning review, never flagged "wrong".

All logic is pure — it reads a parsed ``ScheduleData`` pair and the ``MatchedSchedules``
the caller already built (rev0 vs the canonicalised rev1) and returns a JSON-serialisable
dict. Every path is guarded: missing data yields empty/zero structures, never an exception.

Public API:
    build_quality(rev0, rev1, matched, cal) -> dict  (report['quality'])
"""
from p6_revcompare.structure import _HARD_CONSTRAINTS

_MS = ('StartMilestone', 'FinishMilestone')


# ── small helpers ────────────────────────────────────────────────────────────

def _disp_id(act):
    """Display code for an activity — the real (pre-canonicalisation) code when known."""
    return act.get('orig_id') or act.get('id')


def _rel_endpoints(rels):
    """From a ``{(pred_code, succ_code): rel}`` map, return (codes_with_pred, codes_with_succ)."""
    has_pred, has_succ = set(), set()
    for pc, sc in (rels or {}):
        has_succ.add(pc)     # a predecessor => it has a successor
        has_pred.add(sc)     # a successor  => it has a predecessor
    return has_pred, has_succ


def _dangling_codes(by_code, rels):
    """Codes (excl. start/finish milestones) missing a predecessor OR a successor."""
    has_pred, has_succ = _rel_endpoints(rels)
    out = set()
    for code, a in (by_code or {}).items():
        if not code or a.get('task_type') in _MS:
            continue
        if code not in has_pred or code not in has_succ:
            out.add(code)
    return out


def _lead_edges(rels):
    """{(pred_code, succ_code): lag_days} for every relationship with a negative lag (a lead)."""
    out = {}
    for key, r in (rels or {}).items():
        lag = r.get('lag_days') or 0.0
        if lag < 0:
            out[key] = lag
    return out


def _hard_constraint_count(by_code):
    return sum(1 for a in (by_code or {}).values()
               if a.get('constraint_type') in _HARD_CONSTRAINTS)


def _floats(by_code):
    """Total-float values (working days) for activities that carry one."""
    out = []
    for a in (by_code or {}).values():
        tf = a.get('total_float_days')
        if tf is not None:
            out.append(tf)
    return out


def _band_counts(tfs):
    """Counts across the 5 float bands (mutually exclusive, gap-free)."""
    b = {'<0': 0, '0–5': 0, '6–20': 0, '21–60': 0, '60+': 0}
    for tf in tfs:
        if tf < 0:
            b['<0'] += 1
        elif tf <= 5:
            b['0–5'] += 1
        elif tf <= 20:
            b['6–20'] += 1
        elif tf <= 60:
            b['21–60'] += 1
        else:
            b['60+'] += 1
    return b


def _rels_per_act(n_rels, n_acts):
    return round(n_rels / n_acts, 2) if n_acts else 0.0


# ── the module ────────────────────────────────────────────────────────────────

def build_quality(rev0, rev1, matched, cal=None):
    """Per-revision schedule-quality metrics + the rev0→rev1 diff.

    ``rev0`` / ``rev1`` are parsed ScheduleData (``rev1`` is the canonicalised revision).
    ``matched`` is the ``MatchedSchedules`` the caller built (rev0 vs canonicalised rev1);
    its ``*_by_code`` / ``*_rels`` maps are reused so both revisions share a code space.
    ``cal`` (reference calendar) is accepted for signature parity and future use.

    Returns ``report['quality']`` — see the build contract for the exact key shapes.
    """
    if matched is None:
        try:
            from p6_compare.model import MatchedSchedules
            matched = MatchedSchedules(rev0, rev1)
        except Exception:
            matched = None

    by0 = getattr(matched, 'baseline_by_code', None) or {}
    by1 = getattr(matched, 'update_by_code', None) or {}
    rels0 = getattr(matched, 'baseline_rels', None) or {}
    rels1 = getattr(matched, 'update_rels', None) or {}

    # ── open ends / dangling logic ───────────────────────────────────────────
    dang0 = _dangling_codes(by0, rels0)
    dang1 = _dangling_codes(by1, rels1)
    new_dangling = []
    for code in sorted(dang1 - dang0):
        a = by1.get(code) or {}
        new_dangling.append({'id': _disp_id(a) or code, 'name': a.get('name') or code})

    # ── leads (negative lag) ─────────────────────────────────────────────────
    leads0 = _lead_edges(rels0)
    leads1 = _lead_edges(rels1)
    new_leads = []
    for (pc, sc) in sorted(set(leads1) - set(leads0)):
        new_leads.append({'pred_id': pc, 'succ_id': sc, 'lag': round(leads1[(pc, sc)], 1)})

    # ── relationship density ─────────────────────────────────────────────────
    n_rels0, n_rels1 = len(rels0), len(rels1)
    n_act0, n_act1 = len(by0), len(by1)

    # ── negative float ───────────────────────────────────────────────────────
    neg0 = sum(1 for tf in _floats(by0) if tf < 0)
    neg_register = []
    for code, a in by1.items():
        tf = a.get('total_float_days')
        if tf is not None and tf < 0:
            neg_register.append({'id': _disp_id(a) or code, 'name': a.get('name') or code,
                                 'tf': round(tf, 1), 'wbs': a.get('wbs_path') or '—'})
    neg_register.sort(key=lambda r: r['tf'])
    neg1 = len(neg_register)

    # ── near-critical (0 <= TF < 5) ──────────────────────────────────────────
    near0 = sum(1 for tf in _floats(by0) if 0 <= tf < 5)
    near1 = sum(1 for tf in _floats(by1) if 0 <= tf < 5)

    # ── float distribution ───────────────────────────────────────────────────
    b0 = _band_counts(_floats(by0))
    b1 = _band_counts(_floats(by1))
    float_bands = [{'band': k, 'rev0': b0[k], 'rev1': b1[k]}
                   for k in ('<0', '0–5', '6–20', '21–60', '60+')]

    return {
        'open_ends': {'rev0': len(dang0), 'rev1': len(dang1), 'new_dangling': new_dangling},
        'leads': {'rev0': len(leads0), 'rev1': len(leads1), 'new_leads': new_leads},
        'total_rels': {'rev0': n_rels0, 'rev1': n_rels1},
        'rels_per_act': {'rev0': _rels_per_act(n_rels0, n_act0),
                         'rev1': _rels_per_act(n_rels1, n_act1)},
        'hard_constraints': {'rev0': _hard_constraint_count(by0),
                             'rev1': _hard_constraint_count(by1)},
        'negative_float': {'rev0': neg0, 'rev1': neg1, 'register': neg_register},
        'near_critical': {'rev0': near0, 'rev1': near1},
        'float_bands': float_bands,
    }
