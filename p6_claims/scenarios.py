"""What-if scenario transforms for the AI Copilot's scenario engine.

Each transform edits the P6 XML to model a "what if"; the planner opens the result in P6,
presses F9, and the exact finish/delay movement comes back through `tia.compute_impact`.
The tool never computes a date — the number is always P6's (Decision 003). Handles namespaced
and namespace-free XML and preserves the default namespace (no ``ns0:`` on output).

Kinds:
  delay    — push an activity's start by N working days (via fragnet.insert_start_delay)
  shorten  — crash/accelerate: cut an activity's remaining work by N working days
  six_day  — accelerate the whole project by making Saturday a working day on every calendar
"""
import re
import xml.etree.ElementTree as ET

from p6_claims.fragnet import insert_start_delay

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'
WORKING_DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')


def _detect_ns(xml_text):
    m = re.search(r'xmlns="([^"]+)"', xml_text[:4000])
    return m.group(1) if m else ''


def _load(xml_text):
    ns_uri = _detect_ns(xml_text)
    if ns_uri:
        ET.register_namespace('', ns_uri)
    ns = f'{{{ns_uri}}}' if ns_uri else ''
    root = ET.fromstring(xml_text)

    def tag(name):
        return f'{ns}{name}'
    project = root.find(tag('Project'))
    if project is None:
        raise ValueError('No <Project> element found in the schedule XML.')
    return tag, root, project


def _child_text(el, tag, name):
    c = el.find(tag(name))
    return c.text if c is not None else None


def _find_activity(project, tag, activity_id):
    for act in project.findall(tag('Activity')):
        if _child_text(act, tag, 'Id') == activity_id:
            return act
    return None


def shorten_activity(xml_text, activity_id, days, *, day_hours=8.0, label=None):
    """Cut the activity's remaining work by `days` working days (a crash / acceleration).

    Reduces RemainingDuration (falling back to PlannedDuration), floored at zero. F9 then
    finishes it sooner — the completion usually pulls in (a negative, recovering impact)."""
    tag, root, project = _load(xml_text)
    act = _find_activity(project, tag, activity_id)
    if act is None:
        raise KeyError(f'Activity {activity_id!r} not found in the schedule.')
    cut_hours = float(days) * float(day_hours or 8.0)
    changed = False
    for fld in ('RemainingDuration', 'PlannedDuration'):
        el = act.find(tag(fld))
        if el is not None and el.text:
            try:
                cur = float(el.text)
            except ValueError:
                continue
            el.text = f'{max(0.0, cur - cut_hours):g}'
            changed = True
            if fld == 'RemainingDuration':
                break
    if not changed:
        raise ValueError(f'Activity {activity_id!r} has no duration to shorten.')
    name = _child_text(act, tag, 'Name') or activity_id
    return {'xml': XML_DECLARATION + ET.tostring(root, encoding='unicode'),
            'label': label or f'Shorten {activity_id} by {days} working day(s)',
            'activity_name': name}


def set_six_day_week(xml_text, *, label=None):
    """Make Saturday a working day (same hours as a weekday) on every calendar's work week."""
    tag, root, project = _load(xml_text)
    touched = 0
    for cal in root.iter(tag('Calendar')):
        ww = cal.find(tag('StandardWorkWeek'))
        if ww is None:
            continue
        by_day = {_child_text(d, tag, 'DayOfWeek'): d for d in ww.findall(tag('StandardWorkHours'))}
        # a working day's WorkTime template (first weekday that has WorkTime children)
        template = None
        for wd in WORKING_DAYS:
            d = by_day.get(wd)
            if d is not None and d.find(tag('WorkTime')) is not None:
                template = d
                break
        if template is None:
            continue
        sat = by_day.get('Saturday')
        if sat is None:
            sat = ET.SubElement(ww, tag('StandardWorkHours'))
            dow = ET.SubElement(sat, tag('DayOfWeek'))
            dow.text = 'Saturday'
        else:
            for wt in list(sat.findall(tag('WorkTime'))):
                sat.remove(wt)
        for wt in template.findall(tag('WorkTime')):
            sat.append(_copy(wt, tag))
        touched += 1
    if not touched:
        raise ValueError('No usable weekly calendar found to switch to a 6-day week.')
    return {'xml': XML_DECLARATION + ET.tostring(root, encoding='unicode'),
            'label': label or 'Work 6 days a week (Saturday working)',
            'calendars_changed': touched}


def _copy(el, tag):
    new = ET.Element(el.tag)
    for c in el:
        sub = ET.SubElement(new, c.tag)
        sub.text = c.text
    return new


def build_scenario(xml_text, kind, *, activity_id=None, days=None, day_hours=8.0, label=None):
    """Dispatch to the right transform. Returns {'xml', 'label', ...}."""
    if kind == 'delay':
        out = insert_start_delay(xml_text, activity_id, days, day_hours=day_hours, label=label)
        out['label'] = out.get('delay_name')
        return out
    if kind == 'shorten':
        return shorten_activity(xml_text, activity_id, days, day_hours=day_hours, label=label)
    if kind == 'six_day':
        return set_six_day_week(xml_text, label=label)
    raise ValueError(f'Unknown scenario kind: {kind!r}')
