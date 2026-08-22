"""Starter-baseline export — turn a Knowledge Base standard into a P6 XML
schedule skeleton the user can import into Primavera P6 and F9.

This is a *skeleton*, not a finished programme: the standard WBS branches, a
placeholder phase activity per branch, the KB's key/often-missing activities in
their home branch, and the milestones — linked Finish-to-Start in a sensible
order so P6 can schedule it. The planner then fleshes it out. Nothing here is
derived from a real schedule; it is the reference standard rendered as P6 XML.

The output element names mirror ``p6_evm/parser.py`` exactly, so a generated file
round-trips through the tool's own parser (a strong validity check), and uses a
standard Primavera PMXML shape so P6's XML import accepts it as a new project.
"""
import heapq
from collections import defaultdict
from xml.sax.saxutils import escape

NS = "http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects"
DAY_HOURS = 8.0
PHASE_DEFAULT_DAYS = 20

# Object-id ranges kept apart so ids never collide across element kinds.
_CAL_OID = 1
_PROJ_OID = 1000


def _slug(text_in, fallback="PROJ"):
    keep = [c for c in (text_in or "").upper() if c.isalnum()]
    return ("".join(keep)[:12]) or fallback


def _el(tag, value):
    """One leaf element; value is xml-escaped. Empty string → self-closing."""
    if value is None or value == "":
        return f"<{tag}/>"
    return f"<{tag}>{escape(str(value))}</{tag}>"


def _hours(days):
    try:
        return round(float(days) * DAY_HOURS, 2)
    except (TypeError, ValueError):
        return PHASE_DEFAULT_DAYS * DAY_HOURS


def _calendar_xml():
    # A plain 5-day, 8-hour standard calendar (Mon–Fri 08:00–12:00, 13:00–17:00).
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    work = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
    rows = []
    for d in days:
        if d in work:
            rows.append(
                f"<StandardWorkHours><DayOfWeek>{d}</DayOfWeek>"
                f"<WorkTime><Start>08:00:00</Start><Finish>12:00:00</Finish></WorkTime>"
                f"<WorkTime><Start>13:00:00</Start><Finish>17:00:00</Finish></WorkTime>"
                f"</StandardWorkHours>")
        else:
            rows.append(f"<StandardWorkHours><DayOfWeek>{d}</DayOfWeek></StandardWorkHours>")
    return (
        f"<Calendar>{_el('ObjectId', _CAL_OID)}{_el('Name', 'Standard 5-Day Workweek')}"
        f"{_el('Type', 'Global')}{_el('IsDefault', 'true')}{_el('IsPersonal', 'false')}"
        f"{_el('HoursPerDay', 8)}{_el('HoursPerWeek', 40)}"
        f"<StandardWorkWeek>{''.join(rows)}</StandardWorkWeek></Calendar>")


def _plan(entry):
    """Build the ordered activity + relationship plan for one KB entry.

    Returns (wbs_nodes, activities, relationships) as lists of dicts with the
    fields the XML writer needs. Order = branch order; within a branch the phase
    activity then its KB detail activities; milestones last.
    """
    prefix = _slug(entry.get("type"), "STD")
    root_wbs = 2000
    wbs_nodes = [{"oid": root_wbs, "parent": "", "code": "ROOT",
                  "name": entry.get("type", "Project"), "seq": 0}]
    branch_oid = {}
    for i, w in enumerate(entry.get("wbs", []), start=1):
        oid = root_wbs + i
        branch_oid[w["name"]] = oid
        wbs_nodes.append({"oid": oid, "parent": root_wbs, "code": f"WBS{i:02d}",
                          "name": w["name"], "seq": i})

    activities = []
    a_oid = 3000
    a_seq = 0

    def add(name, wbs_oid, days, is_ms=False, note=""):
        nonlocal a_oid, a_seq
        a_oid += 1
        a_seq += 10
        activities.append({
            "oid": a_oid, "id": f"{prefix}{a_seq:04d}", "name": name,
            "wbs": wbs_oid, "days": days, "ms": is_ms, "note": note})

    # KB detail activities grouped by their home branch
    kb_by_branch = {}
    for a in entry.get("activities", []):
        kb_by_branch.setdefault(a.get("wbs", ""), []).append(a)

    for w in entry.get("wbs", []):
        boid = branch_oid[w["name"]]
        add(f"{w['name']} — works", boid, PHASE_DEFAULT_DAYS)
        for a in kb_by_branch.get(w["name"], []):
            add(a.get("name", "Activity"), boid, a.get("duration_days") or 10,
                note=a.get("why", ""))

    # KB activities whose branch didn't match any WBS name → drop under root
    matched = {w["name"] for w in entry.get("wbs", [])}
    for br, acts in kb_by_branch.items():
        if br not in matched:
            for a in acts:
                add(a.get("name", "Activity"), root_wbs, a.get("duration_days") or 10,
                    note=a.get("why", ""))

    last_branch = wbs_nodes[-1]["oid"] if len(wbs_nodes) > 1 else root_wbs
    for m in entry.get("milestones", []):
        add(m, last_branch, 0, is_ms=True)

    # ── Sequence so the starter satisfies the standard's own logic rules ──────
    # Required precedences from logic_rules (a matching "before" activity must
    # drive each matching "after" activity). We topologically order the whole
    # list honouring these, then chain Finish-to-Start in that order and add the
    # explicit before→after links — so a review of the starter finds no illogic.
    def _matches(name, keywords):
        n = (name or "").lower()
        return any(k.lower() in n for k in (keywords or []))

    edges = set()
    for rule in entry.get("logic_rules", []):
        befores = [a for a in activities if _matches(a["name"], rule.get("before_keywords"))]
        afters = [a for a in activities if _matches(a["name"], rule.get("after_keywords"))]
        for A in afters:
            cand = [b for b in befores if b["oid"] != A["oid"]]
            if cand:
                edges.add((cand[-1]["oid"], A["oid"]))

    oids = [a["oid"] for a in activities]
    pos = {o: i for i, o in enumerate(oids)}          # creation order = tie-break
    succ = defaultdict(list)
    indeg = {o: 0 for o in oids}
    clean_edges = set()
    for p, s in edges:
        if p != s and (p, s) not in clean_edges:
            clean_edges.add((p, s))
            succ[p].append(s)
            indeg[s] += 1

    avail = [pos[o] for o in oids if indeg[o] == 0]
    heapq.heapify(avail)
    topo, ind = [], dict(indeg)
    while avail:
        o = oids[heapq.heappop(avail)]
        topo.append(o)
        for s in succ[o]:
            ind[s] -= 1
            if ind[s] == 0:
                heapq.heappush(avail, pos[s])
    if len(topo) != len(oids):        # cyclic rules (shouldn't happen) → stable order
        topo = list(oids)

    rels, seen, r_oid = [], set(), 4000
    def _addrel(p, s):
        nonlocal r_oid
        if p != s and (p, s) not in seen:
            seen.add((p, s))
            r_oid += 1
            rels.append({"oid": r_oid, "pred": p, "succ": s})

    for p, s in zip(topo, topo[1:]):
        _addrel(p, s)
    for p, s in clean_edges:          # explicit logic links (dedup vs the chain)
        _addrel(p, s)

    return wbs_nodes, activities, rels


def build_starter_xml(entry, data_date="2025-01-01T00:00:00", start_date="2025-01-01T08:00:00"):
    """Return the P6 XML text for a starter schedule skeleton of this KB entry."""
    wbs_nodes, activities, rels = _plan(entry)
    proj_name = f"{entry.get('type', 'Project')} — Starter Baseline (nPace KB)"

    wbs_xml = "".join(
        f"<WBS>{_el('ObjectId', w['oid'])}{_el('ProjectObjectId', _PROJ_OID)}"
        f"{_el('ParentObjectId', w['parent'])}{_el('Code', w['code'])}"
        f"{_el('Name', w['name'])}{_el('SequenceNumber', w['seq'])}"
        f"{_el('Status', 'Active')}</WBS>"
        for w in wbs_nodes)

    act_xml = ""
    for a in activities:
        atype = "Finish Milestone" if a["ms"] else "Task Dependent"
        dur = 0 if a["ms"] else _hours(a["days"])
        act_xml += (
            f"<Activity>{_el('ObjectId', a['oid'])}{_el('Id', a['id'])}"
            f"{_el('Name', a['name'])}{_el('ProjectObjectId', _PROJ_OID)}"
            f"{_el('WBSObjectId', a['wbs'])}{_el('CalendarObjectId', _CAL_OID)}"
            f"{_el('Type', atype)}{_el('Status', 'Not Started')}"
            f"{_el('DurationType', 'Fixed Duration and Units')}"
            f"{_el('PercentCompleteType', 'Duration')}{_el('PercentComplete', 0)}"
            f"{_el('PlannedDuration', dur)}{_el('RemainingDuration', dur)}"
            + "</Activity>")

    rel_xml = "".join(
        f"<Relationship>{_el('ObjectId', r['oid'])}{_el('Type', 'Finish to Start')}"
        f"{_el('Lag', 0)}{_el('PredecessorActivityObjectId', r['pred'])}"
        f"{_el('SuccessorActivityObjectId', r['succ'])}"
        f"{_el('PredecessorProjectObjectId', _PROJ_OID)}"
        f"{_el('SuccessorProjectObjectId', _PROJ_OID)}</Relationship>"
        for r in rels)

    project_xml = (
        f"<Project>{_el('ObjectId', _PROJ_OID)}{_el('Id', _slug(entry.get('type')))}"
        f"{_el('Name', proj_name)}{_el('Status', 'Active')}"
        f"{_el('DataDate', data_date)}{_el('PlannedStartDate', start_date)}"
        f"{wbs_xml}{act_xml}{rel_xml}</Project>")

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<APIBusinessObjects xmlns="{NS}">'
        f"{_calendar_xml()}{project_xml}</APIBusinessObjects>")


def write_starter_xml(entry, output_path):
    """Write the starter P6 XML to ``output_path``; return a small summary dict."""
    wbs_nodes, activities, rels = _plan(entry)
    xml = build_starter_xml(entry)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml)
    return {
        "path": output_path,
        "type": entry.get("type", ""),
        "wbs": len(wbs_nodes) - 1,          # exclude the root node
        "activities": len(activities),
        "relationships": len(rels),
    }
