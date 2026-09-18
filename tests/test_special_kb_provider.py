"""Tests for the Knowledge Base Special Report provider.

The KB provider exposes the reference standard for the type the open schedule is
auto-detected as (the KB library detail pane, scoped to this project). The bundled
``minimal.xml`` matches NO known type, so it exercises the honest 'no_data' gate;
a crafted schedule whose activity names carry a real KB type's signatures
exercises the 'ready' path with real content.
"""
import db
from p6_special.providers import kb
from p6_special.context import SpecialContext


def _seed(fixture):
    pid = db.upsert_project('P1', 'Grain')
    db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    return pid


def _items(ctx):
    return {i.id: i for i in kb.provide(ctx)}


# ── a schedule that detects a real KB type ───────────────────────────────────
def _detecting_xml(tmp_path):
    """Write a valid P6 XML whose activity names carry the FIRST KB entry's
    signatures, so detect_subtype resolves a real curated type (robust to KB
    reordering: it reads whatever load_kb() ships first)."""
    from p6_kb.kb import load_kb
    entry = load_kb()[0]
    sigs = (entry.get('signatures') or [])[:10] or ['road', 'pavement']
    acts = []
    for i, s in enumerate(sigs, 1):
        acts.append(
            f'<Activity><ObjectId>OBJ{i:03d}</ObjectId><Id>ACT{i:03d}</Id>'
            f'<Name>{s} works</Name><Status>Not Started</Status>'
            f'<CalendarObjectId>CAL1</CalendarObjectId><WBSObjectId>100</WBSObjectId>'
            f'<PercentComplete>0</PercentComplete><PlannedDuration>80</PlannedDuration>'
            f'<PlannedStartDate>2024-01-01T00:00:00</PlannedStartDate>'
            f'<PlannedFinishDate>2024-03-01T00:00:00</PlannedFinishDate></Activity>')
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<APIBusinessObjects>'
        '<Calendar><ObjectId>CAL1</ObjectId><Name>Standard</Name>'
        '<StandardWorkWeek>'
        '<StandardWorkHours><DayOfWeek>Saturday</DayOfWeek></StandardWorkHours>'
        '<StandardWorkHours><DayOfWeek>Sunday</DayOfWeek></StandardWorkHours>'
        '</StandardWorkWeek></Calendar>'
        '<Project><ObjectId>1</ObjectId><Id>PRJ-KB</Id><Name>KB Detect</Name>'
        '<DataDate>2024-07-01T00:00:00</DataDate>'
        '<WBS><ObjectId>100</ObjectId><Name>Construction Works</Name>'
        '<ParentObjectId></ParentObjectId></WBS>'
        + ''.join(acts) + '</Project></APIBusinessObjects>')
    p = tmp_path / 'kb_detect.xml'
    p.write_text(xml, encoding='utf-8')
    return p


# ── the honest 'no_data' gate (minimal.xml matches no type) ──────────────────
def test_minimal_fixture_detects_no_type(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    # detection helper returns None → every item must gate to 'no_data'.
    assert kb._entry(ctx) is None
    for item in _items(ctx).values():
        assert item.availability(ctx) == 'no_data'


def test_produce_returns_dict_and_complements_availability(temp_db, xml_path):
    """The #1 past defect: a 'ready' item that renders empty. produce() must
    return a payload dict without raising, and availability must exactly
    complement it (ready ⇔ real content; no_data ⇔ NO_DATA)."""
    ctx = SpecialContext(_seed(xml_path))
    for item in _items(ctx).values():
        payload = item.produce(ctx)
        assert isinstance(payload, dict) and payload.get('kind')
        avail = item.availability(ctx)
        if avail == 'ready':
            assert payload.get('kind') != 'no_data'
        else:
            assert avail == 'no_data'
            assert payload.get('kind') == 'no_data'


def test_no_snapshot_all_no_data(temp_db):
    ctx = SpecialContext(9999)
    for item in _items(ctx).values():
        assert item.availability(ctx) == 'no_data'
        assert item.produce(ctx).get('kind') == 'no_data'


# ── the 'ready' path (a schedule that detects a real type) ───────────────────
def test_ready_path_reference_standard(temp_db, tmp_path):
    fixture = _detecting_xml(tmp_path)
    ctx = SpecialContext(_seed(fixture))
    assert kb._entry(ctx) is not None            # a real KB type resolved
    item = _items(ctx)['kb:reference_standard']
    assert item.availability(ctx) == 'ready'
    pl = item.produce(ctx)
    assert pl['kind'] == 'group'
    assert pl.get('blocks')                       # non-empty (callout + WBS/activities …)


def test_ready_path_activities_and_wbs_tables(temp_db, tmp_path):
    fixture = _detecting_xml(tmp_path)
    ctx = SpecialContext(_seed(fixture))
    items = _items(ctx)
    for iid in ('kb:standard_activities', 'kb:standard_wbs'):
        it = items[iid]
        assert it.availability(ctx) == 'ready'
        pl = it.produce(ctx)
        assert pl['kind'] == 'table'
        assert pl.get('columns') and pl.get('rows')


def test_ready_path_every_item_complements(temp_db, tmp_path):
    """Even on a detecting schedule, each item's availability must match produce:
    a slice with no data (e.g. a type with no logic_rules) stays 'no_data'."""
    fixture = _detecting_xml(tmp_path)
    ctx = SpecialContext(_seed(fixture))
    for item in _items(ctx).values():
        payload = item.produce(ctx)
        assert isinstance(payload, dict) and payload.get('kind')
        if item.availability(ctx) == 'ready':
            assert payload.get('kind') != 'no_data'
        else:
            assert payload.get('kind') == 'no_data'


def test_activities_table_matches_screen_columns(temp_db, tmp_path):
    """Columns/format mirror the KB screen's kb-acts table exactly."""
    fixture = _detecting_xml(tmp_path)
    ctx = SpecialContext(_seed(fixture))
    pl = _items(ctx)['kb:standard_activities'].produce(ctx)
    assert pl['columns'] == ['Activity', 'WBS', 'Typical sequence', 'Dur (d)', 'Why it matters']
