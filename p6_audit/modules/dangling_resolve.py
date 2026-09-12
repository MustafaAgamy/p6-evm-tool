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

Detection is untouched. Op application and the corrected-file writers are reused verbatim from
``oos_resolve`` (they are engine-agnostic — they only apply relationship operations); only the
re-validation engine differs.
"""
import types

from p6_evm.parser import parse_file
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.dangling import run_dangling
from p6_audit.modules.oos_resolve import (
    apply_ops_to_relationships,
    write_corrected as _oos_write_corrected,
)

_CORRECTION_NOTE = ('Dangling Activities — corrected schedule. Relationship types revised so each '
                    'activity start/finish is driven by real logic (accepted fixes only). Actuals '
                    'and dates untouched — reschedule (F9) in P6.')


def revalidate(data, config, accepted):
    """Apply the accepted type-change fixes to a graph copy, re-run the dangling engine, and report
    which activities are now genuinely no longer dangling. Returns the fresh (post-fix) findings, the
    resolved finding_ids and the recomputed KPIs."""
    new_rels = apply_ops_to_relationships(data, accepted)
    shim = types.SimpleNamespace(
        activities=data.activities, relationships=new_rels,
        calendars=getattr(data, 'calendars', {}) or {},
        project=getattr(data, 'project', None))
    fresh = run_dangling(ScheduleGraph(shim), config)
    still_dangling = {f['activity_id'] for f in fresh['findings']}
    # A finding is resolved only when its ACTIVITY is no longer dangling at all. Fixing one side of a
    # both-sided finding changes its issue (and thus its finding_id), so a vanished finding_id is NOT
    # proof on its own — honest accounting that never credits a half-fix.
    resolved = sorted({
        (x.get('finding_id') or '')
        for x in accepted
        if x.get('finding_id') and x.get('activity_id') and x['activity_id'] not in still_dangling
    })
    return {
        'findings': fresh['findings'],
        'fresh_ids': sorted({f['finding_id'] for f in fresh['findings']}),
        'resolved': resolved,
        'kpis': fresh['kpis'],
    }


def revalidate_from_path(path, config, accepted):
    return revalidate(parse_file(path), config, accepted)


def write_corrected(source_path, accepted, out_path, note=_CORRECTION_NOTE):
    """Write a corrected copy of the imported schedule with the accepted relationship-type changes
    applied, in the same format as the source (P6 XML or XER). Reuses the shared writers."""
    return _oos_write_corrected(source_path, accepted, out_path, note=note)
