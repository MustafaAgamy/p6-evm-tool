"""Finish-slip driver bridge — a neutral *attribution* of the governing-finish move.

Baseline Revision Comparison reports what changed between two approved baselines and
how much it can move the plan; this module answers the natural follow-up question —
"the finish moved N working days; along the Rev.01 driving chain, what changed to make
that happen?" — as an approximate bridge (a waterfall) whose bars always reconcile to
the total.

It is attribution, not a verdict and not a forensic delay analysis: a baseline carries
no progress, so we cannot run a but-for. We take the *working-day* delta between the two
governing finishes (``_wd_between(cal, gov0, gov1)``) and split it across neutral causes
observed on the Rev.01 critical path (``cp['rev1']`` node codes):

  * ``Added CP scope``    — new activities that sit on the Rev.01 driving chain, valued at
                            their planned durations (working days).
  * ``Longer durations``  — matched driving-chain activities whose planned duration grew.
  * ``Re-sequence``       — execution-order reversals that touch the driving chain.
  * ``New driving link``  — logic added or re-typed on the driving chain.
  * ``Constraint``        — a hard date constraint added or moved on the driving chain.

Only the first two carry day-level quantities; the structural causes are flagged with
their counts (``wd`` = 0) because their day-impact cannot be split deterministically
without re-scheduling. Whatever the quantified bars do not account for lands in a final
``Other / interaction`` bar, so ``sum(wd) == total_wd`` exactly — the bridge always closes.

Pure and side-effect free. Every path is guarded: missing data yields an empty, again-safe
structure rather than an exception.
"""

_MS = ('StartMilestone', 'FinishMilestone')


def build_slip(rev0, rev1, matched, match, cp, cal, gov0, gov1):
    """Attribute the governing-finish working-day delta to neutral causes on the
    Rev.01 driving chain. Returns::

        {
          'total_wd':   int,          # working days from gov0 to gov1 (+ = later finish)
          'rev0_finish': str | None,  # short-form governing finish dates
          'rev1_finish': str | None,
          'contributions': [ {'cause': str, 'wd': int, 'detail': str}, ... ],  # sum(wd) == total_wd
        }
    """
    # Lazy imports keep this module free of any import-order coupling to compare.py.
    from p6_revcompare.compare import _dur_days, _wd_between, _d0, _short

    total_wd = 0
    try:
        wd = _wd_between(cal, _d0(gov0), _d0(gov1))
        total_wd = int(round(wd)) if wd is not None else 0
    except Exception:
        total_wd = 0

    out = {
        'total_wd': total_wd,
        'rev0_finish': _short(gov0),
        'rev1_finish': _short(gov1),
        'contributions': [],
    }

    # Codes on the Rev.01 driving chain (canonical codes — aligned with match['pairs']
    # canonical and the canonicalised added activities).
    cp1_codes = set()
    for n in (cp or {}).get('rev1') or []:
        c = n.get('code') if isinstance(n, dict) else None
        if c:
            cp1_codes.add(c)

    contributions = []

    # ── 1) Added CP scope — new activities on the driving chain × their durations ──
    added_on_cp = [a for a in (match or {}).get('added', [])
                   if a.get('id') in cp1_codes and a.get('task_type') not in _MS]
    if added_on_cp:
        wd_added = 0
        names = []
        for a in added_on_cp:
            try:
                d = round(_dur_days(rev1, a))
            except Exception:
                d = 0
            wd_added += max(0, int(d))
            names.append(a.get('name') or a.get('id') or '?')
        contributions.append({
            'cause': 'Added CP scope', 'wd': wd_added,
            'detail': _phrase(len(added_on_cp), 'new activity', 'new activities',
                              'on the Rev.01 critical path', names),
        })

    # ── 2) Longer durations — matched driving-chain activities that grew ──────────
    wd_longer = 0
    grew = []
    for p in (match or {}).get('pairs', []):
        if p.get('canonical') not in cp1_codes:
            continue
        try:
            d0 = _dur_days(rev0, p['act0'])
            d1 = _dur_days(rev1, p['act1'])
        except Exception:
            continue
        delta = d1 - d0
        if delta > 0.5:
            wd_longer += int(round(delta))
            grew.append((p['act1'].get('name') or p.get('canonical') or '?', round(delta, 1)))
    if grew:
        grew.sort(key=lambda t: -t[1])
        names = [f"{nm} +{dl:g} d" for nm, dl in grew]
        contributions.append({
            'cause': 'Longer durations', 'wd': wd_longer,
            'detail': _phrase(len(grew), 'critical activity', 'critical activities',
                              'planned longer', names),
        })

    # ── 3) Re-sequence — order reversals that touch the driving chain ─────────────
    try:
        from p6_revcompare.sequence import detect_sequence_changes
        seqs = detect_sequence_changes(matched)
    except Exception:
        seqs = []
    seq_hits = [s for s in seqs if set(s.get('involved') or []) & cp1_codes]
    if seq_hits:
        names = [s.get('a_name') or s.get('a') or '?' for s in seq_hits]
        contributions.append({
            'cause': 'Re-sequence', 'wd': 0,
            'detail': _phrase(len(seq_hits), 'order reversal', 'order reversals',
                              'on the critical path (not day-quantified)', names),
        })

    # ── 4) New driving link — logic added or re-typed on the driving chain ────────
    b_rels = getattr(matched, 'baseline_rels', {}) or {}
    u_rels = getattr(matched, 'update_rels', {}) or {}

    def _touches_cp(k):
        return (k[0] in cp1_codes) or (k[1] in cp1_codes)

    added_links = [k for k in u_rels if k not in b_rels and _touches_cp(k)]
    retyped_links = [k for k in (set(b_rels) & set(u_rels))
                     if _touches_cp(k) and b_rels[k].get('type') != u_rels[k].get('type')]
    n_links = len(added_links) + len(retyped_links)
    if n_links:
        contributions.append({
            'cause': 'New driving link', 'wd': 0,
            'detail': (f"{n_links} logic link{'s' if n_links != 1 else ''} added or re-typed "
                       f"on the critical path (not day-quantified)."),
        })

    # ── 5) Constraint — a hard date constraint added or moved on the driving chain ─
    try:
        from p6_revcompare.structure import diff_constraints
        cons = diff_constraints(matched)
    except Exception:
        cons = []
    cons_hits = [c for c in cons
                 if c.get('activity_id') in cp1_codes and c.get('hard')
                 and c.get('kind') in ('added', 'date', 'type')]
    if cons_hits:
        names = [c.get('name') or c.get('activity_id') or '?' for c in cons_hits]
        contributions.append({
            'cause': 'Constraint', 'wd': 0,
            'detail': _phrase(len(cons_hits), 'hard constraint', 'hard constraints',
                              'added or moved on the critical path (not day-quantified)', names),
        })

    # ── Reconcile — the residual (interaction of the changes above, plus anything off
    #    the modelled chain) always closes the bridge so sum(wd) == total_wd. ───────
    residual = total_wd - sum(c['wd'] for c in contributions)
    if contributions or residual != 0:
        contributions.append({
            'cause': 'Other / interaction', 'wd': int(residual),
            'detail': ('Net interaction of the changes above and effects off the modelled '
                       'driving chain — the balancing figure that reconciles this attribution '
                       'to the total finish move.'),
        })

    out['contributions'] = contributions
    return out


def _phrase(n, singular, plural, tail, names, max_names=3):
    """A neutral, readable detail line: 'N thing(s) tail (name, name, …).'"""
    noun = singular if n == 1 else plural
    head = f"{n} {noun} {tail}"
    shown = [str(x) for x in (names or []) if x][:max_names]
    if not shown:
        return head + '.'
    extra = len(names) - len(shown)
    listed = ', '.join(shown) + (f", +{extra} more" if extra > 0 else '')
    return f"{head} ({listed})."
