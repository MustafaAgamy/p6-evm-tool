"""Tests for the Baseline Narrative Special Report provider.

The provider reuses ``p6_evm.narrative.build_narrative`` on the stored DB result,
so these tests seed a snapshot + metrics (+ a category) via ``temp_db`` and the
``xml_path`` fixture, then assert each item's ``produce(ctx)`` returns a payload
dict without raising, and that availability exactly complements produce().
"""
import db
from p6_special.providers import narrative
from p6_special.context import SpecialContext


def _seed(fixture):
    pid = db.upsert_project('P1', 'Grain')
    sid = db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    db.insert_metrics(sid, {
        'pv': 1e6, 'ev': 6e5, 'ac': 7e5, 'spi': 0.6, 'cpi': 0.857, 'delay_days': 5,
        'overall_planned_pct': 0.614, 'overall_actual_pct': 0.404, 'variance': -0.21,
    })
    db.insert_category_metrics(sid, {
        'Construction': {'weight': 0.855, 'planned_pct': 0.58, 'actual_pct': 0.38,
                         'bac': 1e6, 'ac': 7e5, 'activity_count': 50, 'overridden': False},
    })
    return pid


def _items(ctx):
    return {i.id: i for i in narrative.provide(ctx)}


def _text_block(pl):
    """The underlying text payload of a section item, whether it came back as a bare
    ``text`` payload (neutral section) or wrapped in a ``group`` with a verdict note
    (non-neutral section)."""
    if pl.get('kind') == 'text':
        return pl
    if pl.get('kind') == 'group':
        for b in pl.get('blocks') or []:
            if b.get('kind') == 'text':
                return b
    return None


def _verdict_note(pl):
    """The ``Verdict: …`` note payload from a section item, or None when the section
    is neutral (a bare text payload with no verdict)."""
    if pl.get('kind') != 'group':
        return None
    for b in pl.get('blocks') or []:
        if b.get('kind') == 'note':
            return b
    return None


# ── shape: every item produces a payload dict without raising ─────────────────
def test_every_item_produces_a_payload_dict(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    items = _items(ctx)
    # status + the 5 sections
    assert set(items) == {
        'narrative:status', 'narrative:summary', 'narrative:schedule',
        'narrative:cost', 'narrative:areas', 'narrative:outlook',
    }
    for iid, it in items.items():
        pl = it.produce(ctx)
        assert isinstance(pl, dict) and pl.get('kind') != 'no_data', iid


def test_status_is_keyvals_mirroring_the_header(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    pl = _items(ctx)['narrative:status'].produce(ctx)
    assert pl['kind'] == 'keyvals'
    pairs = dict(pl['pairs'])
    assert pairs['Project'] == 'Grain'
    assert pairs['Data date'] == '2026-01-01'          # sliced YYYY-MM-DD, like narrative.js
    # SPI 0.6 → 'is significantly behind schedule' → overall tone bad → 'Action needed'.
    assert pairs['Status'] == 'Action needed'


def test_status_carries_the_excel_header_figure_block(temp_db, xml_path):
    """The status item surfaces the same figure block narrative_excel._header_block
    shows — SPI, CPI, planned/actual complete and delay — read straight from
    ctx.evm (SPI/CPI 2 dp, complete % whole, delay bare int)."""
    ctx = SpecialContext(_seed(xml_path))
    pairs = dict(_items(ctx)['narrative:status'].produce(ctx)['pairs'])
    assert pairs['SPI · Schedule'] == '0.60'           # fmt.ratio(0.6)
    assert pairs['CPI · Cost'] == '0.86'               # fmt.ratio(0.857)
    assert pairs['Planned complete (%)'] == '61'       # round(0.614*100)
    assert pairs['Actual complete (%)'] == '40'        # round(0.404*100)
    assert pairs['Delay (days)'] == '5'                # bare int, unit in the label


def test_sections_carry_paragraphs(temp_db, xml_path):
    """Every section item carries its prose — as a bare ``text`` payload (neutral
    section) or as a ``group`` wrapping the text plus a verdict note."""
    ctx = SpecialContext(_seed(xml_path))
    items = _items(ctx)
    for key in ('summary', 'schedule', 'cost', 'areas', 'outlook'):
        pl = items[f'narrative:{key}'].produce(ctx)
        assert pl['kind'] in ('text', 'group')
        tb = _text_block(pl)
        assert tb and tb['paragraphs']
        assert all(isinstance(p, str) and p for p in tb['paragraphs'])


def test_section_text_matches_build_narrative(temp_db, xml_path):
    """The reused generator IS the source of truth — the item text must equal
    build_narrative's own section paragraphs (no divergent hand-rebuild)."""
    from p6_evm.narrative import build_narrative
    ctx = SpecialContext(_seed(xml_path))
    result = ctx.evm
    secs = {s['key']: s for s in build_narrative(result)['sections']}
    for key in ('summary', 'schedule', 'cost', 'areas', 'outlook'):
        pl = _items(ctx)[f'narrative:{key}'].produce(ctx)
        assert _text_block(pl)['paragraphs'] == secs[key]['paragraphs']


def test_nonneutral_sections_carry_matching_verdict_note(temp_db, xml_path):
    """Gap (b): each section's build_narrative tone is surfaced. A non-neutral tone
    (good/warn/bad) adds a coloured 'Verdict: <word>' note (word from the provider's
    _TONE_WORD map, note tone == the section tone); a neutral section stays plain
    text with no verdict. Expectations are derived from build_narrative itself, so
    the test tracks the source of truth rather than a fixed seed outcome."""
    from p6_evm.narrative import build_narrative
    ctx = SpecialContext(_seed(xml_path))
    secs = {s['key']: s for s in build_narrative(ctx.evm)['sections']}
    saw_nonneutral = False
    for key in ('summary', 'schedule', 'cost', 'areas', 'outlook'):
        pl = _items(ctx)[f'narrative:{key}'].produce(ctx)
        tone = secs[key]['tone']
        note = _verdict_note(pl)
        if tone and tone != 'neutral':
            saw_nonneutral = True
            assert note is not None, key
            assert note['tone'] == tone
            assert note['message'] == f'Verdict: {narrative._TONE_WORD[tone]}'
        else:
            assert note is None, key             # neutral → no false verdict
            assert pl['kind'] == 'text'
    # 'areas' is always neutral in build_narrative; the seed drives the rest non-neutral.
    assert secs['areas']['tone'] == 'neutral'
    assert saw_nonneutral


def test_item_title_equals_section_heading(temp_db, xml_path):
    from p6_evm.narrative import build_narrative
    ctx = SpecialContext(_seed(xml_path))
    titles = {s['key']: s['title'] for s in build_narrative(ctx.evm)['sections']}
    items = _items(ctx)
    for key, title in titles.items():
        assert items[f'narrative:{key}'].title == title


# ── availability exactly complements produce() ────────────────────────────────
def test_availability_ready_with_stored_result(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    for it in narrative.provide(ctx):
        assert it.availability(ctx) == 'ready'


def test_availability_no_data_without_result(temp_db):
    """No stored result → every item reports 'no_data' AND produce returns the
    NO_DATA sentinel (never a 'ready' item that then renders empty)."""
    ctx = SpecialContext(9999)
    for it in narrative.provide(ctx):
        assert it.availability(ctx) == 'no_data'
        assert it.produce(ctx)['kind'] == 'no_data'
