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
                     context={"Project type": "Commercial"}, quantity=100)
    assert r["found"] is True
    comps = {c["component_id"]: c for c in r["components"]}
    assert comps["formwork"]["component_qty"] == 900
    assert comps["reinforcement"]["component_qty"] == 15
    assert comps["concrete"]["component_qty"] == 100
    # rates from the Egyptian reference: formwork 1.5 m3/day x 9 m2/m3 = 13.5 m2 per crew-day;
    # reinforcement 2.5 m3/day x 0.15 t/m3 = 0.38 t per crew-day
    assert comps["formwork"]["man_hours"] == 1071
    assert comps["reinforcement"]["man_hours"] == 632
    assert comps["concrete"]["man_hours"] == 72
    assert r["rollup"]["total_mh"] == 1775
    assert r["rollup"]["blended_mh_per_primary"] == 17.8
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
                     context={"Project type": "Commercial"},
                     component_quantities={"reinforcement": 20})
    comps = {c["component_id"]: c for c in r["components"]}
    assert r["has_quantity"] is True
    # reinforcement uses the entered 20 t (not derived); 20 t x 42.11 MH/t = 842 MH
    assert comps["reinforcement"]["component_qty"] == 20
    assert comps["reinforcement"]["man_hours"] == 842
    # a component with no override and no primary quantity stays knowledge-only
    assert comps["formwork"].get("man_hours") is None


def test_primary_quantity_still_derives_all():
    r = engine.query("civil.structural.concrete.rc_column", context={}, quantity=100)
    comps = {c["component_id"]: c for c in r["components"]}
    assert comps["reinforcement"]["component_qty"] == 15   # 100 m3 x 0.15
    assert comps["formwork"]["component_qty"] == 900


# ── Owner comments 37 / 61 / 62: the settings change the rate ───────────────────────────
#   61  there is no Location setting (the tool is used in Egypt)
#   62  the Project type changes the rate BY ITSELF: a built-in factor per project type and trade
#   62  Methodology = the estimate used: Optimistic (lowest duration) / Most likely / Pessimistic
#   37  the planner's own Project-type factor replaces the built-in one and is labelled as his

RC = "civil.structural.concrete.rc_column"
PLASTER = "architectural.finishes.plaster.internal_plaster"


def _q(factors=None, item=RC, **ctx):
    c = {"Project type": "Commercial", "Methodology": "Most likely"}
    c.update(ctx)
    if factors is not None:
        c["factors"] = factors
    return engine.query(item, context=c, quantity=100)


def test_there_is_no_location_setting():
    assert "Location" not in engine.CONTEXT_DIMENSIONS
    r = _q()
    assert "Location" not in {row["factor"] for row in r["context_ledger"]}
    js = open("ui/modules/prodintel.js", encoding="utf-8").read()
    assert "pi-loc" not in js and "LOCATIONS" not in js and "['Location']" not in js
    import server
    summary = dict((row[0], row[1]) for row in server._prodintel_excel_sections(r)[0]["blocks"][0]["rows"])
    assert "Location" not in summary


def test_project_type_changes_the_rate_by_itself_per_trade():
    """Plaster is not equally productive on a residential, a commercial and a hospital project -
    and a hospital slows MEP more than it slows concrete."""
    out = {pt: _q(item=PLASTER, **{"Project type": pt}) for pt in ("Residential", "Commercial", "Hospital")}
    rate = lambda r: r["components"][0]["rate"]["output_per_day"]
    assert rate(out["Residential"]) > rate(out["Commercial"]) > rate(out["Hospital"])
    assert out["Commercial"]["context_net"] == 1.0                       # the base = the library norm
    assert out["Hospital"]["rollup"]["total_mh"] > out["Commercial"]["rollup"]["total_mh"]
    assert out["Hospital"]["rollup"]["duration_days"] > out["Commercial"]["rollup"]["duration_days"]
    row = out["Hospital"]["context_ledger"][0]
    assert row["factor"] == "Project type" and row["source"] == "builtin" and row["applied"] is True
    assert "Architectural finishes" in row["evidence"] and "Hospital" in row["evidence"]
    # the factor is the TRADE's: different for concrete and for MEP on the same project type
    conc = _q(item=RC, **{"Project type": "Hospital"})["context_net"]
    mep_item = next(i for i in kb.load_items() if i["discipline"] == "MEP" and i["work_type"] == "HVAC")
    mep = engine.item_result(mep_item, context={"Project type": "Hospital"})["context_net"]
    assert mep > conc > 1.0


def test_every_work_item_has_a_rate_on_every_project_type():
    types = kb.project_types()
    assert types == ["Residential", "Commercial", "Hospital", "Industrial", "Infrastructure",
                     "Oil & Gas", "Marine/Port", "Airport", "Power Plant"]
    items = kb.load_items()
    for it in items:
        g = kb.trade_group(it)
        assert g, (it["item_id"], it["discipline"], it["work_type"])       # no work item is left out
        for pt in types:
            f, label = kb.builtin_project_factor(it, pt)
            assert f is not None and 0.8 <= f <= 1.5 and label, (it["item_id"], pt)
    t, rows = engine.rates_database()
    assert t == types and len(rows) == len(items)
    assert all(set(r["rates"]) == set(types) and all(v for v in r["rates"].values()) for r in rows)
    # no two project types share a productivity within a trade (owner: "how do residential,
    # commercial, hospital and industrial have the same productivity - this is not logical")
    for g in kb.project_type_factors()['groups']:
        assert len(set(g['factors'].values())) == len(types), g['key']
    # every trade group's Commercial factor is the base
    assert all(g["factors"]["Commercial"] == 1.0 for g in kb.project_type_factors()["groups"])


def test_the_same_work_item_on_every_project_type_table():
    r = _q(item=PLASTER, **{"Project type": "Residential"})
    tbl = {x["project_type"]: x for x in r["project_type_rates"]}
    assert list(tbl) == kb.project_types()
    assert tbl["Residential"]["chosen"] and not tbl["Hospital"]["chosen"]
    assert tbl["Residential"]["output_per_day"] == r["components"][0]["rate"]["output_per_day"]
    assert tbl["Residential"]["total_mh"] == r["rollup"]["total_mh"]
    assert tbl["Hospital"]["factor"] == 1.2 and tbl["Commercial"]["factor"] == 1.0
    # the planner's own project-type factor is NOT in this table - it shows the library's own numbers
    mine = _q({"Project type": 2.0}, item=PLASTER, **{"Project type": "Residential"})
    assert mine["context_net"] == 2.0
    assert {x["project_type"]: x["output_per_day"] for x in mine["project_type_rates"]} == \
           {k: v["output_per_day"] for k, v in tbl.items()}


def test_an_item_can_carry_its_own_number_instead_of_its_trade_groups(monkeypatch):
    it = next(i for i in kb.load_items() if i["item_id"] == PLASTER)
    table = dict(kb.project_type_factors(), items={PLASTER: {"Industrial": 1.25}})
    monkeypatch.setattr(kb, "_PT_FACTORS", table)
    assert kb.builtin_project_factor(it, "Industrial")[0] == 1.25         # the item's own
    assert kb.builtin_project_factor(it, "Hospital")[0] == 1.2            # the group's


def test_methodology_is_the_estimate_optimistic_most_likely_pessimistic():
    """Owner: "the method that needs the higher duration is Pessimistic, the one that needs the
    lower duration is Optimistic, and the average one is Most likely"."""
    assert [n for n, _, _ in engine.ESTIMATES] == ["Optimistic", "Most likely", "Pessimistic"]
    o, m, p = (_q(Methodology=n) for n in ("Optimistic", "Most likely", "Pessimistic"))
    assert o["rollup"]["duration_days"] < m["rollup"]["duration_days"] < p["rollup"]["duration_days"]
    assert o["rollup"]["total_mh"] < m["rollup"]["total_mh"] < p["rollup"]["total_mh"]
    fw = lambda r: {c["component_id"]: c for c in r["components"]}["formwork"]["rate"]
    # each estimate is the work item's OWN low / likely / high rate from the library
    assert (fw(o)["mh_per_unit"], fw(m)["mh_per_unit"], fw(p)["mh_per_unit"]) == (0.95, 1.19, 1.49)
    assert fw(o)["output_per_day"] > fw(m)["output_per_day"] > fw(p)["output_per_day"]
    assert m["context_net"] == 1.0 and all(c["rate"]["adjusted"] is False for c in m["components"] if c.get("rate"))
    # Most likely = exactly the totals the range already showed as low / high
    assert o["rollup"]["total_mh"] == m["rollup"]["total_mh_low"]
    assert p["rollup"]["total_mh"] == m["rollup"]["total_mh_high"]
    row = {x["factor"]: x for x in p["context_ledger"]}["Methodology"]
    assert row["choice"] == "Pessimistic" and row["source"] == "estimate" and "longest duration" in row["evidence"]
    # an old saved 'Conventional' / blank reads as Most likely
    for old in ("Conventional", "Jump-form", "", None):
        r = _q(Methodology=old)
        assert r["estimate"] == "Most likely" and r["rollup"]["total_mh"] == m["rollup"]["total_mh"]


def test_the_three_estimates_are_shown_side_by_side():
    r = _q(Methodology="Optimistic")
    rows = {x["estimate"]: x for x in r["estimates"]}
    assert list(rows) == ["Optimistic", "Most likely", "Pessimistic"]
    assert rows["Optimistic"]["chosen"] and not rows["Most likely"]["chosen"]
    assert rows["Optimistic"]["total_mh"] == r["rollup"]["total_mh"]
    assert rows["Optimistic"]["duration_days"] < rows["Most likely"]["duration_days"] < rows["Pessimistic"]["duration_days"]
    assert all(x["when"] for x in rows.values())


def test_estimate_and_project_type_work_together():
    base = _q()
    r = _q(Methodology="Pessimistic", **{"Project type": "Industrial"})          # x1.10 on the hard case
    fw0 = {c["component_id"]: c for c in base["components"]}["formwork"]
    fw = {c["component_id"]: c for c in r["components"]}["formwork"]
    assert fw["rate"]["mh_per_unit"] == round(1.49 * 1.1, 2)
    assert abs(fw["man_hours"] - fw0["man_hours"] * 1.49 / 1.19 * 1.1) <= 2
    # the project-type table keeps the chosen estimate; the estimate table keeps the project type
    assert {x["project_type"]: x for x in r["project_type_rates"]}["Industrial"]["total_mh"] == r["rollup"]["total_mh"]
    assert {x["estimate"]: x for x in r["estimates"]}["Pessimistic"]["total_mh"] == r["rollup"]["total_mh"]


def test_the_project_type_factor_changes_rate_manhours_and_duration():
    base = _q()
    fw0 = {c["component_id"]: c for c in base["components"]}["formwork"]
    r = _q({"Project type": 1.25})
    fw = {c["component_id"]: c for c in r["components"]}["formwork"]
    assert r["context_net"] == 1.25
    assert fw["rate"]["adjusted"] is True and fw["rate"]["factor"] == 1.25
    assert fw["rate"]["output_per_day"] == round(fw0["rate"]["output_per_day"] / 1.25, 2)     # slower crew
    assert fw["rate"]["mh_per_unit"] == round(fw0["rate"]["mh_per_unit"] * 1.25, 2)
    assert fw["rate"]["output_per_day_base"] == fw0["rate"]["output_per_day"]                # the norm is kept
    assert fw["man_hours"] == round(fw0["man_hours"] * 1.25)
    assert abs(fw["duration_days"] - fw0["duration_days"] * 1.25) <= 0.1                     # duration follows
    row = r["context_ledger"][0]
    assert row["applied"] is True and row["source"] == "user" and "entered by you" in row["evidence"]


def test_the_planners_factor_replaces_the_builtin_one():
    r = _q({"Project type": 1.4}, **{"Project type": "Oil & Gas"})
    row = r["context_ledger"][0]
    assert r["context_net"] == 1.4 and row["source"] == "user" and row["builtin"] == 1.18


def test_a_bad_factor_is_ignored_and_reported_never_applied():
    for bad in (9, 0.05, "abc", -1):
        r = _q({"Project type": bad})
        row = r["context_ledger"][0]
        assert r["context_net"] == 1.0 and row["applied"] is False, bad
        assert "ignored" in row["evidence"], bad
    assert _q({"Project type": ""})["context_net"] == 1.0
    assert _q({"Project type": 1})["context_net"] == 1.0
    # a typed factor for Methodology (older saved settings) is no longer a thing: it is ignored
    assert _q({"Methodology": 0.5})["rollup"]["total_mh"] == _q()["rollup"]["total_mh"]


def test_project_type_applicability_is_reported():
    items = kb.load_items()
    it = next(i for i in items if "Residential" not in (i.get("project_types") or []) and i.get("project_types"))
    assert engine.item_result(it, context={"Project type": "Residential"})["project_type_applies"] is False
    ok = it["project_types"][0]
    assert engine.item_result(it, context={"Project type": ok})["project_type_applies"] is True
    assert engine.item_result(it, context={})["project_type_applies"] is None


def test_a_factor_inside_a_library_item_needs_evidence():
    """A multiplier written in a work item itself must name its evidence (the built-in
    project-type table is separate and says what it is: general practice)."""
    for it in kb.load_items():
        for dim, choices in (it.get("context_factors") or {}).items():
            for choice, entry in (choices or {}).items():
                assert entry.get("evidence"), (it["item_id"], dim, choice)
    assert "not yet verified against an egyptian reference" in kb.project_type_factors()["note"].lower()


def test_excel_summary_lists_the_factors_and_has_no_rates_database_sheet():
    import server
    r = _q(Methodology="Optimistic", **{"Project type": "Industrial"})
    sheets = server._prodintel_excel_sections(r)
    summary = dict((row[0], row[1]) for row in sheets[0]["blocks"][0]["rows"])
    assert summary["Factor · Project type (Industrial)"].startswith("x1.1 — built-in factor for Concrete structure")
    assert summary["Factor · Methodology (Optimistic)"].startswith("Optimistic estimate")
    assert summary["All factors together"].startswith("x1.1")
    names = [sh["name"] for sh in sheets]
    assert "By project type" in names and "Methodology" in names
    assert "Rates database" not in names                       # left out of the Excel export (owner)
    meth = next(sh for sh in sheets if sh["name"] == "Methodology")["blocks"][0]
    assert [row[0] for row in meth["rows"]] == ["Optimistic (used)", "Most likely", "Pessimistic"]
    bpt = next(sh for sh in sheets if sh["name"] == "By project type")["blocks"][0]
    assert [row[0] for row in bpt["rows"]][:2] == ["Residential", "Commercial"]
    assert any(row[0] == "Industrial (chosen)" for row in bpt["rows"])


def test_the_library_has_an_infrastructure_discipline():
    """Owner: "there is no productivity rates for infrastructure works" - roads and every utility
    network are work items of their own discipline, each with rates and the three estimates."""
    tree = {d["name"]: d for d in kb.build_tree()}
    inf = tree["Infrastructure"]
    systems = {s["name"]: len(s["items"]) for s in inf["systems"]}
    for name in ("Roads", "Water Network", "Sewer Network", "Stormwater Drainage", "Irrigation Network",
                 "Electrical Network", "Street Lighting", "Telecom Network", "Gas Network", "Bridges"):
        assert systems.get(name), name
    assert inf["count"] >= 45
    for it in (i for i in kb.load_items() if i["discipline"] == "Infrastructure"):
        assert kb.trade_group(it)["key"] == "infrastructure", it["item_id"]
        for c in it["components"]:
            r = c["rate"]
            assert 0 < r["low"] < r["likely"] < r["high"] and r["output_per_day"] > 0, (it["item_id"], c["component_id"])
            assert c["gang"], it["item_id"]
    r = engine.query("infrastructure.water_network.hdpe_water_pipeline_dn110_dn315",
                     context={"Project type": "Infrastructure"}, quantity=1000)
    assert r["found"] and r["rollup"]["total_mh"] > 0 and r["rollup"]["duration_days"] > 0
    est = {x["estimate"]: x["duration_days"] for x in r["estimates"]}
    assert est["Optimistic"] < est["Most likely"] < est["Pessimistic"]
    # fastest on an infrastructure corridor, slower inside a port
    pt = {x["project_type"]: x["output_per_day"] for x in r["project_type_rates"]}
    assert pt["Infrastructure"] > pt["Commercial"] > pt["Marine/Port"]


def test_rates_name_their_egyptian_reference_and_nothing_else_claims_one():
    """Owner: "the productivity rates must be based on the productivity rates in Egypt" and "add
    these references to the feature". A rate either names the Egyptian reference it is taken
    from, or says plainly that it is a general estimate not yet verified against one."""
    refs = {r["key"]: r for r in kb.references()["references"]}
    assert refs["afifi_2017"]["status"] == "loaded" and refs["afifi_2017"]["country"] == "Egypt"
    assert sum(1 for r in refs.values() if r["status"] == "listed") >= 3
    eg = est = 0
    for it in kb.load_items():
        for c in it["components"]:
            p = c["provenance"]
            if p.get("reference"):
                assert p["reference"] in refs and p["source_type"] == "Egyptian reference"
                assert "Afifi" in p["basis"]
                eg += 1
            else:
                assert p["source_type"].startswith("General estimate"), (it["item_id"], c["component_id"])
                assert not p["basis"].lower().startswith("egypt"), (it["item_id"], p["basis"])
                est += 1
    assert eg >= 35 and est > 0
    # the reference's own figures, exactly
    tile = engine.query("architectural.finishes.tiling.floor_tiling", context={"Project type": "Commercial"})
    assert tile["components"][0]["rate"]["output_per_day"] == 25
    plaster = engine.query(PLASTER, context={"Project type": "Commercial"})
    assert plaster["components"][0]["rate"]["output_per_day"] == 40
    col = {c["component_id"]: c for c in engine.query(RC, context={"Project type": "Commercial"})["components"]}
    assert col["formwork"]["rate"]["output_per_day"] == 13.5            # 1.5 m3/day x 9 m2 per m3
    assert col["formwork"]["gang"] == [{"trade": "Carpenter", "count": 1}, {"trade": "Helper", "count": 1}]
    # ... and the feature shows it
    src = engine.query(RC, context={"Project type": "Commercial"}, quantity=100)["sources"]
    assert src["egyptian_count"] == 2 and src["total"] == 3
    assert [x["egyptian"] for x in src["components"]] == [True, True, False]
    assert any(r["key"] == "afifi_2017" for r in src["references"])
    import server
    names = [sh["name"] for sh in server._prodintel_excel_sections(engine.query(RC, context={"Project type": "Commercial"}, quantity=100))]
    assert names[-1] == "Sources & references"
