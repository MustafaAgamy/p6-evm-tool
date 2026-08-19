"""Deterministic productivity engine — Quantity -> Duration + typed resources.

Offline, rule-based, no AI. The engine SELECTS a calculation model per activity from
its template's ``driver`` — it never forces one formula on everything:

    production_rate   duration = quantity / (rate * n_crews * factors)
    manpower_driven   duration = total_man_hours / (manpower * calendar_hours)
    resource_driven   duration = quantity / (governing_plant_output)   (MNP = N/A)
    lead_time         duration = sum(procure + fabricate + deliver ...) (no crew)
    typical           a fixed experience duration, or a per-count rate

Man-hours (workload) and MNP (people) are kept distinct. MNP uses the activity's P6
**calendar** working-hours/day, not a universal 8-hour day:

    MNP = man_hours / (duration_days * calendar_hours)
"""
import math

DRIVERS = ("production_rate", "manpower_driven", "resource_driven", "lead_time", "typical")


def _crew_size(crew):
    return sum(int(m.get("count", 0)) for m in (crew or {}).get("composition", []))


def _factor_product(template_factors, overrides):
    f = 1.0
    src = dict(template_factors or {})
    src.update(overrides or {})
    for v in src.values():
        try:
            f *= float(v)
        except (TypeError, ValueError):
            continue
    return max(0.35, min(1.15, f))  # clamp to a sane band


def _normalize_rate(r, template):
    """Traceability block shown in the UI: value/unit/source/basis/conditions/confidence.

    ``conditions`` (applicability) is part of the auditable output — it states when the
    rate is valid, so it is clear why it applies to one context and not another.
    ``draft`` marks it as a starter rate, never a validated industry benchmark.
    """
    r = dict(r or {})
    if r.get("value") is None:
        r["value"] = r.get("likely")
    r.setdefault("unit", template.get("unit"))
    r.setdefault("source", "built_in_kb")
    r.setdefault("confidence", "medium")
    r.setdefault("basis", template.get("name"))
    r["conditions"] = (r.get("conditions") or r.get("valid_for")
                       or "Normal access / standard crew / applicable calendar")
    r["draft"] = (template.get("status", "draft") == "draft")
    return r


def _select_rate(template, context):
    """Pick the rate whose CONTEXT best matches (Project Type + Method + Conditions).

    A template may hold one ``rate`` or a ``rates`` list keyed by context. This is what
    keeps a Villa rate and an Industrial rate for the SAME activity from ever mixing:
    a wrong-context rate scores worse than a neutral GLOBAL one, so the engine only uses
    a rate that fits the activity's project type / method.
    """
    ctx = {k: str(v).lower() for k, v in (context or {}).items() if v}
    rates = template.get("rates")
    if not rates:
        return _normalize_rate(template.get("rate"), template)

    def score(r):
        have = {k: str(v).lower() for k, v in (r.get("context") or {}).items()
                if v and str(v).lower() != "global"}
        s = 0
        for key, want in ctx.items():
            got = have.get(key)
            if got is not None:
                s += 2 if got == want else -3  # wrong context worse than neutral GLOBAL
        return s

    return _normalize_rate(max(rates, key=score), template)


def compute(template, quantity=None, *, context=None, calendar_hours=None, n_crews=None,
            manpower=None, factors=None):
    """Return the full auditable chain for one activity template + quantity.

    ``context`` = {project_type, method, complexity, region, ...} selects the rate so
    the same work type resolves to different, non-mixed rates per project type.
    """
    driver = template.get("driver")
    crew = template.get("crew") or {}
    hpd = float(calendar_hours or crew.get("hours_per_day") or 8)
    ncrew = int(n_crews or crew.get("n_crews") or 1)
    csize = _crew_size(crew)
    F = _factor_product(template.get("factors"), factors)
    rate = _select_rate(template, context)

    out = {
        "template_id": template.get("template_id"),
        "activity_name": template.get("name"),
        "discipline": template.get("discipline"),
        "work_type": template.get("work_type"),
        "method": template.get("method"),
        "driver": driver,
        "unit": template.get("unit"),
        "quantity": quantity,
        "hours_per_day": hpd,
        "n_crews": ncrew,
        "rate": rate,
        "duration_days": None,
        "labor": {"man_hours": None, "mnp": None},
        "equipment": [],
        "material": [],
        "needs_qty": False,
        "notes": [],
        "status": template.get("status", "draft"),
    }

    if driver == "lead_time":
        comp = template.get("lead_time") or {}
        dur = sum(float(comp.get(k, 0)) for k in
                  ("approval_days", "procure_days", "fabricate_days",
                   "deliver_days", "customs_days", "offload_days"))
        out["duration_days"] = int(math.ceil(dur)) if dur else None
        out["notes"].append("Lead-time driven — supply/fabricate/deliver; no crew sets the pace.")

    elif driver == "resource_driven":
        gov = next((p for p in (template.get("plant") or []) if p.get("governing")), None)
        if quantity is None:
            out["needs_qty"] = True
        elif gov:
            outp = float((gov.get("output") or {}).get("likely") or gov.get("output_value") or 0) * F
            daily = float(gov.get("count", 1)) * outp
            if daily > 0:
                out["duration_days"] = int(math.ceil(float(quantity) / daily))
        dur = out["duration_days"]
        if dur and csize:
            out["labor"] = {"man_hours": round(csize * ncrew * dur * hpd), "mnp": None}
        out["notes"].append("Equipment-driven — the governing plant sets the pace; MNP not applicable.")

    elif driver == "manpower_driven":
        mhpu = float(rate.get("mh_per_unit") or rate.get("value") or 0)
        N = int(manpower or (csize * ncrew) or 1)
        if quantity is None:
            out["needs_qty"] = True
        elif mhpu:
            total_mh = mhpu * float(quantity) / F
            dur = int(math.ceil(total_mh / (N * hpd))) if N and hpd else None
            out["duration_days"] = max(dur or 0, 1)
            out["labor"] = {"man_hours": round(total_mh), "mnp": N}

    elif driver in ("production_rate", "typical"):
        val = rate.get("likely") or rate.get("value") or rate.get("per_day")
        if driver == "typical" and val is None:
            dur = rate.get("days") or template.get("typical_days")
            out["duration_days"] = int(math.ceil(float(dur))) if dur else None
        elif quantity is None:
            out["needs_qty"] = True
        elif val:
            daily = float(val) * ncrew * F
            if daily > 0:
                out["duration_days"] = int(math.ceil(float(quantity) / daily))
        dur = out["duration_days"]
        if dur and csize:
            mh = csize * ncrew * dur * hpd
            out["labor"] = {"man_hours": round(mh), "mnp": round(mh / (dur * hpd))}
    else:
        out["notes"].append("Unknown driver '%s'." % driver)

    # ---- typed resources kept distinct: equipment (qty + hours) and material (qty + unit) ----
    dur = out["duration_days"] or 0
    for p in (template.get("plant") or []):
        util = float(p.get("utilization", 1.0))
        out["equipment"].append({
            "name": p.get("name"),
            "quantity": p.get("count", 1),
            "hours": round(float(p.get("count", 1)) * util * dur * hpd) if dur else None,
            "governing": bool(p.get("governing")),
        })
    if quantity is not None:
        for m in (template.get("material") or []):
            qpu = float(m.get("qty_per_unit", 1.0))
            waste = float(m.get("waste_pct", 0)) / 100.0
            out["material"].append({
                "name": m.get("name"), "unit": m.get("unit"),
                "quantity": round(float(quantity) * qpu * (1 + waste), 2),
            })
    out["crew"] = [{"trade": c.get("trade"), "count": int(c.get("count", 0)) * ncrew}
                   for c in (crew.get("composition") or [])]
    return out
