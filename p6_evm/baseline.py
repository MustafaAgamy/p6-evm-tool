"""Apply an attached baseline schedule to an update schedule so EVM matches P6 / the XML.

ONE baseline resolution for every feature (XER = XML, R4) — ``load_schedule`` /
``load_for_project`` / ``resolve_baseline``:

  1. **embedded** — the file carries its baseline project (XML ``<BaselineProject>``);
  2. **attached** — else the baseline file the planner attached for this snapshot
     (Earned Value / Update Analysis ``Attach baseline``, remembered in the DB);
  3. **self**     — else the file's own Planned dates stand in (approximate, and flagged).

So an update + its baseline gives the same numbers whether the baseline is inside the XML or
attached as a separate XER / XML, and an XER or XML without one is labelled, never silent.

A P6 XER *update* export doesn't embed its baseline, so its Planned Value is wrong. When the user
attaches the baseline (a separate XER/XML), this feeds the update both halves P6 anchors PV and the
WBS %-rollup to — the baseline PLANNED DATES and the baseline BUDGET — matched by Activity Id, the
same linkage the XML parser does from <BaselineProject>. metrics.compute() already reads
`baseline_by_id` and `baseline_bac_by_activity`; this just fills them from the attached file.
"""


def apply_baseline(data, baseline_data):
    """Mutate `data` in place: set baseline planned dates + baseline budget from `baseline_data`.

    Returns {'matched': int, 'total': int, 'bac_matched': int} — how many of the update's
    activities line up with the baseline by Activity Id (for the UI's confidence count).
    """
    # Baseline planned dates + object-id → Activity-Id map, keyed by the baseline's Activity Id (code).
    bl_dates = {}
    bl_oid_to_id = {}
    for oid, a in (baseline_data.activities or {}).items():
        aid = a.get('id')
        if not aid:
            continue
        bl_oid_to_id[oid] = aid
        bl_dates[aid] = {'planned_start': a.get('planned_start'),
                         'planned_finish': a.get('planned_finish')}

    # Baseline budget per Activity Id — only where the baseline actually carries cost (mirrors the
    # XML path, where an activity with no baseline resource assignment falls back to the current BAC).
    bl_bac_by_id = {}
    for boid, cost in (getattr(baseline_data, 'bac_by_activity', None) or {}).items():
        aid = bl_oid_to_id.get(boid)
        if aid is not None:
            bl_bac_by_id[aid] = bl_bac_by_id.get(aid, 0.0) + cost

    data.baseline_by_id = bl_dates
    data.baseline_bac_by_code = bl_bac_by_id
    new_bac = {}
    matched = 0
    for oid, a in (data.activities or {}).items():
        aid = a.get('id')
        if aid in bl_dates:
            matched += 1
        if aid in bl_bac_by_id:
            new_bac[oid] = bl_bac_by_id[aid]
    data.baseline_bac_by_activity = new_bac

    return {'matched': matched, 'total': len(data.activities or {}), 'bac_matched': len(new_bac)}


import os
import re

_HASH_PREFIX = re.compile(r'^[0-9a-f]{12}_')


def display_name(path):
    """File name for the screen — drops the XML-cache ``{hash12}_`` prefix."""
    return _HASH_PREFIX.sub('', os.path.basename(path or '')) if path else None


def baseline_expected(data):
    """True when the P6 project NAMES a baseline (XML ``CurrentBaselineProjectObjectId`` / XER
    ``PROJECT.sum_base_proj_id``, other than the project itself). False for a schedule with no
    baseline assigned in P6 — a baseline programme such as GBT REV.03 or MAFI_BASELINE — whose
    own Planned dates ARE its baseline (P6 measures it against itself), so a 'self' result is
    exact, not approximate, and nothing needs attaching."""
    proj = getattr(data, 'project', None) or {}
    bid = str(proj.get('baseline_object_id') or '').strip()
    return bool(bid) and bid != str(proj.get('object_id') or '').strip()


# What to do when an update carries no baseline and none is attached — the SAME words the
# Update Analysis screen and Help show (ui/modules/feature_needs.js UPDATE_NO_BASELINE_ADVICE),
# used by the server's no-baseline answer and by Reporting Studio's Update items.
NO_BASELINE_ADVICE = ('Attach the baseline (XER or XML) with the button on Update Analysis or Earned '
                      'Value — it is remembered for this update and used by every feature — or re-export '
                      'the update from P6 as XML with its baseline project included.')


def expected_baseline_name(data):
    """The name P6 gives the update's baseline (XER BASELINE_EXPORT.proj_name / XML
    <BaselineProject><Name>) — None when no baseline is assigned or the file does not name it."""
    if not baseline_expected(data):
        return None
    return ((getattr(data, 'project', None) or {}).get('baseline_name') or '').strip() or None


def expected_baseline_advice(name):
    """One sentence telling the planner WHICH P6 project to export (ui/modules/baseline.js
    expectedBaselineAdvice says the same). '' when the name is not known."""
    return (f'P6 names “{name}” as this update’s baseline — export that project (XER or XML) '
            f'and attach it.') if name else ''


_BL_COPY = re.compile(r'\s*-\s*B\d+\s*$', re.I)   # P6 names a baseline copy "<project> - B1"


def _norm_name(s):
    return re.sub(r'\s+', ' ', _BL_COPY.sub('', str(s or ''))).strip().lower()


def _name_tokens(s):
    return set(re.findall(r'[a-z0-9]+', str(s or '').lower()))


def baseline_mismatch(expected_name, expected_id, attached_project):
    """None when the attached file is — as far as its identity shows — the baseline P6 names for
    the update; else the attached project's name (for 'P6 names X; you attached Y').

    A P6 baseline is a COPY of the project ("<project> - B1", its own ObjectId), and the planner
    usually exports the original project, so it matches on: the same ObjectId, or the same name
    once the " - Bn" copy suffix is dropped (project name or Project ID), or the attached name
    is the start of the expected one and the rest (e.g. "REV.03") is in its name / Project ID —
    GBT REV.03 'Grain Bulk Terminal Detailed Schedule - Phase I' / GBT-SUB-REV.03 vs P6's
    '… Phase I REV.03 - B1'. Nothing to compare (no expected name) → None: an XML exported
    without its <BaselineProject> carries only the id, which a source project never shares."""
    ap = attached_project or {}
    if expected_id and str(ap.get('object_id') or '').strip() == str(expected_id).strip():
        return None
    if not expected_name:
        return None
    e = _norm_name(expected_name)
    names = [n for n in (_norm_name(ap.get('name')), _norm_name(ap.get('id'))) if n]
    if any(n == e for n in names):
        return None
    toks = _name_tokens(ap.get('name')) | _name_tokens(ap.get('id'))
    if any(e.startswith(n) and _name_tokens(e[len(n):]) <= toks for n in names):
        return None
    return (ap.get('name') or ap.get('id') or 'another project').strip()


def resolve_baseline(data, attached_path=None, parse=None):
    """Settle ``data``'s baseline in place — embedded, else attached, else self — and return
    what was used: {'source', 'name', 'path', 'matched', 'total', 'missing'}. Also stored on
    ``data.baseline_info``. An attached file that lines up with NONE of the activities (the
    wrong project) is not applied; nor is it applied over a baseline embedded in the file.
    """
    total = len(getattr(data, 'activities', None) or {})
    src = getattr(data, 'baseline_source', None)
    if src is None:                                   # older ScheduleData: infer
        src = 'embedded' if getattr(data, 'baseline_by_id', None) else 'self'
        data.baseline_source = src
    info = {'source': src, 'name': None, 'path': None, 'matched': None, 'total': total,
            'missing': None, 'expected': baseline_expected(data),
            'expected_name': expected_baseline_name(data), 'attached_project': None, 'mismatch': None}
    if src == 'embedded':
        # its name travels with the result so every export and the screen print ONE label (R2 F8)
        info['embedded_name'] = ((getattr(data, 'project', None) or {}).get('baseline_name') or '').strip() or None
        data.baseline_info = info
        return info
    if attached_path:
        if not os.path.isfile(attached_path):
            info['missing'] = display_name(attached_path)   # e.g. evicted from the XML cache
        else:
            if parse is None:
                from p6_evm.parser import parse_file as parse
            keep = (data.baseline_by_id, data.baseline_bac_by_activity,
                    getattr(data, 'baseline_bac_by_code', {}))
            bl_data = parse(attached_path)
            rep = apply_baseline(data, bl_data)
            if rep['matched']:
                data.baseline_source = 'attached'
                # is it the baseline P6 names for this update? (an earlier / later revision of the
                # same project shares most Activity IDs, so the match count alone can't tell)
                bproj = getattr(bl_data, 'project', None) or {}
                other = baseline_mismatch(info['expected_name'],
                                          (getattr(data, 'project', None) or {}).get('baseline_object_id'),
                                          bproj)
                info.update(source='attached', name=display_name(attached_path),
                            path=attached_path, matched=rep['matched'],
                            attached_project=(bproj.get('name') or bproj.get('id') or None),
                            mismatch=bool(other))
            else:                                     # wrong file — keep the file's own baseline
                data.baseline_by_id, data.baseline_bac_by_activity, data.baseline_bac_by_code = keep
                info.update(matched=0, name=display_name(attached_path))
    data.baseline_info = info
    return info


def inherit_baseline(prev, curr):
    """Measure an earlier update (``prev``) against the current update's baseline when it has
    none of its own — the SAME baseline whether ``curr`` carries it inside the XML ('embedded')
    or it was attached to ``curr`` as a separate XER / XML ('attached'), so Update vs Update,
    the Critical Path Analyzer's previous role and Reporting Studio give one answer for an XML
    update and for the same update as XER + attached baseline (R4).

    Only when ``prev`` resolved to 'self' (no embedded baseline, none attached for it). Linked
    by Activity Id exactly like ``apply_baseline``: baseline planned dates for every baseline
    activity, baseline budget onto ``prev``'s activities by code. A baseline that matches none
    of ``prev``'s activities (another project) is not applied. Mutates ``prev``; returns its
    baseline info (also stored on ``prev.baseline_info``)."""
    info = getattr(prev, 'baseline_info', None)
    if getattr(prev, 'baseline_source', None) != 'self' or curr is None:
        return info
    csrc = getattr(curr, 'baseline_source', None)
    if csrc not in ('embedded', 'attached') or not getattr(curr, 'baseline_by_id', None):
        return info
    bl_dates = curr.baseline_by_id
    matched = sum(1 for a in (prev.activities or {}).values() if a.get('id') in bl_dates)
    if not matched:
        return info
    by_code = getattr(curr, 'baseline_bac_by_code', None)
    if by_code is None:                                  # older ScheduleData: rebuild from oids
        by_code = {}
        for oid, cost in (curr.baseline_bac_by_activity or {}).items():
            aid = (curr.activities.get(oid) or {}).get('id')
            if aid:
                by_code[aid] = cost
    prev.baseline_by_id = {k: dict(v) for k, v in bl_dates.items()}
    prev.baseline_bac_by_code = dict(by_code)
    prev.baseline_bac_by_activity = {oid: by_code[a['id']] for oid, a in (prev.activities or {}).items()
                                     if a.get('id') in by_code}
    prev.baseline_source = 'attached'
    cinfo = getattr(curr, 'baseline_info', None) or {}
    if csrc == 'attached':
        name, path = cinfo.get('name'), cinfo.get('path')
    else:
        name = (getattr(curr, 'project', None) or {}).get('baseline_name') or 'baseline'
        name, path = f'{name} (inside the current update)', None
    info = {'source': 'attached', 'name': name, 'path': path, 'matched': matched,
            'total': len(prev.activities or {}), 'missing': None, 'from_current': True,
            'expected': baseline_expected(prev), 'expected_name': expected_baseline_name(prev),
            'attached_project': cinfo.get('attached_project'), 'mismatch': cinfo.get('mismatch')}
    prev.baseline_info = info
    return info


def load_schedule(path, attached_path=None):
    """parse_file(path) + resolve_baseline — the schedule every feature should read."""
    from p6_evm.parser import parse_file
    data = parse_file(path)
    resolve_baseline(data, attached_path, parse_file)
    return data


def attached_baseline_for(path=None, snapshot_id=None, cached_path=None):
    """The baseline file attached for this snapshot (by id), else for the latest snapshot of
    this file (by its cached / original path). None when nothing is attached or no DB."""
    try:
        import db
        return db.get_attached_baseline(snapshot_id=snapshot_id, paths=(cached_path, path))
    except Exception:
        return None


def load_for_project(path, snapshot_id=None, cached_path=None, baseline_path=None):
    """load_schedule with the attached baseline looked up for the snapshot / file.
    ``baseline_path`` (an explicit attached baseline) wins over the lookup."""
    attached = baseline_path or attached_baseline_for(path, snapshot_id, cached_path)
    return load_schedule(path, attached)


def baseline_label(fields, embedded_name=None):
    """ONE line naming the baseline the numbers were measured against — printed in every
    report head and Excel header block (the counterpart of the screen's baseline banner), so
    the baseline is labelled, never silent. ``fields`` has the baseline_fields() keys (a result
    dict works too). None when nothing is known (older results). The embedded baseline's name
    comes from ``embedded_name`` or, failing that, the fields' ``baseline_embedded_name``."""
    f = fields or {}
    src = f.get('baseline_source')
    if src == 'embedded':
        embedded_name = embedded_name or f.get('baseline_embedded_name')
        return f'inside the schedule file ({embedded_name})' if embedded_name else 'inside the schedule file'
    if src == 'attached':
        m, t = f.get('baseline_matched'), f.get('baseline_total')
        cnt = f' ({m}/{t} activities matched)' if m is not None and t else ''
        warn = ''
        if f.get('baseline_mismatch') and f.get('baseline_expected_name'):
            warn = (f" — not the baseline P6 names (“{f.get('baseline_expected_name')}”); "
                    f"this file is “{f.get('baseline_attached_project') or 'another project'}”")
        elif m is not None and t and m < t:
            warn = f' — {t - m} activities are not in it (no baseline; left out of Planned %)'
        return f"attached: {f.get('baseline_name') or 'baseline file'}{cnt}{warn}"
    if src == 'self':
        if f.get('baseline_expected') is False:
            return "none assigned in P6 — the schedule's own Planned dates are its baseline"
        miss = f.get('baseline_missing')
        lost = f' (the attached {miss} is no longer available)' if miss else ''
        return ("not in the file and none attached — the update's own Planned dates stand in "
                "(approximate)" + lost)
    return None


def baseline_approx(fields):
    """True when Planned Value / SPI / Delay / Baseline Finish come from the file's own dates
    standing in for a baseline P6 names but the file does not carry (marked 'approx')."""
    f = fields or {}
    return f.get('baseline_source') == 'self' and f.get('baseline_expected') is not False


def baseline_fields(info):
    """The result-JSON keys the UI reads (EVM banner, Update Analysis, Help).
    ``baseline_expected`` False = no baseline is assigned to this project in P6, so its own
    Planned dates are the baseline ('self' is then exact: no prompt, no 'approx')."""
    info = info or {}
    attached = info.get('source') == 'attached'
    return {
        'baseline_source': info.get('source'),
        # the name of the baseline inside the file (XML <BaselineProject><Name> / the XER's
        # baseline PROJECT row) — so the Excel header, the PDF head and the EVM screen name it
        # the same way (R2 F8)
        'baseline_embedded_name': info.get('embedded_name') if info.get('source') == 'embedded' else None,
        'baseline_expected': info.get('expected'),
        'baseline_name': info.get('name') if attached else None,
        'baseline_path': info.get('path') if attached else None,
        'baseline_matched': info.get('matched') if attached else None,
        'baseline_total': info.get('total') if attached else None,
        'baseline_missing': info.get('missing'),
        # the baseline P6 names for this update (XER BASELINE_EXPORT / XML <BaselineProject>) —
        # so the prompt / banner / Update Analysis can say WHICH project to export (R4 F4)
        'baseline_expected_name': info.get('expected_name'),
        'baseline_attached_project': info.get('attached_project') if attached else None,
        'baseline_mismatch': bool(info.get('mismatch')) if attached else None,
    }


def schedule_baseline(data):
    """{'baseline_approx', 'baseline_label'} for a parsed schedule — what every feature puts in
    its result / report so the screen marks baseline-derived values '· approx' and prints the
    one 'Baseline: …' line (R2: screen == PDF == Excel). Reads ``data.baseline_info`` (set by
    resolve_baseline / inherit_baseline), else infers it from the parsed file."""
    if data is None:
        return {'baseline_approx': False, 'baseline_label': None}
    info = getattr(data, 'baseline_info', None)
    if not info:
        src = getattr(data, 'baseline_source', None) or (
            'embedded' if getattr(data, 'baseline_by_id', None) else 'self')
        info = {'source': src, 'expected': baseline_expected(data),
                'expected_name': expected_baseline_name(data),
                'embedded_name': (getattr(data, 'project', None) or {}).get('baseline_name'),
                'total': len(getattr(data, 'activities', None) or {})}
    f = baseline_fields(info)
    return {'baseline_approx': baseline_approx(f),
            'baseline_label': baseline_label(f, (getattr(data, 'project', None) or {}).get('baseline_name'))}
