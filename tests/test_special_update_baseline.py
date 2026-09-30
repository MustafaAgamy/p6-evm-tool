"""Review F1 — Reporting Studio's Update Analysis items follow the screen's baseline rule.

The Update Analysis screen refuses to measure an update against its own Planned dates (no
baseline inside the file and none attached: /api/update/analyze answers 'no_baseline'). The
Studio's Update items read the SAME rule (p6_update.analysis.update_has_baseline): not ready,
with the screen's notice, and a saved report that still lists them shows the notice — never
"planned to be at 18.85%" measured against the update's own dates. With the baseline attached
for the update, the items are ready and identical to the XML exported with its baseline.
"""
import re

import db
import tests.test_parser_parity as H
from p6_special import registry
from p6_special.context import SpecialContext
from p6_special.providers import update
from tests.test_baseline_everywhere import WITH_BL, NO_BL, BASELINE_ALONE


def _seed(tmp_path, name, text, pid_name):
    p = tmp_path / name
    p.write_text(text, encoding='utf-8')
    pid = db.upsert_project(pid_name, pid_name)
    sid = db.insert_snapshot(pid, '2025-04-01', str(p), str(p), name, 3, 1)
    db.insert_metrics(sid, {'pv': 1.0, 'ev': 1.0, 'ac': 1.0, 'spi': 1.0, 'cpi': 1.0, 'delay_days': 0,
                            'overall_planned_pct': 0.5, 'overall_actual_pct': 0.5, 'variance': 0.0})
    return pid, sid


def _items(ctx):
    return {i.id: i for i in update.provide(ctx)}


def _html(payload):
    """The rendered section with the Studio's per-feature wrapper — compared across files."""
    return re.sub(r'\s+', ' ', (payload or {}).get('html') or '')


def test_no_baseline_gives_no_ready_update_item_and_says_why(temp_db, tmp_path):
    pid, _ = _seed(tmp_path, 'no_bl.xml', NO_BL, 'P-nobl')
    ctx = SpecialContext(pid)
    items = _items(ctx)
    assert items, 'the Update group is still listed (with the reason)'
    assert all(it.availability(ctx) != 'ready' for it in items.values())
    assert not any(k.startswith('update:bycode:') or k.startswith('update:scope:') for k in items)
    d = items['update:time'].descriptor(ctx)
    assert d['availability'] == 'needs_input'
    assert 'Attach the baseline (XER or XML)' in d['note'] and 'own Planned dates' in d['note']
    # a saved report that still lists the items: the screen's notice, not own-dates numbers
    for key in ('update:time', 'update:bycode', 'update:conclusion'):
        pl = items[key].produce(ctx)
        assert pl['kind'] == 'note' and 'Attach the baseline (XER or XML)' in pl['message'], key
    groups = registry.catalog(ctx)
    ug = next(g for g in groups if g['feature'] == 'update')
    assert all(i['availability'] == 'needs_input' and i.get('note') for i in ug['items'])


def test_xer_update_without_baseline_rows_is_not_ready_and_names_p6s_baseline(temp_db, tmp_path):
    pid, _ = _seed(tmp_path, 'update.xer', H.build_xer(baseline_rows=False), 'P-xer')
    ctx = SpecialContext(pid)
    items = _items(ctx)
    assert all(it.availability(ctx) == 'needs_input' for it in items.values())
    note = items['update:time'].descriptor(ctx)['note']
    assert f'P6 names “{H.BASELINE["name"]}” as this update’s baseline' in note
    body = items['update:time'].produce(ctx)
    assert body['kind'] == 'note' and 'planned to be at' not in str(body)


def test_attached_baseline_makes_the_items_ready_and_equal_to_the_xml_with_baseline(temp_db, tmp_path):
    bl = tmp_path / 'baseline.xml'
    bl.write_text(BASELINE_ALONE, encoding='utf-8')
    pid_a, sid_a = _seed(tmp_path, 'no_bl.xml', NO_BL, 'P-att')
    db.save_evm_extras(sid_a, {})
    db.save_baseline(sid_a, str(bl), str(bl))                 # attached for this update (EVM / UA)
    pid_e, _ = _seed(tmp_path, 'with_bl.xml', WITH_BL, 'P-emb')
    att, emb = SpecialContext(pid_a, snapshot_id=sid_a), SpecialContext(pid_e)
    ia, ie = _items(att), _items(emb)
    assert sorted(ia) == sorted(ie)                           # the same items, per-dimension ones too
    assert any(k.startswith('update:bycode:') for k in ia)
    for key in ia:
        assert ia[key].availability(att) == ie[key].availability(emb), key
        assert 'note' not in ia[key].descriptor(att), key
    for key in ('update:time', 'update:bycode', 'update:counts', 'update:conclusion'):
        pa, pe = ia[key].produce(att), ie[key].produce(emb)
        assert pa.get('kind') == 'html', (key, pa)
        assert _html(pa) == _html(pe), key
