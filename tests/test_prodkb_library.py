"""KB Doctor — every template in the Productivity KB is well-formed, unique, and computes
with full rate traceability. Guards the growing library against malformed entries."""
import os

from p6_prodkb import compute, kb
from p6_prodkb.calc import DRIVERS

BASE = os.path.join(os.path.dirname(__file__), "..", "productivity_kb")


def _tmpls():
    return kb.load_templates(bundled=BASE, overlay=[])


def test_library_loads_and_ids_unique():
    ts = _tmpls()
    assert len(ts) >= 60
    ids = [t["template_id"] for t in ts]
    assert len(ids) == len(set(ids)), "duplicate template_id in the KB"


def test_every_template_wellformed_and_computes():
    for t in _tmpls():
        tid = t.get("template_id")
        assert tid, "template missing id"
        assert t.get("discipline") and t.get("work_type") and t.get("unit"), tid
        assert t.get("driver") in DRIVERS, f"{tid}: bad driver {t.get('driver')}"
        res = compute(t, 100)                       # a nominal quantity must never error
        r = res["rate"]
        assert r.get("source") and r.get("basis") and r.get("conditions") and r.get("confidence"), tid
        if res["driver"] in ("production_rate", "resource_driven", "manpower_driven"):
            assert res["duration_days"] is not None or res["needs_qty"], tid
        if res["driver"] == "lead_time":
            assert res["duration_days"] and res["labor"]["mnp"] is None, tid


def test_multi_rate_entries_are_context_keyed():
    for t in _tmpls():
        for r in (t.get("rates") or []):
            assert "context" in r, f"{t['template_id']}: a rates[] entry has no context"
