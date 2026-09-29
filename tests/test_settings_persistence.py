"""Owner comment 31 (b) — every settings screen saves, survives re-opening the project and
restarting the app, and is applied to the results.

Each test runs a real server on its own temp data folder (conftest `test_server`); an
"app restart" is a second server started on the same data folder.
"""
import http.client
import json
import threading

import pytest

import db


def _get(port, path):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=20)
    conn.request('GET', path)
    resp = conn.getresponse()
    return resp.status, resp.read()


def _post(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=60)
    conn.request('POST', path, body=json.dumps(payload).encode(),
                 headers={'Content-Type': 'application/json'})
    resp = conn.getresponse()
    return json.loads(resp.read())


def _restart():
    """A second server on the SAME data folder = the app closed and opened again."""
    import server as srv
    httpd = srv.make_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _import(port, path):
    d = _post(port, '/api/parse', {'path': str(path), 'overrides_path': None})
    assert d['ok'] is True, d
    return d


def _reopen(port):
    _, body = _get(port, '/api/history')
    pid = json.loads(body)[0]['project_id']
    d = _post(port, '/api/project/load', {'project_id': pid})
    assert d['ok'] is True, d
    return d


# ── Project Setup: category weights + Actual Cost ──────────────────────────

def test_clean_evm_setup_validates_plainly():
    from server import clean_evm_setup
    assert clean_evm_setup({'Construction': 0.6, 'Engineering': 0.4}, 1250.5) == {
        'weights': {'Construction': 0.6, 'Engineering': 0.4}, 'actual_cost': 1250.5}
    assert clean_evm_setup({}, None) == {'weights': {}, 'actual_cost': None}
    for bad_w, bad_ac, msg in (({'A': 1.5}, None, 'between 0% and 100%'),
                               ({'A': -0.1}, None, 'between 0% and 100%'),
                               ({'A': 'x'}, None, 'not a number'),
                               ({'A': float('nan')}, None, 'not a number'),
                               ({'A': True}, None, 'not a number'),
                               ('oops', None, 'not understood'),
                               ({}, -5, 'cannot be negative'),
                               ({}, 'abc', 'not a number'),
                               ({}, float('inf'), 'not a number')):
        with pytest.raises(ValueError, match=msg):
            clean_evm_setup(bad_w, bad_ac)


def test_evm_setup_survives_reopen_reimport_and_restart(test_server, xml_path):
    d = _import(test_server, xml_path)
    sid = d['snapshot_id']
    cats = list(d['result']['categories'].keys())
    assert cats, 'fixture must yield at least one category'
    weights = {c: round(1.0 / len(cats), 4) for c in cats}

    saved = _post(test_server, '/api/project/evm-setup',
                  {'snapshot_id': sid, 'weights': weights, 'actual_cost': 98765.0})
    assert saved['ok'] is True, saved
    assert saved['evm_setup'] == {'weights': weights, 'actual_cost': 98765.0}

    # re-open the project (DB read path)
    assert _reopen(test_server)['result']['calendar_settings']['evm_setup'] == saved['evm_setup']
    # re-import (the same file / the next update of the same project)
    assert _import(test_server, xml_path)['result']['calendar_settings']['evm_setup'] == saved['evm_setup']
    # restart the app: a fresh server on the same data folder
    httpd = _restart()
    try:
        again = _reopen(httpd.server_address[1])
        assert again['result']['calendar_settings']['evm_setup'] == saved['evm_setup']
    finally:
        httpd.shutdown()


def test_evm_setup_refuses_bad_input_and_keeps_the_saved_one(test_server, xml_path):
    sid = _import(test_server, xml_path)['snapshot_id']
    ok = _post(test_server, '/api/project/evm-setup',
               {'snapshot_id': sid, 'weights': {'Construction': 1.0}, 'actual_cost': 10})
    assert ok['ok'] is True
    bad = _post(test_server, '/api/project/evm-setup',
                {'snapshot_id': sid, 'weights': {'Construction': 2}, 'actual_cost': 10})
    assert bad['ok'] is False and '100%' in bad['error']
    assert _reopen(test_server)['result']['calendar_settings']['evm_setup'] == ok['evm_setup']
    none = _post(test_server, '/api/project/evm-setup', {'weights': {}, 'actual_cost': None})
    assert none == {'ok': False, 'error': 'Open a schedule first.'}


def test_evm_setup_returned_even_when_calendar_audit_fails(test_server, xml_path, monkeypatch):
    sid = _import(test_server, xml_path)['snapshot_id']
    _post(test_server, '/api/project/evm-setup',
          {'snapshot_id': sid, 'weights': {'Construction': 0.5}, 'actual_cost': 1.0})
    import p6_calendar

    def boom(*a, **k):
        raise RuntimeError('calendar audit failed')
    monkeypatch.setattr(p6_calendar, 'calendar_audit', boom)
    d = _import(test_server, xml_path)
    assert d['result']['calendar_audit'] is None
    assert d['result']['calendar_settings']['evm_setup']['actual_cost'] == 1.0


# ── P6 Calendar Audit: shutdown reasons + working-hours notes ──────────────

def test_calendar_reasons_and_notes_merge_row_by_row(test_server, xml_path):
    d = _import(test_server, xml_path)
    base = {'snapshot_id': d['snapshot_id'], 'xml_path': str(xml_path)}
    _post(test_server, '/api/calendar/settings', {**base, 'shutdown_reasons': {'A': 'Eid'}})
    _post(test_server, '/api/calendar/settings', {**base, 'shutdown_reasons': {'B': 'Ramadan'}})
    _post(test_server, '/api/calendar/settings', {**base, 'hours_notes': {'cal1': '10 h Sat'}})
    r = _post(test_server, '/api/calendar/settings', {**base, 'hours_notes': {'cal2': 'night'}})
    assert r['ok'] is True
    # before the fix the second edit wiped the first row's saved reason
    assert r['settings']['shutdown_reasons'] == {'A': 'Eid', 'B': 'Ramadan'}
    assert r['settings']['hours_notes'] == {'cal1': '10 h Sat', 'cal2': 'night'}
    # a blank text clears only that row
    r = _post(test_server, '/api/calendar/settings', {**base, 'shutdown_reasons': {'A': '  '}})
    assert r['settings']['shutdown_reasons'] == {'B': 'Ramadan'}
    httpd = _restart()
    try:
        s = _reopen(httpd.server_address[1])['result']['calendar_settings']
        assert s['shutdown_reasons'] == {'B': 'Ramadan'}
        assert s['hours_notes'] == {'cal1': '10 h Sat', 'cal2': 'night'}
    finally:
        httpd.shutdown()


# ── Bad Weather: location + site type + stop-work limits ───────────────────

def test_weather_settings_saved_offline_survive_restart(test_server, xml_path, monkeypatch):
    """The owner's PC is often offline: the location, site type and edited limits are the
    planner's settings — saved (and reported as saved) even when no estimate could be made,
    and restored after an app restart. No estimate is invented."""
    import p6_calendar.weather as wx

    def offline(lat, lon, data_date, project_finish, today=None, years=5, net=None):
        if net is not None:
            net.update({'offline': True, 'errors': {'forecast': OSError('no network')}})
        return {}, [], None, {}
    monkeypatch.setattr(wx, 'build_daily_weather', offline)
    d = _import(test_server, xml_path)
    thr = {'rain_mm': 7, 'temp_max_c': 41, 'wind_kmh': 30, 'dust': True}
    r = _post(test_server, '/api/weather', {
        'snapshot_id': d['snapshot_id'], 'xml_path': str(xml_path), 'lat': 31.25, 'lon': 32.3,
        'place_name': 'East Port Said', 'thresholds': thr, 'site_type': 'custom'})
    if r.get('error') == 'Schedule has no usable start/finish dates.':
        pytest.skip('fixture has no usable dates for the weather window')
    assert r['ok'] is False and r['settings_saved'] is True and 'weather' not in r
    httpd = _restart()
    try:
        s = _reopen(httpd.server_address[1])['result']['calendar_settings']
        assert s['location'] == {'lat': 31.25, 'lon': 32.3, 'name': 'East Port Said'}
        assert s['site_type'] == 'custom' and s['weather_thresholds'] == thr
        assert 'last_weather' not in s
    finally:
        httpd.shutdown()


# ── Screen preferences (Appearance, Report Contents picks, remembered layouts) ──
# The app window's browser storage is wiped at every launch (private WebView2 + a new random
# port), so ui/prefs_bridge.js mirrors it to <app data>/ui_prefs.json and the server hands
# it back inline at the top of index.html (before the early Appearance script).

def test_ui_prefs_store_saves_removes_and_limits(tmp_path):
    import ui_prefs
    d = str(tmp_path)
    assert ui_prefs.load(d) == {}
    n, skipped = ui_prefs.update(d, {'p6_report_appearance': 'midnight', 'p6evm_w_cols': '[1,2]'})
    assert n == 2 and skipped == []
    n, skipped = ui_prefs.update(d, {'ok': 'v', 'bad': 5, 'x' * 300: 'v',
                                     'big': 'x' * (ui_prefs.MAX_VALUE_LEN + 1)},
                                 ['p6evm_w_cols'])
    assert sorted(skipped) == sorted(['bad', 'x' * 300, 'big'])
    assert ui_prefs.load(d) == {'p6_report_appearance': 'midnight', 'ok': 'v'}
    with pytest.raises(ValueError):
        ui_prefs.update(d, ['not', 'a', 'dict'])


def test_ui_prefs_damaged_file_is_set_aside_not_fatal(tmp_path):
    import ui_prefs
    p = tmp_path / ui_prefs.FILE_NAME
    p.write_text('{not json', encoding='utf-8')
    assert ui_prefs.load(str(tmp_path)) == {}
    assert (tmp_path / (ui_prefs.FILE_NAME + '.bad')).exists()
    ui_prefs.update(str(tmp_path), {'a': '1'})
    assert ui_prefs.load(str(tmp_path)) == {'a': '1'}


def test_ui_prefs_script_json_cannot_close_the_script_tag():
    import ui_prefs
    s = ui_prefs.script_json({'k': '</script><script>alert(1)</script>\u2028'})
    assert '</script' not in s and '\u2028' not in s
    assert json.loads(s) == {'k': '</script><script>alert(1)</script>\u2028'}


def test_ui_prefs_survive_app_restart_and_load_before_appearance(test_server):
    r = _post(test_server, '/api/ui-prefs',
              {'set': {'p6_report_appearance': 'blueprint', 'p6evm_e1_layout': '{"cols":["a"]}'}})
    assert r['ok'] is True and r['skipped'] == []
    assert _post(test_server, '/api/ui-prefs', {'set': 'nope'})['ok'] is False
    httpd = _restart()
    try:
        port = httpd.server_address[1]
        _, body = _get(port, '/api/ui-prefs')
        prefs = json.loads(body)['prefs']
        assert prefs['p6_report_appearance'] == 'blueprint'
        assert prefs['p6evm_e1_layout'] == '{"cols":["a"]}'
        status, html = _get(port, '/')
        html = html.decode('utf-8')
        assert status == 200
        i_prefs = html.index('window.__UI_PREFS__=')
        i_bridge = html.index('/api/ui-prefs')           # the inlined bridge
        i_appearance = html.index("localStorage.getItem('p6_report_appearance')")
        i_app = html.index('src="/ui/app.js"')
        assert i_prefs < i_bridge < i_appearance < i_app
        assert '"p6_report_appearance":"blueprint"' in html
    finally:
        httpd.shutdown()


def test_ui_prefs_unreadable_store_never_blocks_the_page(test_server, monkeypatch):
    import ui_prefs
    monkeypatch.setattr(ui_prefs, 'load', lambda d: (_ for _ in ()).throw(OSError('locked')))
    status, html = _get(test_server, '/')
    assert status == 200 and b'window.__UI_PREFS__={}' in html


# ── AI Chat: the chosen offline AI brain ────────────────────────────────────

def _llm(tmp_path, monkeypatch):
    from p6_chat import llm
    monkeypatch.setattr(llm, 'app_data_dir', lambda: str(tmp_path))
    return llm


def test_ai_brain_choice_saved_survives_restart_and_is_applied(tmp_path, monkeypatch):
    llm = _llm(tmp_path, monkeypatch)
    (tmp_path / 'chat_brain.json').write_text('{"model_key": "detailed", "other": 1}', encoding='utf-8')
    s = llm.save_settings(model='fast')
    assert s['saved'] is True and s['model_key'] == 'fast'
    on_disk = json.loads((tmp_path / 'chat_brain.json').read_text(encoding='utf-8'))
    assert on_disk == {'model_key': 'fast', 'other': 1}          # other keys kept
    assert not (tmp_path / 'chat_brain.json.tmp').exists()      # atomic swap, nothing left over
    # "restart": nothing is held in memory — the choice is read back from the file
    assert llm.get_model_key() == 'fast'
    st = llm.status()
    assert st['model_key'] == 'fast' and st['model_name'] == llm.MODELS['fast']['label']
    # applied: answers load the chosen brain's model file
    assert llm._model_path().endswith(llm.MODELS['fast']['file'])


def test_ai_brain_choice_not_kept_is_reported_and_old_choice_stays(tmp_path, monkeypatch):
    llm = _llm(tmp_path, monkeypatch)
    assert llm.save_settings(model='detailed')['saved'] is True

    def locked(*a, **k):
        raise PermissionError('read-only folder')
    monkeypatch.setattr(llm.os, 'replace', locked)
    s = llm.save_settings(model='fast')
    assert s['saved'] is False and 'could not be saved' in s['error']
    assert s['model_key'] == 'detailed' and llm.get_model_key() == 'detailed'
    assert not (tmp_path / 'chat_brain.json.tmp').exists()
    bad = llm.save_settings(model='no-such-brain')
    assert bad['saved'] is False and bad['model_key'] == 'detailed'
    assert llm.save_settings()['model_key'] == 'detailed' and 'saved' not in llm.save_settings()


def test_ai_brain_choice_via_the_app_survives_restart(test_server, tmp_path, monkeypatch):
    _llm(tmp_path, monkeypatch)
    d = _post(test_server, '/api/chat/settings', {'model': 'fast'})
    assert d['ok'] is True and d['settings']['saved'] is True and d['brain']['model_key'] == 'fast'
    httpd = _restart()
    try:
        _, body = _get(httpd.server_address[1], '/api/chat/status')
        assert json.loads(body)['brain']['model_key'] == 'fast'
    finally:
        httpd.shutdown()


# ── Schedule Health: contract milestones (gate B) ───────────────────────────

def _hard(result):
    return ((result.get('audit_modules') or {}).get('modules') or {}).get('hard_constraints')


def test_contract_milestones_prefill_survive_reopen_reimport_restart(test_server, xml_path):
    d = _import(test_server, xml_path)
    if _hard(d['result']) is None:
        pytest.skip('fixture yields no Milestone Check module')
    sid = d['snapshot_id']
    rows = [{'name': 'Mechanical Completion', 'date': '2027-06-30'},
            {'name': 'Handover', 'date': '2027-09-30'},
            {'name': '', 'date': ''},                            # a blank row never wipes the list
            'junk']
    r = _post(test_server, '/api/milestones/save', {'snapshot_id': sid, 'milestones': rows})
    want = rows[:2]
    assert r['ok'] is True and r['saved'] is True and r['milestones'] == want
    mod = r['milestone_module']
    assert mod is not None and mod['needs_input'] is False
    # "Edit contract milestones" pre-fills from the module the screen now holds
    assert mod['contract_milestones'] == want
    assert [e['contract_name'] for e in mod['milestones']] == ['Mechanical Completion', 'Handover']

    # re-open: pre-filled from the saved list
    hard = _hard(_reopen(test_server)['result'])
    assert hard['contract_milestones'] == want

    # re-import the same schedule: evaluated against the saved list at once (applied)
    hard = _hard(_import(test_server, xml_path)['result'])
    assert hard['contract_milestones'] == want and hard['needs_input'] is False
    assert len(hard['milestones']) == 2

    # app restart (a second server on the same data folder)
    httpd = _restart()
    try:
        hard = _hard(_reopen(httpd.server_address[1])['result'])
        assert hard['contract_milestones'] == want
    finally:
        httpd.shutdown()


def test_contract_milestones_save_reports_db_busy_and_unchecked(test_server, xml_path, monkeypatch):
    d = _import(test_server, xml_path)
    sid = d['snapshot_id']
    good = [{'name': 'Handover', 'date': '2027-09-30'}]
    assert _post(test_server, '/api/milestones/save', {'snapshot_id': sid, 'milestones': good})['ok']

    def busy(*a, **k):
        raise RuntimeError('database is locked')
    real_save = db.save_contract_milestones
    monkeypatch.setattr(db, 'save_contract_milestones', busy)
    r = _post(test_server, '/api/milestones/save',
              {'snapshot_id': sid, 'milestones': [{'name': 'X', 'date': '2027-01-01'}]})
    assert r['ok'] is False and 'could not be saved' in r['error']
    monkeypatch.setattr(db, 'save_contract_milestones', real_save)
    pid = db.get_project_id_for_snapshot(sid)
    assert db.get_contract_milestones(pid) == good                # the old list is kept

    # saved, but the schedule file is gone -> saved + a plain reason (not "please retry")
    monkeypatch.setattr(db, 'get_snapshot_xml_path', lambda s: None)
    r = _post(test_server, '/api/milestones/save', {'snapshot_id': sid, 'milestones': good})
    assert r['ok'] is True and r['saved'] is True and r['milestone_module'] is None
    assert 'could not be found' in r['error']


# ── Lag & Lead justifications ───────────────────────────────────────────────

def test_lag_justification_survives_reopen_and_restart(test_server, tmp_path):
    from tests.test_server import _UPDATE_XML        # carries A050 --FS lag--> A100
    p = tmp_path / 'lag.xml'
    p.write_text(_UPDATE_XML, encoding='utf-8')
    d = _import(test_server, p)
    key = d['result']['audit_modules']['modules']['lag_lead']['findings'][0]['rel_key']
    r = _post(test_server, '/api/lag/justification',
              {'snapshot_id': d['snapshot_id'], 'rel_key': key, 'text': 'Cure 28 days per MS-07'})
    assert r['ok'] is True

    def reason(result):
        lag = result['audit_modules']['modules']['lag_lead']
        return {f['rel_key']: f['justification'] for f in lag['findings']}[key]

    assert reason(_reopen(test_server)['result']) == 'Cure 28 days per MS-07'
    httpd = _restart()
    try:
        assert reason(_reopen(httpd.server_address[1])['result']) == 'Cure 28 days per MS-07'
    finally:
        httpd.shutdown()
