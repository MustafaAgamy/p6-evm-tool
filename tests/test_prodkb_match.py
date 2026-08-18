"""Step 1 matching pipeline — activity name/WBS -> template + context -> chain."""
import os

from p6_prodkb import kb, match as m

BASE = os.path.join(os.path.dirname(__file__), "..", "productivity_kb")


def _t():
    return kb.load_templates(bundled=BASE, overlay=[])


def test_matches_rc_columns():
    res = m.match({"name": "RC Columns to Level 3", "wbs_path": "Structure/Columns"}, _t())
    assert res["template"]["template_id"] == "civil.concrete.rc_column.conventional"
    assert res["band"] in ("confirmed", "review", "low")


def test_matches_plaster():
    res = m.match({"name": "Internal Wall Plastering - Villa Block A"}, _t())
    assert res["template"]["template_id"] == "finishes.plaster.internal_wall"


def test_matches_bulk_excavation():
    res = m.match({"name": "Bulk Excavation for Raft"}, _t())
    assert res["template"]["template_id"] == "civil.earthworks.bulk_excavation"


def test_no_match_flags_planner():
    res = m.match({"name": "Zzz miscellaneous nonsense token"}, _t())
    assert res["template"] is None or res["band"] == "needs_planner"


def test_resolve_end_to_end_villa_context():
    out = m.resolve({"name": "Internal Wall Plaster - Villa"}, 300,
                    project_type="Residential/Villa", templates=_t())
    assert out["match"]["template"]["template_id"] == "finishes.plaster.internal_wall"
    assert out["result"]["duration_days"] == 12     # villa rate via context
    assert out["result"]["rate"]["value"] == 25
    assert out["result"]["rate"]["conditions"]      # applicability shown
    assert out["status"] == "ok"


def test_status_knowledge_not_available():
    out = m.resolve({"name": "Specialized Process Equipment Installation"}, 5,
                    project_type="Oil & Gas", templates=_t())
    assert out["status"] == "knowledge_not_available"
    assert out["result"] is None                    # never invents a rate for a KB gap
    assert out["status_detail"]["missing"] == "productivity_pattern"
    assert out["status_detail"]["project_type"] == "Oil & Gas"


def test_status_needs_input_when_quantity_missing():
    out = m.resolve({"name": "RC Columns to Level 3"}, None,
                    project_type="Industrial", templates=_t())
    assert out["status"] == "needs_input"           # matched a pattern, but qty missing
    assert out["result"]["needs_qty"] is True
    assert out["status_detail"]["missing"] == "quantity"
