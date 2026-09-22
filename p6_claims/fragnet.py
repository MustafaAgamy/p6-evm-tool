"""Insert a named delay-event 'fragnet' into a P6 XML for Time Impact Analysis.

The delay is modelled as a new, named activity of N working days that DRIVES the
impacted activity's start: a Finish-to-Start predecessor anchored (Start On or
After) to when the impacted activity was originally due to start. Open the result
in P6 and press F9 — the movement of the finish milestone IS the impact.

Only the XML is edited; the tool never computes a date. Costs, actuals, and every
other activity are left untouched. Handles both namespaced (real P6 exports) and
namespace-free XML, and preserves the default namespace on output (no ``ns0:``
prefixes that would break a P6 import).
"""
import re
import xml.etree.ElementTree as ET

CONSTRAINT_START_NO_EARLIER = 'Start On or After'
XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'


def _detect_ns(xml_text):
    m = re.search(r'xmlns="([^"]+)"', xml_text[:4000])
    return m.group(1) if m else ''


def _sub(parent, tag, text=None):
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def insert_start_delay(xml_text, activity_id, delay_days, *, label=None,
                       day_hours=8.0, delay_oid=None, delay_id=None):
    """Return the impacted XML (plus the delay activity's identifiers).

    Args:
        xml_text: the base programme XML (the update as it stood at the event).
        activity_id: the impacted activity's P6 Id (code), e.g. ``'MEP-L2-001'``.
        delay_days: the delay length in working days.
        label: the delay activity's name; defaults to a generated one.
        day_hours: hours-per-day of the impacted activity's calendar (for duration).

    Returns:
        ``{'xml', 'delay_oid', 'delay_id', 'delay_name', 'duration_hours'}``.

    Raises:
        KeyError: the activity Id is not in the schedule.
        ValueError: no ``<Project>`` element.
    """
    ns_uri = _detect_ns(xml_text)
    if ns_uri:
        ET.register_namespace('', ns_uri)
    ns = f'{{{ns_uri}}}' if ns_uri else ''

    def t(name):
        return f'{ns}{name}'

    def child_text(el, name):
        c = el.find(t(name))
        return c.text if c is not None else None

    root = ET.fromstring(xml_text)
    project = root.find(t('Project'))
    if project is None:
        raise ValueError('No <Project> element found in the schedule XML.')

    target = None
    existing_oids, existing_ids = set(), set()
    for act in project.findall(t('Activity')):
        oid, aid = child_text(act, 'ObjectId'), child_text(act, 'Id')
        if oid:
            existing_oids.add(oid)
        if aid:
            existing_ids.add(aid)
        if aid == activity_id:
            target = act
    if target is None:
        raise KeyError(f'Activity {activity_id!r} not found in the schedule.')

    target_oid = child_text(target, 'ObjectId')
    target_cal = child_text(target, 'CalendarObjectId')
    target_wbs = child_text(target, 'WBSObjectId')
    target_start = child_text(target, 'PlannedStartDate')

    d_oid = delay_oid or f'DLY-{target_oid}'
    n = 1
    while d_oid in existing_oids:
        d_oid, n = f'DLY-{target_oid}-{n}', n + 1
    d_id = delay_id or f'DELAY-{activity_id}'
    n = 1
    while d_id in existing_ids:
        d_id, n = f'DELAY-{activity_id}-{n}', n + 1

    dur_hours = round(float(delay_days) * float(day_hours or 8.0), 4)
    name = label or f'Delay event — {activity_id} (+{delay_days} wd)'

    delay = ET.SubElement(project, t('Activity'))
    _sub(delay, t('ObjectId'), d_oid)
    _sub(delay, t('Id'), d_id)
    _sub(delay, t('Name'), name)
    _sub(delay, t('Status'), 'Not Started')
    _sub(delay, t('Type'), 'Task Dependent')
    if target_cal:
        _sub(delay, t('CalendarObjectId'), target_cal)
    if target_wbs:
        _sub(delay, t('WBSObjectId'), target_wbs)
    _sub(delay, t('PercentComplete'), '0')
    _sub(delay, t('PlannedDuration'), dur_hours)
    _sub(delay, t('RemainingDuration'), dur_hours)
    # Anchor the delay to when the impacted activity was due to start, so F9 places
    # it there and its finish (+N) drives the impacted activity's start forward.
    if target_start:
        _sub(delay, t('PrimaryConstraintType'), CONSTRAINT_START_NO_EARLIER)
        _sub(delay, t('PrimaryConstraintDate'), target_start)
        _sub(delay, t('PlannedStartDate'), target_start)

    rel = ET.SubElement(project, t('Relationship'))
    _sub(rel, t('PredecessorActivityObjectId'), d_oid)
    _sub(rel, t('SuccessorActivityObjectId'), target_oid)
    _sub(rel, t('Type'), 'Finish to Start')
    _sub(rel, t('Lag'), '0')

    body = ET.tostring(root, encoding='unicode')
    return {
        'xml': XML_DECLARATION + body,
        'delay_oid': d_oid,
        'delay_id': d_id,
        'delay_name': name,
        'duration_hours': dur_hours,
    }
