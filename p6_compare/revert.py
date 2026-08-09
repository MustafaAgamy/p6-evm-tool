"""Corrected "but-for" XML — revert the flagged manipulations back to baseline.

`revert_operations` turns the driving-logic and duration diffs into a list of
concrete, selectable operations, each locatable in the update XML and carrying its
baseline target values in raw hours. `write_corrected_xml` applies the chosen
operations to a copy of the update XML: relationships, lags and durations go back
to baseline while every actual / progress field is left untouched. The file can
then be rescheduled (F9) in P6 to reveal the genuine delay.

The tool never computes a date — P6 does the scheduling. This only edits the inputs.
Only the update-as-XML case is supported (P6 exports updates as XML for this).
"""
import copy
import re
import xml.etree.ElementTree as ET

# EVM/other modules must not change how a number is derived — this module only
# writes P6 input fields (Type, Lag, PlannedDuration, RemainingDuration).

_REL_TYPE_XML = {'FS': 'Finish to Start', 'SS': 'Start to Start',
                 'FF': 'Finish to Finish', 'SF': 'Start to Finish'}


def _lag_label(type_, lag_days):
    lag = lag_days or 0.0
    sign = '+' if lag >= 0 else '−'
    return f"{type_}{sign}{abs(round(lag, 1)):g}"


def _differs(a, b):
    if a.get('type') != b.get('type'):
        return True
    return abs((a.get('lag_hours', 0.0) or 0.0) - (b.get('lag_hours', 0.0) or 0.0)) > 1e-6


def _remaining_target_hours(base_planned, upd_planned, upd_remaining):
    """Corrected remaining duration = baseline original minus the time already spent
    (Ibrahim's rule). Time spent is the update's consumed duration. Never negative."""
    spent = max(0.0, (upd_planned or 0.0) - (upd_remaining or 0.0))
    return max(0.0, (base_planned or 0.0) - spent)


def _rel_pairs_from_row(row):
    """(pred_code, succ_code) pairs whose driving link changed/was added/removed."""
    succ = row['activity_id']
    pairs = set()
    for p in row.get('update_preds', []):
        if p.get('status') in ('changed', 'added'):
            pairs.add((p['code'], succ))
    for p in row.get('baseline_preds', []):
        if p.get('status') == 'removed':
            pairs.add((p['code'], succ))
    return pairs


def revert_operations(matched, logic, durations):
    """Build the selectable revert plan from the driving-logic and duration diffs.

    Each driving change is resolved against the FULL relationship sets (not just the
    driving subset) so a link that merely became driving is corrected in place, never
    wrongly deleted. Returns a list of op dicts, each with a stable ``id``, a human
    ``label``/``detail``, and the fields the writer needs.
    """
    ops = []
    seen = set()

    for row in logic.get('rows', []):
        for (pred, succ) in sorted(_rel_pairs_from_row(row)):
            if (pred, succ) in seen:
                continue
            seen.add((pred, succ))
            b = matched.baseline_rels.get((pred, succ))
            u = matched.update_rels.get((pred, succ))
            pn = (b or u or {}).get('pred_name', '') or pred
            sn = ((b or u or {}).get('succ_name', '')
                  or matched.update_by_code.get(succ, {}).get('name', '') or succ)
            if b and u:
                if _differs(b, u):
                    ops.append({
                        'id': f'rel:{pred}:{succ}', 'kind': 'set_rel',
                        'activity_id': succ, 'pred_code': pred, 'succ_code': succ,
                        'type': b['type'], 'lag_hours': b.get('lag_hours', 0.0) or 0.0,
                        'label': f'{succ}: revert driving link from {pred}',
                        'detail': (f"{_lag_label(u['type'], u['lag_days'])} → "
                                   f"{_lag_label(b['type'], b['lag_days'])}  ({pn} → {sn})"),
                    })
            elif u and not b:
                ops.append({
                    'id': f'rel:{pred}:{succ}', 'kind': 'remove_rel',
                    'activity_id': succ, 'pred_code': pred, 'succ_code': succ,
                    'label': f'{succ}: remove added link from {pred}',
                    'detail': f"added {_lag_label(u['type'], u['lag_days'])} ({pn} → {sn}) — remove",
                })
            elif b and not u:
                ops.append({
                    'id': f'rel:{pred}:{succ}', 'kind': 'add_rel',
                    'activity_id': succ, 'pred_code': pred, 'succ_code': succ,
                    'type': b['type'], 'lag_hours': b.get('lag_hours', 0.0) or 0.0,
                    'label': f'{succ}: restore removed link from {pred}',
                    'detail': f"restore {_lag_label(b['type'], b['lag_days'])} ({pn} → {sn})",
                })

    for r in durations.get('rows', []):
        code = r['activity_id']
        base = matched.baseline_by_code.get(code, {})
        upd = matched.update_by_code.get(code, {})
        base_planned = base.get('planned_duration', 0.0) or 0.0
        if base_planned <= 0:
            continue   # no meaningful baseline duration to revert to
        upd_planned = upd.get('planned_duration', 0.0) or 0.0
        upd_remaining = upd.get('remaining_duration', 0.0) or 0.0
        ops.append({
            'id': f'dur:{code}', 'kind': 'set_duration',
            'activity_id': code,
            'planned_hours': base_planned,
            'remaining_hours': _remaining_target_hours(base_planned, upd_planned, upd_remaining),
            'label': f'{code}: revert duration to baseline',
            'detail': (f"original {r['update_orig_days']}d → {r['baseline_orig_days']}d; "
                       f"remaining reset to baseline pace"),
        })
    return ops


# ── XML writer ─────────────────────────────────────────────────────────────

def _fmt_hours(v):
    v = float(v or 0.0)
    return str(int(v)) if v == int(v) else repr(v)


def _register_namespaces(path):
    """Register every xmlns declared on the root so the written file keeps P6's
    prefixes (default namespace unprefixed, xsi/xsd intact). Returns the default URI."""
    with open(path, encoding='utf-8') as f:
        head = f.read(4000)
    default = ''
    for m in re.finditer(r'xmlns(?::([\w.\-]+))?="([^"]+)"', head):
        prefix, uri = m.group(1) or '', m.group(2)
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            pass
        if not prefix:
            default = uri
    return default


def write_corrected_xml(update_xml_path, ops, out_path, note=None):
    """Apply ``ops`` to a copy of the update XML and write it to ``out_path``.

    Actuals, % complete and dates are never touched — only Type / Lag / PlannedDuration
    / RemainingDuration on the affected elements. Returns {'applied', 'out_path'}.
    """
    ns_uri = _register_namespaces(update_xml_path)
    ns = f'{{{ns_uri}}}' if ns_uri else ''

    def tag(n):
        return f'{ns}{n}'

    tree = ET.parse(update_xml_path)
    root = tree.getroot()
    project = root.find(tag('Project'))
    if project is None:
        raise ValueError('No <Project> element in the update XML — cannot build a corrected file.')

    def ctext(el, name):
        c = el.find(tag(name))
        return c.text if c is not None else None

    def set_child(el, name, value):
        c = el.find(tag(name))
        if c is None:
            c = ET.SubElement(el, tag(name))
        c.text = value

    code_to_oid, code_to_actel = {}, {}
    for a in project.findall(tag('Activity')):
        code = ctext(a, 'Id')
        if code:
            code_to_oid[code] = ctext(a, 'ObjectId')
            code_to_actel[code] = a

    rel_by_oids, rel_template, max_rel_oid = {}, None, 0
    for r in project.findall(tag('Relationship')):
        rel_by_oids[(ctext(r, 'PredecessorActivityObjectId'),
                     ctext(r, 'SuccessorActivityObjectId'))] = r
        if rel_template is None:
            rel_template = r
        try:
            max_rel_oid = max(max_rel_oid, int(ctext(r, 'ObjectId') or 0))
        except (TypeError, ValueError):
            pass

    applied = 0
    for op in ops:
        kind = op.get('kind')
        if kind == 'set_duration':
            el = code_to_actel.get(op['activity_id'])
            if el is None:
                continue
            set_child(el, 'PlannedDuration', _fmt_hours(op['planned_hours']))
            set_child(el, 'RemainingDuration', _fmt_hours(op['remaining_hours']))
            applied += 1
            continue

        p_oid = code_to_oid.get(op['pred_code'])
        s_oid = code_to_oid.get(op['succ_code'])
        if not p_oid or not s_oid:
            continue

        if kind == 'set_rel':
            el = rel_by_oids.get((p_oid, s_oid))
            if el is None:
                continue
            set_child(el, 'Type', _REL_TYPE_XML.get(op['type'], 'Finish to Start'))
            set_child(el, 'Lag', _fmt_hours(op['lag_hours']))
            applied += 1
        elif kind == 'remove_rel':
            el = rel_by_oids.get((p_oid, s_oid))
            if el is not None:
                project.remove(el)
                applied += 1
        elif kind == 'add_rel':
            new = copy.deepcopy(rel_template) if rel_template is not None else ET.Element(tag('Relationship'))
            max_rel_oid += 1
            set_child(new, 'ObjectId', str(max_rel_oid))
            set_child(new, 'PredecessorActivityObjectId', p_oid)
            set_child(new, 'SuccessorActivityObjectId', s_oid)
            set_child(new, 'Type', _REL_TYPE_XML.get(op['type'], 'Finish to Start'))
            set_child(new, 'Lag', _fmt_hours(op['lag_hours']))
            project.append(new)
            applied += 1

    if note:
        try:
            root.insert(0, ET.Comment(f' {note} '))
        except (TypeError, ValueError):
            pass

    tree.write(out_path, encoding='utf-8', xml_declaration=True)
    return {'applied': applied, 'out_path': out_path}


def ops_from_paths(baseline_path, update_path):
    """Parse a baseline + update and return the full revert plan (the tick-list)."""
    from p6_evm.parser import parse_file
    from p6_audit.graph import ScheduleGraph
    from p6_compare.model import MatchedSchedules
    from p6_compare.diff import driving_link_map, diff_logic, diff_durations
    baseline, update = parse_file(baseline_path), parse_file(update_path)
    matched = MatchedSchedules(baseline, update)
    logic = diff_logic(driving_link_map(ScheduleGraph(baseline)),
                       driving_link_map(ScheduleGraph(update)))
    return revert_operations(matched, logic, diff_durations(matched))


def write_corrected_from_paths(baseline_path, update_path, out_path, selected_ids=None, note=None):
    """Full pipeline for the route: recompute the revert plan from the two files, keep
    only the selected op ids (all if ``selected_ids`` is None), write the corrected XML."""
    ops = ops_from_paths(baseline_path, update_path)
    if selected_ids is not None:
        sel = set(selected_ids)
        ops = [o for o in ops if o['id'] in sel]
    return write_corrected_xml(update_path, ops, out_path, note=note)
