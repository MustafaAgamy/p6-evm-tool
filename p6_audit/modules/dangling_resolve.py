"""Dangling Activities — Resolve & Correct.

The planner accepts (and may edit) the proposed fix on a dangling finding — a relationship-type
change on a link that already exists (e.g. Finish-to-Finish → Finish-to-Start). This module

  1. **re-validates** — applies the accepted fixes to an in-memory copy of the network and re-runs
     the SAME dangling detection engine (the source of truth). A finding is *resolved* only when the
     activity is genuinely no longer dangling; and

  2. **exports a corrected schedule** — writes the accepted relationship changes back to a copy of
     the imported file, in the same format (P6 XML or XER). Only relationship Type / Lag is touched —
     actuals, % complete and dates are never changed. P6 reschedules on F9.

Where an activity has no predecessor / no successor at all there is nothing to re-type, so the UI
marks that side *Needs Planner Review* and sends no op — the tool never invents a link.

**Contract-milestone guard.** When the planner has entered a contractual completion milestone (the
Milestone Check gate), a fix is *blocked* if applying it would push that milestone's completion past
its contract date. The tool is offline — it never runs P6's F9 — so the impact is ESTIMATED with the
in-tool forward-pass scheduler (`p6_compare.schedule`, the same engine behind the instant but-for
delay). A blocked fix is never applied and never written to the corrected file; the UI shows
"Changing this could exceeds the contractual milestone" instead. Because it is an estimate, the guard
only blocks a fix that, on its own, moves the completion later AND past the contract date.

Detection is untouched. Op application and the corrected-file writers are reused verbatim from
``oos_resolve`` (they are engine-agnostic — they only apply relationship operations); only the
re-validation engine differs.
"""
import types
from datetime import datetime

from p6_evm.parser import parse_file
from p6_audit.graph import ScheduleGraph
from p6_audit.presentation import build_presentation
from p6_audit.modules.dangling import run_dangling
from p6_audit.modules.oos_resolve import (
    apply_ops_to_relationships,
    write_corrected as _oos_write_corrected,
)
from p6_compare.schedule import forward_pass

_CORRECTION_NOTE = ('Dangling Activities — corrected schedule. Relationship types revised so each '
                    'activity start/finish is driven by real logic (accepted fixes only). Actuals '
                    'and dates untouched — reschedule (F9) in P6.')

# Ibrahim's exact wording for a fix held back by the contract-milestone guard.
MILESTONE_BLOCK_MESSAGE = 'Changing this could exceeds the contractual milestone'


def _parse_date(v):
    """Tolerant date parse — accepts a datetime, P6-style '9-Feb-2027', ISO, or common numerics."""
    if isinstance(v, datetime):
        return v
    if not v:
        return None
    s = str(v).strip()
    for fmt in ('%d-%b.%Y', '%d-%b-%Y', '%d-%b-%y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s[:len(fmt) + 4], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s[:19])
    except ValueError:
        return None


def _shim(data, rels):
    return types.SimpleNamespace(
        activities=data.activities, relationships=rels,
        calendars=getattr(data, 'calendars', {}) or {},
        project=getattr(data, 'project', None))


def _completion_finish(data, rels, comp_oids):
    """Forward-pass estimate of the completion activity's finish for the given relationships. Takes the
    latest across every ObjectId that shares the completion code (P6 exports can duplicate codes)."""
    ef = forward_pass(_shim(data, rels))
    vals = [ef.get(o) for o in comp_oids if ef.get(o)]
    return max(vals) if vals else None


def milestone_blocked(data, accepted, completion):
    """Finding_ids whose fix would push the contractual completion milestone past its contract date.

    ``completion`` = {'activity_id', 'contract_date'} (the matched completion milestone the planner
    entered). A finding is blocked when applying JUST its ops to the imported schedule makes the
    completion finish (a) later than the contract date AND (b) later than it was without the fix — so a
    schedule that is already late is not blamed on a fix that does not move completion. Offline
    estimate (no F9)."""
    if not completion:
        return set()
    # Best-effort estimate — the guard must NEVER break Apply. Any failure computing the offline
    # forward pass falls open (allow the fix) rather than erroring the whole re-validation.
    try:
        aid = completion.get('activity_id')
        contract = _parse_date(completion.get('contract_date'))
        if not aid or not contract:
            return set()
        comp_oids = [oid for oid, a in data.activities.items() if a.get('id') == aid]
        if not comp_oids:
            return set()
        base_finish = _completion_finish(data, data.relationships, comp_oids)
        by_finding = {}
        for op in accepted:
            fid = op.get('finding_id')
            if fid:
                by_finding.setdefault(fid, []).append(op)
        blocked = set()
        for fid, ops in by_finding.items():
            rels = apply_ops_to_relationships(data, ops)       # this finding's fix on the original
            fx = _completion_finish(data, rels, comp_oids)
            if fx and fx.date() > contract.date() and (base_finish is None or fx > base_finish):
                blocked.add(fid)
        return blocked
    except Exception as exc:
        import sys
        print(f'[dangling] milestone guard skipped (estimate failed): {exc}', file=sys.stderr)
        return set()


def _variants(op):
    """The ways one side's fix can be applied, most wanted first: as asked; the same type with no
    lag; and - the P6 pairing - the existing link kept and its partner added on the same two
    activities (Start-to-Start closes a dangling start, Finish-to-Finish a dangling finish)."""
    out = [op]
    if (op.get('action') or 'change') != 'change':
        return out
    try:
        lag = float(op.get('new_lag_days') or 0)
    except (TypeError, ValueError):
        lag = 0.0
    if lag:
        out.append(dict(op, new_lag_days=0))
    out.append(dict(op, action='add', new_pred_id=op.get('pred_id'),
                    new_type='SS' if op.get('side') == 'start' else 'FF', new_lag_days=0))
    return out


def milestone_safe(data, accepted, completion):
    """The accepted fixes made safe for the contractual completion milestone the planner entered.

    Returns ``(effective_ops, adjusted_ops, blocked_finding_ids)``. Every fix is applied when all of
    them together leave the completion milestone on or before its contract date (or no later than it
    already is). Otherwise each finding is taken in turn, on top of the ones already kept, and the
    first way of applying it that does not move the milestone is used (see ``_variants``); the ops
    that differ from what was asked are returned in ``adjusted_ops``. A finding with no such way is
    held back (``blocked``) and none of its ops are applied. Offline estimate (no F9); any failure
    falls open - the guard must never break Apply."""
    accepted = list(accepted or [])
    if not completion or not accepted:
        return accepted, [], set()
    try:
        import itertools
        aid = completion.get('activity_id')
        contract = _parse_date(completion.get('contract_date'))
        comp_oids = [oid for oid, a in data.activities.items() if a.get('id') == aid] if aid else []
        if not contract or not comp_oids:
            return accepted, [], set()
        base_finish = _completion_finish(data, data.relationships, comp_oids)

        def pushes(ops):
            fx = _completion_finish(data, apply_ops_to_relationships(data, ops), comp_oids)
            return bool(fx and fx.date() > contract.date() and (base_finish is None or fx > base_finish))

        if not pushes(accepted):
            return accepted, [], set()
        groups, order = {}, []
        for op in accepted:
            key = op.get('finding_id') or id(op)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(op)
        kept, adjusted, blocked = [], [], set()
        for key in order:
            ops = groups[key]
            for combo in itertools.product(*[_variants(o) for o in ops]):
                if not pushes(kept + list(combo)):
                    kept += list(combo)
                    adjusted += [c for c, o in zip(combo, ops) if c is not o]
                    break
            else:
                blocked.add(ops[0].get('finding_id') or '')
        return kept, adjusted, {b for b in blocked if b}
    except Exception as exc:
        import sys
        print(f'[dangling] milestone guard skipped (estimate failed): {exc}', file=sys.stderr)
        return accepted, [], set()


def revalidate(data, config, accepted, completion=None):
    """Apply the accepted fixes to a graph copy, re-run the dangling engine, and report which
    activities are now genuinely no longer dangling. The fixes never move the contractual completion
    milestone the planner entered: a fix that would is applied in a way that does not (``adjusted`` -
    the screen swaps these ops in, so the download writes what was checked), and one that cannot be
    is held back (``blocked``)."""
    effective, adjusted, blocked = milestone_safe(data, accepted, completion)
    new_rels = apply_ops_to_relationships(data, effective)
    fresh = run_dangling(ScheduleGraph(_shim(data, new_rels)), config)
    still_dangling = {f['activity_id'] for f in fresh['findings']}
    # A finding is resolved only when its ACTIVITY is no longer dangling at all. Fixing one side of a
    # both-sided finding changes its issue (and thus its finding_id), so a vanished finding_id is NOT
    # proof on its own — honest accounting that never credits a half-fix.
    resolved = sorted({
        (x.get('finding_id') or '')
        for x in effective
        if x.get('finding_id') and x.get('activity_id') and x['activity_id'] not in still_dangling
    })
    # P6's own activity totals beside the check, as on import (a fix never changes them)
    _g = ScheduleGraph(data)
    fresh['p6_counts'] = {'total': len(_g.p6_all()), 'remaining': len(_g.p6_remaining())}
    return {
        'findings': fresh['findings'],
        'fresh_ids': sorted({f['finding_id'] for f in fresh['findings']}),
        'resolved': resolved,
        'blocked': sorted(blocked),
        'adjusted': adjusted,
        'warned': [],
        'kpis': fresh['kpis'],
        # The recomputed score/grade/% + presentation of the CORRECTED (post-fix) state, so the screen's
        # execution dashboard (gauge + KPI tiles) updates live as findings resolve — the score rises.
        'score': fresh.get('score'),
        'grade': fresh.get('grade'),
        'pct': fresh.get('pct'),
        'presentation': build_presentation(fresh),
    }


def revalidate_from_path(path, config, accepted, completion=None):
    return revalidate(parse_file(path), config, accepted, completion=completion)


def write_corrected(source_path, accepted, out_path, completion=None, note=_CORRECTION_NOTE):
    """Write a corrected copy of the imported schedule with the accepted relationship-type changes
    applied, in the same format as the source (P6 XML or XER). With ``completion`` the fixes pass
    through the same contract-milestone guard as the screen, so the file never carries a change that
    moves the completion milestone. Reuses the shared writers."""
    if completion:
        accepted, _adj, _blk = milestone_safe(parse_file(source_path), accepted, completion)
    return _oos_write_corrected(source_path, accepted, out_path, note=note)
