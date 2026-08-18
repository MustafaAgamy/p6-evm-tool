"""Rule-based activity -> template matching (offline, no AI).

Given an imported activity (name, wbs_path, code) and the project context, score each
template's match keywords and return ranked candidates with a confidence band. Never
invents a rate; a weak match is flagged for the planner. Mirrors the spirit of
``p6_kb.detect.score_entries`` — a length-normalised keyword vote — one level down, at
the activity row.
"""
import math
import re

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text):
    return set(_WORD.findall((text or "").lower()))


def _template_terms(t):
    terms = set()
    for kw in (t.get("match") or {}).get("keywords", []):
        terms |= _tokens(kw)
    for extra in (t.get("work_type"), t.get("method"), t.get("name")):
        terms |= _tokens(extra)
    return terms


def score_templates(activity, templates):
    """Return [(template, score, phrase_hits)] best-first."""
    name = (activity.get("name") or "")
    text = _tokens(name) | _tokens(activity.get("wbs_path"))
    lname = name.lower()
    scored = []
    for t in templates:
        m = t.get("match") or {}
        phrase = sum(1 for kw in m.get("keywords", []) if kw.lower() in lname)
        neg = sum(1 for kw in m.get("negative_keywords", []) if kw.lower() in lname)
        terms = _template_terms(t)
        raw = 3 * phrase + len(text & terms) - 2 * neg
        score = raw / ((len(terms) ** 0.5) or 1)
        scored.append((t, score, phrase))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _band(conf):
    if conf >= 0.75:
        return "confirmed"
    if conf >= 0.5:
        return "review"
    if conf >= 0.3:
        return "low"
    return "needs_planner"


def match(activity, templates):
    """Resolve one activity to its best template + a confidence band."""
    scored = score_templates(activity, templates)
    if not scored or scored[0][1] <= 0:
        return {"template": None, "confidence": 0.0, "band": "needs_planner",
                "margin": 0.0, "candidates": []}
    best, s1, phrase = scored[0]
    s2 = scored[1][1] if len(scored) > 1 else 0.0
    margin = s1 - s2
    conf = 1.0 / (1.0 + math.exp(-(s1 - 1.0)))
    if phrase == 0:
        conf *= 0.8               # no full-phrase hit -> less certain
    if margin < 0.25:
        conf = min(conf, 0.55)    # ambiguous -> cap at review
    return {
        "template": best,
        "confidence": round(conf, 2),
        "band": _band(conf),
        "margin": round(margin, 2),
        "candidates": [{"template_id": t["template_id"], "score": round(sc, 2)}
                       for t, sc, _ in scored[:3]],
    }


def resolve(activity, quantity=None, project_type=None, templates=None,
            calendar_hours=None):
    """Full pipeline for one activity: match -> context -> compute the chain."""
    from p6_prodkb.calc import compute
    from p6_prodkb.kb import load_templates
    templates = templates if templates is not None else load_templates()
    m = match(activity, templates)
    # Two DISTINCT statuses, never conflated:
    #   knowledge_not_available -> the KB has no pattern for this activity/type/method
    #   needs_input             -> a template matched, but a required input (quantity) is missing
    if not m["template"] or m["band"] == "needs_planner":
        return {"activity": activity, "match": m, "result": None,
                "status": "knowledge_not_available",
                "status_label": "Knowledge Not Available",
                "status_detail": {
                    "reason": "No applicable productivity model/rate exists in the current KB "
                              "for this activity / work type / method.",
                    "project_type": project_type,
                    "work_type": activity.get("work_type"),
                    "method": activity.get("method"),
                    "missing": "productivity_pattern",
                    "action": "Add or calibrate the required productivity pattern in the KB."}}
    ctx = {}
    if project_type:
        ctx["project_type"] = project_type
    if activity.get("method"):
        ctx["method"] = activity["method"]
    res = compute(m["template"], quantity, context=ctx or None,
                  calendar_hours=calendar_hours)
    res["match_confidence"] = m["confidence"]
    res["match_band"] = m["band"]
    if res.get("needs_qty"):
        status, label = "needs_input", "Needs Planner Input"
        detail = {"reason": "Quantity (and unit) are required to calculate the duration.",
                  "missing": "quantity",
                  "action": "Enter the BOQ quantity and unit for this activity."}
    else:
        status, label, detail = "ok", "Calculated", None
    return {"activity": activity, "match": m, "result": res,
            "status": status, "status_label": label, "status_detail": detail}
