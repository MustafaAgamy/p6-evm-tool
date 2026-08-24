"""Out-of-Sequence — Resolve & Correct.

The planner accepts (and may edit) the proposed correction on an out-of-sequence
finding; this module

  1. **re-validates** — applies the accepted corrections to an in-memory copy of the
     network and re-runs the SAME detection engine (the source of truth). A finding is
     *resolved* only when the out-of-sequence condition genuinely no longer holds; and

  2. **exports a corrected schedule** — writes the accepted relationship changes back to
     a copy of the imported file, in the same format (P6 XML or XER). Only relationship
     Type / Lag / existence is touched — actuals, % complete and dates are never changed.
     P6 reschedules on F9; the tool never invents a date.

Detection is untouched. This layer only *applies* what the planner accepted and lets the
engine re-check it.
"""
import types

from p6_evm.parser import parse_file
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.out_of_sequence import run_out_of_sequence

_REL_TYPES = {'FS', 'SS', 'FF', 'SF'}


# ── Accepted-op normalisation ────────────────────────────────────────────────

def _norm_op(op):
    """A client-accepted correction → a stable internal shape.

    action ∈ {'change', 'remove', 'replace', 'add', 'data'}. 'data' (a wrong actual
    date) is never applied — no relationship edit clears it.
    """
    action = (op.get('action') or '').lower()
    lag = op.get('new_lag_days')
    return {
        'finding_id': op.get('finding_id') or '',
        'action': action,
        'pred_id': op.get('pred_id') or '',
        'succ_id': op.get('succ_id') or '',
        'new_type': ((op.get('new_type') or '').upper() or None),
        'new_lag_days': (float(lag) if lag is not None else None),
        'new_pred_id': op.get('new_pred_id') or '',
        'reason': op.get('reason') or '',
    }


def _oid_to_code(data):
    return {oid: (a.get('id') or '') for oid, a in data.activities.items()}


def _code_to_oids(data):
    m = {}
    for oid, a in data.activities.items():
        m.setdefault(a.get('id') or '', []).append(oid)
    return m


# ── Re-validation (in-memory, re-runs the detection engine) ──────────────────

def apply_ops_to_relationships(data, accepted):
    """Return a NEW relationships list with the accepted corrections applied by activity
    CODE — to every duplicate copy of a code pair, matching the file writer so re-validation
    and the exported file always agree. 'data' corrections are no-ops (they stay Open)."""
    oid_to_code = _oid_to_code(data)
    code_to_oids = _code_to_oids(data)
    rels = [dict(r) for r in data.relationships]

    def _match(r, pc, sc):
        return oid_to_code.get(r['pred_id']) == pc and oid_to_code.get(r['succ_id']) == sc

    for raw in accepted:
        o = _norm_op(raw)
        act, pc, sc = o['action'], o['pred_id'], o['succ_id']
        if act == 'data' or not sc:
            continue
        if act in ('remove', 'replace'):
            rels = [r for r in rels if not _match(r, pc, sc)]
        if act == 'change':
            for r in rels:
                if _match(r, pc, sc):
                    if o['new_type'] in _REL_TYPES:
                        r['type'] = o['new_type']
                    if o['new_lag_days'] is not None:
                        r['lag_days'] = o['new_lag_days']
        if act in ('add', 'replace'):
            npc = o['new_pred_id'] or pc
            p_oids, s_oids = code_to_oids.get(npc), code_to_oids.get(sc)
            if p_oids and s_oids:
                rels.append({
                    'pred_id': p_oids[0], 'succ_id': s_oids[0],
                    'type': o['new_type'] if o['new_type'] in _REL_TYPES else 'FS',
                    'lag_days': o['new_lag_days'] if o['new_lag_days'] is not None else 0.0,
                })
    return rels


def revalidate(data, config, accepted):
    """Apply the accepted corrections to a graph copy, re-run the detection engine, and
    report which accepted findings are now genuinely resolved. Returns the fresh (post-
    correction) findings plus the resolved finding_ids and the recomputed KPIs."""
    new_rels = apply_ops_to_relationships(data, accepted)
    shim = types.SimpleNamespace(
        activities=data.activities, relationships=new_rels,
        calendars=getattr(data, 'calendars', {}) or {},
        project=getattr(data, 'project', None))
    fresh = run_out_of_sequence(ScheduleGraph(shim), config)
    fresh_ids = {f['finding_id'] for f in fresh['findings']}
    accepted_ids = {_norm_op(o)['finding_id'] for o in accepted if _norm_op(o)['finding_id']}
    resolved = sorted(accepted_ids - fresh_ids)
    return {
        'findings': fresh['findings'],
        'fresh_ids': sorted(fresh_ids),
        'resolved': resolved,
        'kpis': fresh['kpis'],
    }


def revalidate_from_path(path, config, accepted):
    return revalidate(parse_file(path), config, accepted)


# ── Corrected-file export ────────────────────────────────────────────────────

def _succ_day_hours(data, succ_code):
    for _oid, a in data.activities.items():
        if a.get('id') == succ_code:
            cal = (getattr(data, 'calendars', {}) or {}).get(a.get('calendar_id'))
            return (getattr(cal, 'day_hours', 8.0) or 8.0) if cal is not None else 8.0
    return 8.0


def _current_type(data, pc, sc):
    oid_to_code = _oid_to_code(data)
    for r in data.relationships:
        if oid_to_code.get(r['pred_id']) == pc and oid_to_code.get(r['succ_id']) == sc:
            return r.get('type', 'FS')
    return 'FS'


def to_file_ops(accepted, data):
    """Translate accepted corrections → the file-writer op vocabulary shared with
    ``p6_compare.revert``: set_rel / remove_rel / add_rel, with the lag already converted
    to hours (P6 stores lag in hours in both XML and XER)."""
    ops = []
    for raw in accepted:
        o = _norm_op(raw)
        act, pc, sc = o['action'], o['pred_id'], o['succ_id']
        if act == 'data' or not sc:
            continue
        day_hours = _succ_day_hours(data, sc)
        lag_days = o['new_lag_days'] if o['new_lag_days'] is not None else 0.0
        lag_hours = float(lag_days) * day_hours
        typ = o['new_type'] or _current_type(data, pc, sc)
        if act == 'remove':
            ops.append({'kind': 'remove_rel', 'pred_code': pc, 'succ_code': sc})
        elif act == 'change':
            ops.append({'kind': 'set_rel', 'pred_code': pc, 'succ_code': sc,
                        'type': typ, 'lag_hours': lag_hours})
        elif act == 'add':
            ops.append({'kind': 'add_rel', 'pred_code': pc, 'succ_code': sc,
                        'type': typ, 'lag_hours': lag_hours})
        elif act == 'replace':
            npc = o['new_pred_id'] or pc
            ops.append({'kind': 'remove_rel', 'pred_code': pc, 'succ_code': sc})
            ops.append({'kind': 'add_rel', 'pred_code': npc, 'succ_code': sc,
                        'type': typ, 'lag_hours': lag_hours})
    return ops


_CORRECTION_NOTE = ('Out-of-Sequence — corrected schedule. Relationship logic revised to '
                    'match actual execution (accepted corrections only). Actuals and dates '
                    'untouched — reschedule (F9) in P6.')


def write_corrected(source_path, accepted, out_path, note=_CORRECTION_NOTE):
    """Write a corrected copy of the imported schedule with the accepted relationship
    corrections applied, in the same format as the source (P6 XML or XER)."""
    data = parse_file(source_path)
    ops = to_file_ops(accepted, data)
    low = source_path.lower()
    if low.endswith('.xml'):
        from p6_compare.revert import write_corrected_xml
        return write_corrected_xml(source_path, ops, out_path, note=note)
    if low.endswith('.xer'):
        return write_corrected_xer(source_path, ops, out_path, note=note)
    raise ValueError('Corrected schedule export supports P6 XML (.xml) or XER (.xer) only.')


# ── XER writer (in-place TASKPRED edit — no XER writer existed before) ────────

_XER_PRED_TYPE = {'FS': 'PR_FS', 'SS': 'PR_SS', 'FF': 'PR_FF', 'SF': 'PR_SF'}


def _fmt_hours(v):
    v = float(v or 0.0)
    return str(int(v)) if v == int(v) else repr(v)


def write_corrected_xer(source_path, ops, out_path, note=None):
    """Apply set_rel / remove_rel / add_rel to a copy of the update XER by editing the
    TASKPRED table in place — change a predecessor's type/lag, drop a relationship row,
    or append a new one (cloned from an existing row so every required column is present).
    Every other table is preserved verbatim. TASKPRED matches on internal task ids, so
    ops (keyed by activity code) are expanded to all task-id pairs for that code — duplicate
    codes are handled the same way the XML writer does. Returns {'applied', 'out_path'}."""
    from p6_evm.xer import _read_text
    text = _read_text(source_path)
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = [ln.rstrip('\r') for ln in text.split('\n')]

    # Pass 1 — map activity code → [task_id] from the TASK table.
    code_to_taskids = {}
    cur, fields = None, []
    for ln in lines:
        parts = ln.split('\t')
        tag = parts[0]
        if tag == '%T':
            cur = parts[1] if len(parts) > 1 else None
            fields = []
        elif tag == '%F':
            fields = parts[1:]
        elif tag == '%R' and cur == 'TASK':
            row = dict(zip(fields, parts[1:]))
            code, tid = row.get('task_code'), row.get('task_id')
            if code and tid:
                code_to_taskids.setdefault(code, []).append(tid)

    # Expand code-pair ops → (pred_task_id, succ_task_id) targets.
    remove_pairs, set_pairs, add_ops = set(), {}, []
    for op in ops:
        kind = op.get('kind')
        pc, sc = op.get('pred_code'), op.get('succ_code')
        p_ids, s_ids = code_to_taskids.get(pc, []), code_to_taskids.get(sc, [])
        if kind == 'remove_rel':
            for pi in p_ids:
                for si in s_ids:
                    remove_pairs.add((pi, si))
        elif kind == 'set_rel':
            for pi in p_ids:
                for si in s_ids:
                    set_pairs[(pi, si)] = (op.get('type', 'FS'), op.get('lag_hours', 0.0))
        elif kind == 'add_rel':
            if p_ids and s_ids:
                add_ops.append((p_ids[0], s_ids[0], op.get('type', 'FS'), op.get('lag_hours', 0.0)))

    # Pass 2 — rewrite. Track TASKPRED fields + the max row id + a template row for adds.
    tp_fields, tp_template, max_pred_id = [], None, 0
    for ln in lines:
        parts = ln.split('\t')
        if parts[0] == '%T':
            cur = parts[1] if len(parts) > 1 else None
        elif parts[0] == '%F' and cur == 'TASKPRED':
            tp_fields = parts[1:]
        elif parts[0] == '%R' and cur == 'TASKPRED':
            if tp_template is None:
                tp_template = parts[1:]
            row = dict(zip(tp_fields, parts[1:]))
            try:
                max_pred_id = max(max_pred_id, int(row.get('task_pred_id') or 0))
            except (TypeError, ValueError):
                pass

    def _idx(name):
        return tp_fields.index(name) if name in tp_fields else -1

    i_pred_id = _idx('task_pred_id')
    i_task = _idx('task_id')
    i_pred_task = _idx('pred_task_id')
    i_type = _idx('pred_type')
    i_lag = _idx('lag_hr_cnt')

    def _new_row(pred_task, succ_task, rel_type, lag_hours):
        nonlocal max_pred_id
        vals = list(tp_template) if tp_template else [''] * len(tp_fields)
        if len(vals) < len(tp_fields):
            vals += [''] * (len(tp_fields) - len(vals))
        max_pred_id += 1
        if i_pred_id >= 0:
            vals[i_pred_id] = str(max_pred_id)
        if i_task >= 0:
            vals[i_task] = succ_task
        if i_pred_task >= 0:
            vals[i_pred_task] = pred_task
        if i_type >= 0:
            vals[i_type] = _XER_PRED_TYPE.get(rel_type, 'PR_FS')
        if i_lag >= 0:
            vals[i_lag] = _fmt_hours(lag_hours)
        return '%R\t' + '\t'.join(vals)

    out_lines, applied = [], 0
    cur = None
    in_taskpred = False
    emitted_adds = False

    def _flush_adds():
        nonlocal applied, emitted_adds
        if add_ops and not emitted_adds and i_task >= 0 and i_pred_task >= 0:
            for (pi, si, t, lag) in add_ops:
                out_lines.append(_new_row(pi, si, t, lag))
                applied += 1
        emitted_adds = True

    for ln in lines:
        parts = ln.split('\t')
        tag = parts[0]
        if tag == '%T':
            # Leaving TASKPRED for a new table → append any pending new rows first.
            if in_taskpred:
                _flush_adds()
            cur = parts[1] if len(parts) > 1 else None
            in_taskpred = (cur == 'TASKPRED')
            out_lines.append(ln)
            continue
        if tag == '%E':
            if in_taskpred:
                _flush_adds()
            in_taskpred = False
            out_lines.append(ln)
            continue
        if in_taskpred and tag == '%R':
            vals = parts[1:]
            pair = (vals[i_pred_task] if i_pred_task >= 0 and i_pred_task < len(vals) else None,
                    vals[i_task] if i_task >= 0 and i_task < len(vals) else None)
            if pair in remove_pairs:
                applied += 1
                continue  # drop the relationship row
            if pair in set_pairs:
                rel_type, lag_hours = set_pairs[pair]
                if i_type >= 0 and i_type < len(vals):
                    vals[i_type] = _XER_PRED_TYPE.get(rel_type, 'PR_FS')
                if i_lag >= 0 and i_lag < len(vals):
                    vals[i_lag] = _fmt_hours(lag_hours)
                applied += 1
                out_lines.append('%R\t' + '\t'.join(vals))
                continue
            out_lines.append(ln)
            continue
        out_lines.append(ln)

    # File with no %E terminator: flush any adds at the very end.
    if in_taskpred:
        _flush_adds()

    if note:
        # XER comments aren't standard; carry the note as an ERMHDR-adjacent comment line
        # that P6 ignores on import is risky — instead leave the file clean. (Kept param for
        # signature parity with the XML writer.)
        pass

    with open(out_path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(newline.join(out_lines))
    return {'applied': applied, 'out_path': out_path}
