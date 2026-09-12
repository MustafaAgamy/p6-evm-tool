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
    for fmt in ('%d-%b-%Y', '%d-%b-%y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
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


def revalidate(data, config, accepted, completion=None):
    """Apply the accepted type-change fixes to a graph copy, re-run the dangling engine, and report
    which activities are now genuinely no longer dangling. Fixes that would push the contractual
    completion milestone past its date are NOT applied and are returned in ``blocked``."""
    blocked = milestone_blocked(data, accepted, completion)
    effective = [op for op in accepted if op.get('finding_id') not in blocked]
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
    return {
        'findings': fresh['findings'],
        'fresh_ids': sorted({f['finding_id'] for f in fresh['findings']}),
        'resolved': resolved,
        'blocked': sorted(blocked),
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
    applied, in the same format as the source (P6 XML or XER). Fixes blocked by the contract-milestone
    guard are excluded so a milestone-exceeding change is never written. Reuses the shared writers."""
    if completion:
        blocked = milestone_blocked(parse_file(source_path), accepted, completion)
        accepted = [op for op in accepted if op.get('finding_id') not in blocked]
    return _oos_write_corrected(source_path, accepted, out_path, note=note)
