"""Tests for the Productivity Intelligence engine (p6_prodintel)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from p6_prodintel import kb, engine


def _items():
    return kb.load_items()


def test_kb_loads_and_all_items_valid():
    items = _items()
    assert items, "KB should load at least the bundled items"
    for it in items:
        assert it.get("item_id")
        assert it.get("primary_unit")
        assert it.get("components"), f"{it['item_id']} has no components"
        for c in it["components"]:
            assert c.get("component_id") and c.get("name") and c.get("unit")


def test_every_item_computes():
    """KB-doctor: every item must compute in both lookup and quantity modes without error."""
    for it in _items():
        r_lookup = engine.item_result(it, context={"Project type": "Industrial"})
        assert r_lookup["has_quantity"] is False
        assert r_lookup["rollup"] is None
        r_qty = engine.item_result(it, context={"Project type": "Industrial"}, quantity=100)
        assert r_qty["has_quantity"] is True
        priced = [c for c in r_qty["components"] if c.get("man_hours")]
        if priced:
            assert r_qty["rollup"]["total_mh"] > 0


def test_rc_column_numbers():
    r = engine.query("civil.structural.concrete.rc_column",
                     context={"Project type": "Industrial", "Location": "Egypt"}, quantity=100)
    assert r["found"] is True
    comps = {c["component_id"]: c for c in r["components"]}
    assert comps["formwork"]["component_qty"] == 900
    assert comps["reinforcement"]["component_qty"] == 15
    assert comps["concrete"]["component_qty"] == 100
    assert comps["formwork"]["man_hours"] == 1440
    assert comps["reinforcement"]["man_hours"] == 345
    assert comps["concrete"]["man_hours"] == 72
    assert r["rollup"]["total_mh"] == 1857
    assert r["rollup"]["blended_mh_per_primary"] == 18.6
    assert r["rollup"]["controlling_component"] == "Formwork / carpentry"
    assert comps["formwork"]["controls"] is True


def test_lookup_mode_shows_norm_without_manhours():
    r = engine.query("civil.structural.concrete.rc_column", context={"Project type": "Industrial"})
    assert r["has_quantity"] is False
    for c in r["components"]:
        assert "man_hours" not in c or c.get("man_hours") is None
        if c["rate"]:
            assert c["rate"]["mh_per_unit"] is not None
            assert c["gang_persons"] > 0


def test_never_invent_unknown_item():
    r = engine.query("does.not.exist", quantity=50)
    assert r["found"] is False
    assert r["state"] == "no_reference"
    assert "No validated reference" in r["message"]


def test_context_not_adjusted_without_evidence():
    r = engine.query("civil.structural.concrete.rc_column",
                     context={"Project type": "Industrial", "Congestion": "High"})
    ledger = {row["factor"]: row for row in r["context_ledger"]}
    assert ledger["Congestion"]["applied"] is False
    assert ledger["Congestion"]["multiplier"] == 1.0
    assert "insufficient evidence" in ledger["Congestion"]["evidence"]


def test_shipped_kb_has_no_manufactured_percentiles():
    """Built-in norms carry 0 project records -> percentiles must NOT be shown for any of them
    (honours 'do not manufacture statistical values')."""
    for it in _items():
        r = engine.item_result(it, quantity=100)
        for c in r["components"]:
            assert c["percentile_supported"] is False, f"{it['item_id']}/{c['component_id']}"
            prov = c.get("provenance") or {}
            assert int(prov.get("records") or 0) == 0
            assert (prov.get("source") or "built_in_kb") != "xer_evidence"


def test_percentile_gate_turns_on_with_real_evidence():
    """A component WITH >= threshold validated records is percentile-supported (the gate works)."""
    synthetic = {
        "item_id": "t.item", "primary_unit": "m3", "item": "T", "discipline": "Civil",
        "components": [{
            "component_id": "x", "name": "X", "unit": "m3", "qty_per_primary": 1.0,
            "rate": {"mh_per_unit": 1.0, "low": 0.8, "likely": 1.0, "high": 1.2, "output_per_day": 50},
            "gang": [{"trade": "Worker", "count": 2}],
            "provenance": {"source": "xer_evidence", "source_type": "Validated project evidence",
                            "confidence": "high", "records": 7},
        }],
    }
    r = engine.item_result(synthetic, quantity=100)
    assert r["components"][0]["percentile_supported"] is True
    assert r["components"][0]["state"] == "validated"


def test_overall_confidence_weakest_link():
    r = engine.query("civil.structural.concrete.rc_column", context={}, quantity=100)
    assert r["overall_confidence"] in ("draft", "moderate")


def test_build_tree_shapes():
    tree = kb.build_tree()
    assert isinstance(tree, list) and tree
    disc = tree[0]
    assert "name" in disc and "systems" in disc and disc["count"] >= 1


def test_component_quantity_override():
    """Planner can enter a component's quantity in its own unit; it overrides the derived value."""
    r = engine.query("civil.structural.concrete.rc_column",
                     context={"Project type": "Industrial"},
                     component_quantities={"reinforcement": 20})
    comps = {c["component_id"]: c for c in r["components"]}
    assert r["has_quantity"] is True
    # reinforcement uses the entered 20 t (not derived); 20 t x 23 MH/t = 460 MH
    assert comps["reinforcement"]["component_qty"] == 20
    assert comps["reinforcement"]["man_hours"] == 460
    # a component with no override and no primary quantity stays knowledge-only
    assert comps["formwork"].get("man_hours") is None


def test_primary_quantity_still_derives_all():
    r = engine.query("civil.structural.concrete.rc_column", context={}, quantity=100)
    comps = {c["component_id"]: c for c in r["components"]}
    assert comps["reinforcement"]["component_qty"] == 15   # 100 m3 x 0.15
    assert comps["formwork"]["component_qty"] == 900
