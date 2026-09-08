"""Tests for the Overview Special Report provider.

The Overview provider must be HONEST: it only re-presents statuses/severities other
features already produced. These tests seed a project with EVM metrics + audit
modules (so ctx.evm and ctx.audit are populated) and assert that:
  * the status header defers the single verdict (always None),
  * every chip carries domain/tone/headline, and a domain with no data reads a
    neutral "Not run" (never a guessed colour),
  * the attention register aggregates the audit modules' OWN severities, ordered
    high→medium→low→info, capped at 8 (+ an optional "+N more"), each with a source
    detail line,
  * both items are registered in the catalog.
"""
import db
from p6_special import registry
from p6_special.providers import overview
from p6_special.context import SpecialContext

_SEV_RANK = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}


def _module(key, name, severity, count, score=50):
    """A stored audit-module dict with `count` findings each carrying `severity`
    (title-case, exactly as the real modules emit it)."""
    return {
        'module': key, 'name': name, 'score': score, 'grade': 'C', 'pct': 10.0,
        'kpis': {}, 'wbs_summary': [],
        'findings': [{'activity_id': f'{key}-{i}', 'activity_name': 'Act',
                      'wbs_path': 'Project > Discipline', 'severity': severity,
                      'recommendation': 'Fix it'} for i in range(count)],
    }


def _seed(fixture, modules):
    """Seed metrics + the given audit modules for one snapshot; no weather saved."""
    pid = db.upsert_project('OV1', 'Overview Fixture')
    sid = db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    db.insert_metrics(sid, {
        'pv': 1e6, 'ev': 6e5, 'ac': 7e5, 'spi': 0.6, 'cpi': 0.857, 'delay_days': 5,
        'overall_planned_pct': 0.61, 'overall_actual_pct': 0.40, 'variance': -0.21,
    })
    order = [m['module'] for m in modules]
    db.insert_audit_modules(sid, {'module_order': order,
                                  'modules': {m['module']: m for m in modules}})
    return pid, sid


def _items(ctx):
    return {i.id: i for i in overview.provide(ctx)}


# ── status header ────────────────────────────────────────────────────────────
def test_status_header_defers_verdict_and_lists_domains(temp_db, xml_path):
    pid, sid = _seed(xml_path, [_module('dangling', 'Dangling Activities', 'High', 2)])
    ctx = SpecialContext(pid, snapshot_id=sid)
    pl = _items(ctx)['overview:status_header'].produce(ctx)

    assert pl['kind'] == 'status_header'
    assert pl['verdict'] is None                       # DEFERRED — the honesty rule
    domains = pl['domains']
    assert isinstance(domains, list) and domains
    for d in domains:
        assert set(('domain', 'tone', 'headline')) <= set(d)
        assert d['tone'] in ('neutral', 'accent', 'good', 'warn', 'bad')


def test_status_header_neutral_not_run_for_absent_domain(temp_db, xml_path):
    """Buildability (and Weather, unsaved here) must read neutral 'Not run' — never a
    guessed green/amber/red for a domain that was not assessed."""
    pid, sid = _seed(xml_path, [_module('dangling', 'Dangling Activities', 'High', 2)])
    ctx = SpecialContext(pid, snapshot_id=sid)
    domains = _items(ctx)['overview:status_header'].produce(ctx)['domains']

    not_run = [d for d in domains if d['tone'] == 'neutral' and d['headline'] == 'Not run']
    assert not_run, domains
    assert any(d['domain'] == 'Buildability' for d in not_run)


def test_evm_chip_present_and_neutral(temp_db, xml_path):
    """EVM has no stored pass/fail band → its chip is ALWAYS neutral (SPI/CPI shown,
    never coloured)."""
    pid, sid = _seed(xml_path, [_module('dangling', 'Dangling Activities', 'High', 1)])
    ctx = SpecialContext(pid, snapshot_id=sid)
    domains = _items(ctx)['overview:status_header'].produce(ctx)['domains']
    evm = [d for d in domains if d['domain'] == 'EVM']
    assert evm and evm[0]['tone'] == 'neutral'
    assert 'SPI' in evm[0]['headline'] and 'CPI' in evm[0]['headline']


def test_schedule_chip_uses_health_verdict_band(temp_db, xml_path):
    """Schedule-quality tone comes from the Schedule Health roll-up's OWN verdict —
    a low overall health is 'Not ready to submit' → tone 'bad'. Not an invented band."""
    pid, sid = _seed(xml_path, [
        _module('dangling', 'Dangling Activities', 'Critical', 3, score=20),
        _module('negative_float', 'Negative Float', 'Critical', 2, score=10),
    ])
    ctx = SpecialContext(pid, snapshot_id=sid)
    domains = _items(ctx)['overview:status_header'].produce(ctx)['domains']
    sched = [d for d in domains if d['domain'] == 'Schedule quality'][0]
    # health.verdict for a sub-80 score is 'Not ready to submit' → mapped to 'bad'
    assert sched['tone'] == 'bad'
    assert sched['headline'].endswith('%')


def test_status_header_availability(temp_db, xml_path):
    pid, sid = _seed(xml_path, [_module('dangling', 'Dangling Activities', 'High', 1)])
    ctx = SpecialContext(pid, snapshot_id=sid)
    assert _items(ctx)['overview:status_header'].availability(ctx) == 'ready'
    assert overview.provide(SpecialContext(9999))[0].availability(SpecialContext(9999)) == 'no_data'


# ── what needs attention ───────────────────────────────────────────────────
def test_attention_orders_by_severity_and_carries_detail(temp_db, xml_path):
    pid, sid = _seed(xml_path, [
        _module('lag_lead', 'Lag & Lead', 'Low', 4),
        _module('dangling', 'Dangling Activities', 'High', 2),
        _module('out_of_sequence', 'Out of Sequence', 'Critical', 3),
    ])
    ctx = SpecialContext(pid, snapshot_id=sid)
    pl = _items(ctx)['overview:attention'].produce(ctx)

    assert pl['kind'] == 'findings'
    items = pl['items']
    assert len(items) == 3
    # each item names its source
    for it in items:
        assert it.get('detail'), it
        assert it['detail'].startswith('Schedule Audit')
    # ordered high → medium → low → info (Critical maps to 'high')
    ranks = [_SEV_RANK[it['severity']] for it in items]
    assert ranks == sorted(ranks)
    assert items[0]['severity'] == 'high'      # the Critical out-of-sequence finding
    assert items[-1]['severity'] == 'low'      # the lag & lead findings


def test_attention_omits_modules_without_severity(temp_db, xml_path):
    """A module whose findings carry no severity (e.g. the CPLI driving path — a route,
    not a defect list) has no existing classification to re-present, so it is omitted
    rather than assigned a guessed severity."""
    no_sev = {'module': 'cpli', 'name': 'Critical Path / CPLI', 'score': 90,
              'grade': 'A', 'pct': 0.0, 'kpis': {}, 'wbs_summary': [],
              'findings': [{'activity_id': 'A1', 'activity_name': 'Drive', 'start': '2026-01-01'}]}
    pid, sid = _seed(xml_path, [no_sev,
                                _module('dangling', 'Dangling Activities', 'High', 1)])
    ctx = SpecialContext(pid, snapshot_id=sid)
    items = _items(ctx)['overview:attention'].produce(ctx)['items']
    assert [it['detail'] for it in items] == ['Schedule Audit · Dangling Activities']


def test_attention_caps_at_eight_with_more_note(temp_db, xml_path):
    mods = [_module(k, k.replace('_', ' ').title(), 'High', 1) for k in (
        'dangling', 'float', 'out_of_sequence', 'lag_lead', 'open_ends',
        'relationship_types', 'high_duration', 'leads', 'negative_float', 'whole_day')]
    pid, sid = _seed(xml_path, mods)                    # 10 flagged modules
    ctx = SpecialContext(pid, snapshot_id=sid)
    items = _items(ctx)['overview:attention'].produce(ctx)['items']

    # 8 real items + a single "+N more" info line
    assert len(items) == 9
    real, more = items[:8], items[-1]
    assert all(it['severity'] != 'info' or 'more' in it['title'] for it in real)
    assert more['severity'] == 'info'
    assert more['title'] == '+2 more in the report'


def test_attention_empty_message(temp_db, xml_path):
    """No findings across the modules → the honest empty message, not a fake all-clear
    with a colour."""
    pid, sid = _seed(xml_path, [_module('dangling', 'Dangling Activities', 'High', 0)])
    ctx = SpecialContext(pid, snapshot_id=sid)
    pl = _items(ctx)['overview:attention'].produce(ctx)
    assert pl['items'] == []
    assert pl['empty'] == 'Nothing flagged this update.'


def test_attention_availability(temp_db, xml_path):
    pid, sid = _seed(xml_path, [_module('dangling', 'Dangling Activities', 'High', 1)])
    ctx = SpecialContext(pid, snapshot_id=sid)
    assert _items(ctx)['overview:attention'].availability(ctx) == 'ready'
    assert _items(ctx)['overview:attention'].availability(SpecialContext(9999)) == 'no_data'


# ── registration ─────────────────────────────────────────────────────────────
def test_both_items_registered_in_catalog(temp_db, xml_path):
    registry.clear_providers()
    pid, sid = _seed(xml_path, [_module('dangling', 'Dangling Activities', 'High', 1)])
    ctx = SpecialContext(pid, snapshot_id=sid)
    ids = {i['id'] for g in registry.catalog(ctx) for i in g['items']}
    assert 'overview:status_header' in ids
    assert 'overview:attention' in ids
