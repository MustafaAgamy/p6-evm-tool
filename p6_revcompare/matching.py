"""Activity matching across two baseline revisions — beyond the Activity ID.

Primavera lets a code change between submissions while the work stays the same, so
matching purely on ``id`` (as ``p6_compare.MatchedSchedules`` does) reads an ID
change as a false "removed + added". This module matches on the *evidence*: code,
name, WBS, activity codes, duration and dates. It distinguishes:

  * exact      — same code in both revisions
  * renamed    — same code, materially different name
  * idchange   — different code, but the same work (matched on the evidence)
  * added      — present only in the revised revision (true new scope)
  * removed    — present only in the original revision (true dropped scope)
  * moved_wbs  — a matched activity whose WBS path changed

The output also carries a ``canonical`` map ``rev1_code -> canonical_code`` so the
revised revision can be re-keyed onto the original's code space (see
``canonicalize``); every downstream engine then aligns an ID-changed pair
automatically.

Everything here is pure (reads dicts, returns dicts) so it is unit-testable
without parsing a file.
"""
import copy
from difflib import SequenceMatcher


# ── Matching thresholds & weights (documented so the rule is auditable) ──────
ACCEPT_SCORE = 0.62      # minimum evidence score to call two different-code activities "the same work"
RENAME_RATIO = 0.80      # name similarity at/above which a same-code name change is cosmetic, below = renamed

# Evidence weights — sum to 1.0. Name dominates; WBS/codes/shape corroborate.
_W_NAME = 0.50
_W_WBS = 0.20
_W_CODES = 0.12
_W_DUR = 0.10
_W_DATE = 0.08


def _norm_name(s):
    """Lowercase, collapse whitespace and drop punctuation noise for a stable comparison."""
    s = (s or '').lower().strip()
    out = []
    prev_space = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            prev_space = False
        elif ch in ' -_/&,.()[]':
            if not prev_space:
                out.append(' ')
                prev_space = True
    return ''.join(out).strip()


def name_ratio(a, b):
    """Similarity of two activity names in [0, 1] after normalisation."""
    na, nb = _norm_name(a), _norm_name(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _dur_ratio(a, b):
    da = a.get('planned_duration') or 0.0
    db = b.get('planned_duration') or 0.0
    if da <= 0 and db <= 0:
        return 1.0
    hi = max(da, db)
    if hi <= 0:
        return 1.0
    return 1.0 - min(abs(da - db) / hi, 1.0)


def _date_ratio(a, b):
    """1.0 when planned starts are within a few days, decaying to 0 over ~120 days."""
    sa, sb = a.get('planned_start'), b.get('planned_start')
    if not (hasattr(sa, 'toordinal') and hasattr(sb, 'toordinal')):
        return 0.5                                  # unknown — neutral, don't reward or punish
    gap = abs(sa.toordinal() - sb.toordinal())
    return max(0.0, 1.0 - gap / 120.0)


def _codes_ratio(a, b):
    ca, cb = a.get('activity_codes') or {}, b.get('activity_codes') or {}
    if not ca and not cb:
        return 0.5                                  # neither carries codes — neutral
    keys = set(ca) | set(cb)
    if not keys:
        return 0.5
    same = sum(1 for k in keys if ca.get(k) is not None and ca.get(k) == cb.get(k))
    return same / len(keys)


def evidence_score(a, b):
    """Weighted evidence that two activities are the same work, in [0, 1].

    Same WBS path is a strong corroborator; name similarity dominates; duration,
    dates and activity codes fine-tune. Pure and unit-tested."""
    wbs = 1.0 if (a.get('wbs_path') and a.get('wbs_path') == b.get('wbs_path')) else 0.0
    return round(
        _W_NAME * name_ratio(a.get('name'), b.get('name'))
        + _W_WBS * wbs
        + _W_CODES * _codes_ratio(a, b)
        + _W_DUR * _dur_ratio(a, b)
        + _W_DATE * _date_ratio(a, b),
        4,
    )


def _index_by_code(data):
    out = {}
    for act in data.activities.values():
        code = act.get('id')
        if code:
            out[code] = act
    return out


def match_activities(rev0, rev1, accept=ACCEPT_SCORE):
    """Reconcile two revisions' activities on the evidence, not the code alone.

    Returns a dict with:
      pairs       [{code0, code1, canonical, match, act0, act1, score, moved_wbs}]
      added       [act1, ...]   present only in rev1 (true new scope)
      removed     [act0, ...]   present only in rev0 (true dropped scope)
      id_changes  [pair, ...]   subset of pairs where code0 != code1
      renamed     [pair, ...]   subset of pairs where the name changed materially
      moved_wbs   [pair, ...]   subset of pairs whose WBS path changed
      canonical   {rev1_code: canonical_code}
    """
    by0, by1 = _index_by_code(rev0), _index_by_code(rev1)
    pairs, canonical = [], {}

    def _pair(code0, code1, a0, a1, match, score):
        moved = bool(a0.get('wbs_path') and a1.get('wbs_path') and a0['wbs_path'] != a1['wbs_path'])
        p = {'code0': code0, 'code1': code1, 'canonical': code0,
             'act0': a0, 'act1': a1, 'match': match, 'score': score, 'moved_wbs': moved}
        pairs.append(p)
        canonical[code1] = code0
        return p

    # 1) Exact code matches first (the common case) — renamed if the name drifted.
    for code in sorted(set(by0) & set(by1)):
        a0, a1 = by0[code], by1[code]
        nr = name_ratio(a0.get('name'), a1.get('name'))
        _pair(code, code, a0, a1, 'renamed' if nr < RENAME_RATIO else 'exact', round(nr, 4))

    # 2) Fuzzy-match the leftovers (different code, possibly same work). Greedy 1-1 on
    #    the best evidence score above the accept threshold.
    left0 = sorted(set(by0) - set(by1))
    left1 = sorted(set(by1) - set(by0))
    candidates = []
    for c0 in left0:
        for c1 in left1:
            s = evidence_score(by0[c0], by1[c1])
            if s >= accept:
                candidates.append((s, c0, c1))
    candidates.sort(key=lambda t: (-t[0], t[1], t[2]))
    used0, used1 = set(), set()
    for s, c0, c1 in candidates:
        if c0 in used0 or c1 in used1:
            continue
        used0.add(c0)
        used1.add(c1)
        _pair(c0, c1, by0[c0], by1[c1], 'idchange', s)

    added = [by1[c] for c in left1 if c not in used1]
    removed = [by0[c] for c in left0 if c not in used0]

    return {
        'pairs': pairs,
        'added': added,
        'removed': removed,
        'id_changes': [p for p in pairs if p['code0'] != p['code1']],
        'renamed': [p for p in pairs if p['match'] == 'renamed'],
        'moved_wbs': [p for p in pairs if p['moved_wbs']],
        'canonical': canonical,
    }


def canonicalize(rev1, canonical_map):
    """Return a shallow clone of the revised ScheduleData with every activity's ``id``
    re-keyed to its matched original code (its ``orig_id`` preserves the real code).

    Relationships reference per-file ObjectIds and resolve their endpoint codes through
    ``activities[oid]['id']``, so remapping the id is enough for ``MatchedSchedules`` and
    the critical-path engine to align an ID-changed pair — no other structure changes.
    Unchanged activities keep their original dict (shared, read-only)."""
    clone = copy.copy(rev1)
    new_acts = {}
    for oid, act in rev1.activities.items():
        code = act.get('id')
        canon = canonical_map.get(code, code)
        if canon != code:
            na = dict(act)
            na['id'] = canon
            na['orig_id'] = code
            new_acts[oid] = na
        else:
            new_acts[oid] = act
    clone.activities = new_acts
    bb = getattr(rev1, 'baseline_by_id', None) or {}
    if bb:
        clone.baseline_by_id = {canonical_map.get(k, k): v for k, v in bb.items()}
    return clone
