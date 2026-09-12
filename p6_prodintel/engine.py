"""Deterministic compute for Productivity Intelligence.

``query(item_id, context, quantity)`` returns everything the result dashboard shows:
per-component productivity norms, separated labour / equipment / material, and — only when a
quantity is supplied — man-hours, crew and an indicative duration, rolled up to the work item
with the controlling (bottleneck) component named.

Design rules baked in here (never bypassed):
- No quantity  -> pure knowledge (norms, ranges, resources); no man-hours / duration.
- No evidence  -> the component reports ``state == "no_reference"`` and carries no number; the
  roll-up is flagged ``basis_incomplete`` rather than inventing one.
- Percentiles   -> only when a component has >= PERCENTILE_MIN_RECORDS validated records.
- Context factor without evidence -> "not adjusted — insufficient evidence" (x1.0).
- Overall confidence is the weakest link across the priced components.
"""
from .kb import by_id, load_items

PERCENTILE_MIN_RECORDS = 5
DEFAULT_SHIFT_HOURS = 8.0

# context dimensions surfaced in the adjustment ledger, in display order
CONTEXT_DIMENSIONS = ["Location", "Access", "Congestion", "Shift / environment", "Methodology"]


def _round(x, n=1):
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return None


def _gang_persons(comp):
    return sum(int(g.get("count", 0)) for g in comp.get("gang", []) or [])


def _component_state(comp):
    if not comp.get("rate"):
        return "no_reference"
    prov = comp.get("provenance") or {}
    st = (prov.get("source_type") or "").lower()
    conf = (prov.get("confidence") or "").lower()
    if "validated" in st or conf == "high":
        return "validated"
    return "draft"


def _component_confidence(comp):
    prov = comp.get("provenance") or {}
    conf = (prov.get("confidence") or "").lower()
    if not comp.get("rate"):
        return "none"
    if conf in ("high", "moderate", "draft", "low"):
        return "moderate" if conf == "low" else conf
    return "draft"


def _percentile_supported(comp):
    prov = comp.get("provenance") or {}
    records = int(prov.get("records") or 0)
    return _component_state(comp) == "validated" and records >= PERCENTILE_MIN_RECORDS


def _context_ledger(item, context):
    """One row per context dimension. Applied only where the item carries evidence for it;
    otherwise an honest 'not adjusted — insufficient evidence' pass-through (x1.0)."""
    factors = item.get("context_factors") or {}
    ctx = context or {}
    ledger = []
    net = 1.0
    for dim in CONTEXT_DIMENSIONS:
        chosen = ctx.get(dim)
        entry = None
        dimdata = factors.get(dim) or {}
        if chosen and isinstance(dimdata, dict):
            entry = dimdata.get(chosen)
        if entry and isinstance(entry, dict) and entry.get("multiplier") and entry.get("evidence"):
            mult = float(entry["multiplier"])
            net *= mult
            ledger.append({"factor": dim, "choice": chosen, "applied": True,
                           "multiplier": mult, "evidence": entry.get("evidence")})
        else:
            ledger.append({"factor": dim, "choice": chosen, "applied": False,
                           "multiplier": 1.0, "evidence": "not adjusted — insufficient evidence"})
    return ledger, net


def _worst_confidence(levels):
    order = ["none", "draft", "moderate", "high"]
    priced = [l for l in levels if l != "none"]
    if not priced:
        return "none"
    return min(priced, key=lambda l: order.index(l) if l in order else 0)


def item_result(item, context=None, quantity=None, component_quantities=None):
    """Compute the full result dict for one KB item.

    quantity seeds each component from the item's primary unit (via qty_per_primary);
    component_quantities {component_id: qty} lets the planner enter each component's own
    quantity in its own unit (e.g. reinforcement in tonnes) and overrides the derived value.
    """
    context = context or {}
    shift = float(context.get("shift_hours") or DEFAULT_SHIFT_HOURS)
    ledger, ctx_net = _context_ledger(item, context)
    has_primary = quantity is not None and quantity != "" and float(quantity) > 0
    qty = float(quantity) if has_primary else None
    cq_over = component_quantities or {}
    any_qty = False

    comps_out = []
    for comp in item.get("components", []):
        state = _component_state(comp)
        rate = comp.get("rate") or None
        gp = _gang_persons(comp)
        row = {
            "component_id": comp.get("component_id"),
            "name": comp.get("name"),
            "unit": comp.get("unit"),
            "state": state,
            "gang": comp.get("gang", []),
            "gang_persons": gp,
            "equipment": comp.get("equipment", []),
            "material": comp.get("material", []),
            "provenance": comp.get("provenance", {}),
            "confidence": _component_confidence(comp),
            "percentile_supported": _percentile_supported(comp),
            "controls": False,
        }
        if rate:
            adj = float(rate.get("mh_per_unit")) * ctx_net if rate.get("mh_per_unit") is not None else None
            row["rate"] = {
                "mh_per_unit": rate.get("mh_per_unit"),
                "mh_per_unit_adjusted": _round(adj, 2) if adj is not None else None,
                "low": rate.get("low"),
                "likely": rate.get("likely", rate.get("mh_per_unit")),
                "high": rate.get("high"),
                "output_per_day": rate.get("output_per_day"),
                "output_unit": rate.get("output_unit"),
            }
            ov = cq_over.get(comp.get("component_id"))
            try:
                ov = float(ov) if ov not in (None, "") else None
            except (TypeError, ValueError):
                ov = None
            cqty = ov if (ov is not None and ov > 0) else (qty * float(comp.get("qty_per_primary", 1.0)) if has_primary else None)
            if cqty is not None:
                any_qty = True
                mhu = adj if adj is not None else float(rate["mh_per_unit"])
                n_gangs = max(1, int(comp.get("default_gangs", 1) or 1))
                mh = cqty * mhu
                out_day = rate.get("output_per_day")
                if out_day:
                    dur = cqty / (float(out_day) * n_gangs)
                elif gp:
                    dur = mh / (gp * n_gangs * shift)
                else:
                    dur = None
                row["component_qty"] = _round(cqty, 2)
                row["man_hours"] = _round(mh, 0)
                row["man_hours_low"] = _round(cqty * float(rate["low"]) * ctx_net, 0) if rate.get("low") else None
                row["man_hours_high"] = _round(cqty * float(rate["high"]) * ctx_net, 0) if rate.get("high") else None
                row["n_gangs"] = n_gangs
                row["duration_days"] = _round(dur, 1) if dur is not None else None
        else:
            row["rate"] = None
        comps_out.append(row)

    result = {
        "item_id": item.get("item_id"),
        "item": item.get("item"),
        "discipline": item.get("discipline"),
        "work_type": item.get("work_type"),
        "system": item.get("system"),
        "primary_unit": item.get("primary_unit"),
        "project_types": item.get("project_types", []),
        "aliases": item.get("aliases", []),
        "context": {**context, "shift_hours": shift},
        "context_ledger": ledger,
        "has_quantity": any_qty,
        "quantity": qty,
        "components": comps_out,
        "overall_confidence": _worst_confidence([c["confidence"] for c in comps_out]),
        "basis_incomplete": any(c["state"] == "no_reference" for c in comps_out),
        "evidence": _item_evidence(comps_out),
        "notes": item.get("notes"),
        "why": item.get("why"),
        "assumptions": item.get("assumptions", []),
        "exclusions": item.get("exclusions", []),
    }

    if any_qty:
        priced = [c for c in comps_out if c.get("man_hours") is not None]
        total_mh = sum(c["man_hours"] for c in priced)
        durs = [(c, c.get("duration_days")) for c in priced if c.get("duration_days") is not None]
        controlling = max(durs, key=lambda cd: cd[1])[0] if durs else None
        if controlling:
            controlling["controls"] = True
        peak = {}
        for c in priced:
            n = c.get("n_gangs", 1)
            for g in c.get("gang", []):
                peak[g.get("trade")] = peak.get(g.get("trade"), 0) + int(g.get("count", 0)) * n
        result["rollup"] = {
            "total_mh": _round(total_mh, 0),
            "total_mh_low": _round(sum(c.get("man_hours_low") or c["man_hours"] for c in priced), 0),
            "total_mh_high": _round(sum(c.get("man_hours_high") or c["man_hours"] for c in priced), 0),
            "blended_mh_per_primary": _round(total_mh / qty, 1) if qty else None,
            "primary_unit": item.get("primary_unit"),
            "controlling_component": controlling["name"] if controlling else None,
            "duration_days": max((d for _, d in durs), default=None),          # bottleneck / line-of-balance
            "duration_days_sequential": _round(sum(d for _, d in durs), 1) if durs else None,
            "peak_crew_by_trade": peak,
            "peak_persons": sum(peak.values()),
        }
    else:
        result["rollup"] = None
    return result


def _item_evidence(comps_out):
    """Item-level evidence summary drawn from the strongest priced component."""
    best = None
    for c in comps_out:
        if c["state"] == "no_reference":
            continue
        prov = c.get("provenance") or {}
        rec = int(prov.get("records") or 0)
        if best is None or rec > best[0]:
            best = (rec, prov)
    if not best:
        return {"records": 0, "source_type": "No reference", "period": "", "projects": [], "confidence": "none"}
    prov = best[1]
    return {
        "records": int(prov.get("records") or 0),
        "source_type": prov.get("source_type") or "Internal reference",
        "period": prov.get("period") or "",
        "projects": prov.get("projects") or [],
        "confidence": (prov.get("confidence") or "draft"),
    }


def query(item_id, context=None, quantity=None, items=None, component_quantities=None):
    """Look up an item by id and compute its result. Unknown id -> honest no-reference."""
    index = by_id(items if items is not None else load_items())
    item = index.get(item_id)
    if not item:
        return {"item_id": item_id, "found": False, "state": "no_reference",
                "message": "No validated reference available."}
    res = item_result(item, context=context, quantity=quantity, component_quantities=component_quantities)
    res["found"] = True
    return res
