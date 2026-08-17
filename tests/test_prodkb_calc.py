"""Step 1 engine — the auditable chain, per-activity driver selection, and
context-keyed rates that do NOT mix across project types."""
import os

from p6_prodkb import compute, kb

BASE = os.path.join(os.path.dirname(__file__), "..", "productivity_kb")


def _templates():
    return kb.by_id(kb.load_templates(bundled=BASE, overlay=[]))


def test_production_rate_chain_rc_column():
    r = compute(_templates()["civil.concrete.rc_column.conventional"], 220)
    assert r["driver"] == "production_rate"
    assert r["duration_days"] == 10
    assert r["labor"]["man_hours"] == 1280
    assert r["labor"]["mnp"] == 16
    assert r["rate"]["source"] == "built_in_kb"
    assert "RC column" in r["rate"]["basis"]
    assert r["rate"]["confidence"] == "high"


def test_context_selection_does_not_mix_rates():
    t = _templates()["finishes.plaster.internal_wall"]
    villa = compute(t, 300, context={"project_type": "Residential/Villa"})
    indus = compute(t, 300, context={"project_type": "Industrial"})
    assert villa["rate"]["value"] == 25 and "Villa" in villa["rate"]["basis"]
    assert indus["rate"]["value"] == 18 and "Industrial" in indus["rate"]["basis"]
    assert villa["duration_days"] == 12
    assert indus["duration_days"] == 17
    # same activity, different context -> different rate, never mixed
    assert villa["duration_days"] != indus["duration_days"]


def test_method_specific_tiling():
    t = _templates()
    floor = compute(t["finishes.tiling.floor"], 200)
    wall = compute(t["finishes.tiling.wall"], 200)
    assert floor["duration_days"] == 10
    assert wall["duration_days"] == 17
    assert floor["duration_days"] != wall["duration_days"]


def test_resource_driven_mnp_is_na():
    r = compute(_templates()["civil.earthworks.bulk_excavation"], 12000)
    assert r["driver"] == "resource_driven"
    assert r["duration_days"] == 15
    assert r["labor"]["mnp"] is None          # equipment sets the pace
    assert r["labor"]["man_hours"] == 960      # support crew still tracked
    assert any(e["governing"] for e in r["equipment"])


def test_lead_time_has_no_manpower():
    r = compute(_templates()["industrial.equipment.compressor.supply"], 1)
    assert r["driver"] == "lead_time"
    assert r["duration_days"] == 300
    assert r["labor"]["man_hours"] is None
    assert r["labor"]["mnp"] is None


def test_typical_loop_check():
    r = compute(_templates()["commissioning.ic.loop_check"], 250)
    assert r["duration_days"] == 42
    assert r["labor"]["man_hours"] == 2016
    assert r["labor"]["mnp"] == 6


def test_calendar_hours_not_universal_8():
    r = compute(_templates()["civil.concrete.rc_column.conventional"], 220, calendar_hours=10)
    assert r["hours_per_day"] == 10
    assert r["labor"]["man_hours"] == 1600     # more hours/day -> more man-hours
    assert r["labor"]["mnp"] == 16             # MNP (peak crew) invariant to hours/day


def test_needs_qty_when_missing():
    r = compute(_templates()["civil.concrete.rc_column.conventional"], None)
    assert r["needs_qty"] is True
    assert r["duration_days"] is None
    assert r["rate"]["value"] == 12            # rate + crew still shown; planner only types a number
