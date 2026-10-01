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


# ── Owner comment 37: the settings (project type / country / methodology) change the rate ──

RC = "civil.structural.concrete.rc_column"


def _q(factors=None, **ctx):
    c = {"Project type": "Industrial", "Location": "KSA", "Methodology": "Jump-form"}
    c.update(ctx)
    if factors is not None:
        c["factors"] = factors
    return engine.query(RC, context=c, quantity=100)


def test_no_factor_means_the_library_norm_and_says_so():
    base = engine.query(RC, context={}, quantity=100)
    r = _q()
    assert r["context_net"] == 1.0
    assert r["rollup"]["total_mh"] == base["rollup"]["total_mh"]
    ledger = {row["factor"]: row for row in r["context_ledger"]}
    for dim in ("Project type", "Location", "Methodology"):       # every screen setting is in the ledger
        assert ledger[dim]["applied"] is False and ledger[dim]["source"] == "none"
        assert "insufficient evidence" in ledger[dim]["evidence"]
    assert all(c["rate"]["adjusted"] is False for c in r["components"] if c.get("rate"))


def test_each_setting_factor_changes_rate_manhours_and_duration():
    base = _q()
    fw0 = {c["component_id"]: c for c in base["components"]}["formwork"]
    for dim in ("Project type", "Location", "Methodology"):
        r = _q({dim: 1.25})
        fw = {c["component_id"]: c for c in r["components"]}["formwork"]
        assert r["context_net"] == 1.25, dim
        assert fw["rate"]["adjusted"] is True and fw["rate"]["factor"] == 1.25
        assert fw["rate"]["output_per_day"] == round(fw0["rate"]["output_per_day"] / 1.25, 2)     # slower crew
        assert fw["rate"]["mh_per_unit"] == round(fw0["rate"]["mh_per_unit"] * 1.25, 2)
        assert fw["rate"]["output_per_day_base"] == fw0["rate"]["output_per_day"]                # the norm is kept
        assert fw["man_hours"] == round(fw0["man_hours"] * 1.25)
        assert fw["duration_days"] == round(fw0["duration_days"] * 1.25, 1)                      # duration follows
        assert r["rollup"]["total_mh"] > base["rollup"]["total_mh"]
        row = {x["factor"]: x for x in r["context_ledger"]}[dim]
        assert row["applied"] is True and row["source"] == "user" and "entered by you" in row["evidence"]


def test_factors_multiply_together_and_a_faster_factor_shortens():
    r = _q({"Location": 1.25, "Methodology": 0.8})
    assert r["context_net"] == 1.0                               # 1.25 x 0.8
    fast = _q({"Methodology": 0.8})
    assert fast["rollup"]["duration_days"] < _q()["rollup"]["duration_days"]
    assert fast["rollup"]["total_mh"] < _q()["rollup"]["total_mh"]


def test_a_bad_factor_is_ignored_and_reported_never_applied():
    for bad in (9, 0.05, "abc", -1):
        r = _q({"Location": bad})
        row = {x["factor"]: x for x in r["context_ledger"]}["Location"]
        assert r["context_net"] == 1.0 and row["applied"] is False, bad
        assert "ignored" in row["evidence"], bad
    assert _q({"Location": ""})["context_net"] == 1.0
    assert _q({"Location": 1})["context_net"] == 1.0


def test_project_type_applicability_is_reported():
    items = kb.load_items()
    it = next(i for i in items if "Residential" not in (i.get("project_types") or []) and i.get("project_types"))
    assert engine.item_result(it, context={"Project type": "Residential"})["project_type_applies"] is False
    ok = it["project_types"][0]
    assert engine.item_result(it, context={"Project type": ok})["project_type_applies"] is True
    assert engine.item_result(it, context={})["project_type_applies"] is None


def test_shipped_library_still_carries_no_factor_of_its_own():
    """The tool never supplies a multiplier: a factor is the planner's, or evidence in the item."""
    for it in kb.load_items():
        for dim, choices in (it.get("context_factors") or {}).items():
            for choice, entry in (choices or {}).items():
                assert entry.get("evidence"), (it["item_id"], dim, choice)


def test_excel_summary_lists_the_factors():
    import server
    r = _q({"Location": 1.15, "Methodology": 0.9})
    sheets = server._prodintel_excel_sections(r)
    summary = dict((row[0], row[1]) for row in sheets[0][2]) if isinstance(sheets[0], tuple) else \
        dict((row[0], row[1]) for row in sheets[0]["blocks"][0]["rows"])
    assert summary["Factor · Location (KSA)"].startswith("x1.15")
    assert summary["Factor · Methodology (Jump-form)"].startswith("x0.9")
    assert "insufficient evidence" in summary["Factor · Project type (Industrial)"]
    assert summary["All factors together"].startswith("x1.035")
