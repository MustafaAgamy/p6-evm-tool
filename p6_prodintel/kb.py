"""Load the Productivity Intelligence knowledge base — bundled defaults + per-user overlay.

Mirrors ``p6_kb.kb`` / the old ``p6_prodkb.kb``: glob the bundled
``productivity_kb/disciplines/**/*.json`` plus an optional overlay under
``%APPDATA%/Controlyx/productivity_kb``; the overlay wins by ``item_id``. Malformed files are
skipped, never fatal. Only ``schema == "productivity_kb.item/2.0"`` (component-based) entries
are loaded here; legacy ``.../1.0`` activity templates are ignored so the two can coexist.
"""
import glob
import json
import os

try:
    from utils import resource_path, app_data_dir
except Exception:  # pragma: no cover - keeps the engine importable in isolation
    def resource_path(rel):
        return rel

    def app_data_dir():
        return ""

SCHEMA = "productivity_kb.item/2.0"


def bundled_dir():
    return resource_path("productivity_kb")


def overlay_dir():
    base = app_data_dir()
    return os.path.join(base, "productivity_kb") if base else ""


def _load_dir(base):
    if not base or not isinstance(base, str) or not os.path.isdir(base):
        return []
    out = []
    pattern = os.path.join(base, "disciplines", "**", "*.json")
    for path in sorted(glob.glob(pattern, recursive=True)):
        try:
            with open(path, encoding="utf-8") as f:
                entry = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(entry, dict) and entry.get("item_id") and entry.get("schema") == SCHEMA:
            out.append(entry)
    return out


def load_items(bundled=None, overlay=None):
    """Return merged component-based KB items (overlay overrides bundled by ``item_id``)."""
    b = _load_dir(bundled if bundled is not None else bundled_dir())
    o = _load_dir(overlay if overlay is not None else overlay_dir())
    by_key, order = {}, []
    for entry in b + o:  # overlay last -> wins
        key = entry.get("item_id")
        if key not in by_key:
            order.append(key)
        by_key[key] = entry
    return [by_key[k] for k in order]


def by_id(items=None):
    return {it["item_id"]: it for it in (items if items is not None else load_items())}


def build_tree(items=None):
    """Nest items as Discipline -> Work type -> System -> Item for the browse view.

    Returns a list of discipline nodes; each item node carries its ``item_id`` and a small
    provenance mix (validated / draft / none across its components) for the tree's mini-bars.
    """
    items = items if items is not None else load_items()
    tree = {}
    for it in items:
        disc = it.get("discipline") or "Other"
        wt = it.get("work_type") or ""
        sysname = it.get("system") or wt or "General"
        d = tree.setdefault(disc, {"name": disc, "count": 0, "systems": {}})
        s = d["systems"].setdefault(sysname, {"name": sysname, "items": []})
        mix = _component_mix(it)
        s["items"].append({
            "item_id": it["item_id"],
            "item": it.get("item") or it["item_id"],
            "work_type": wt,
            "project_types": it.get("project_types") or [],
            "components": [c.get("name") for c in it.get("components", [])],
            "mix": mix,
        })
        d["count"] += 1
    out = []
    for disc in sorted(tree):
        d = tree[disc]
        systems = [d["systems"][s] for s in sorted(d["systems"])]
        out.append({"name": disc, "count": d["count"], "systems": systems})
    return out


def _component_mix(item):
    v = k = n = 0
    for c in item.get("components", []):
        st = (c.get("provenance") or {}).get("source_type", "")
        conf = (c.get("provenance") or {}).get("confidence", "")
        if not c.get("rate"):
            n += 1
        elif "validated" in st.lower() or conf == "high":
            v += 1
        else:
            k += 1
    return {"validated": v, "draft": k, "none": n}
