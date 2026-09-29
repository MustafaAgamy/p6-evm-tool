"""Startup reliability — the "sometimes it opens on a black screen" fixes.

Covers the server half of the readiness handshake (GET /api/health, POST /api/client-log),
the static-file handler answering 503 instead of dropping the connection on a transient
OSError, the startup guard being inlined into index.html, the [::1] twin listener and the
listen backlog, the DB-open resilience (a corrupt file is set aside and a fresh DB created;
a locked DB is never quarantined), and app_startup's watchdog / safe-graphics / launch
bookkeeping. No browser needed (the Playwright check lives outside the unit suite).
"""
import http.client
import json
import os
import socket
import sqlite3
import threading
import time

import pytest

import app_startup
import db


@pytest.fixture(autouse=True)
def _isolated_startup(tmp_path, monkeypatch):
    """app_startup writes its log/flags under the per-user data folder: point it at tmp."""
    monkeypatch.setattr(app_startup, 'data_dir', lambda: str(tmp_path))
    monkeypatch.delenv(app_startup.SAFE_GRAPHICS_ENV, raising=False)
    app_startup.enable_file_log()
    app_startup.READY.clear()
    app_startup.STATE.update(ready_after_s=None, graphics='normal', watchdog=None)
    with app_startup._LAUNCH_LOCK:
        app_startup._LAUNCH.clear()
    yield
    app_startup._FILE_LOG = False        # plain assignment: a monkeypatch undo would run
    app_startup.reset_logger()           # later and switch the file log back on
    app_startup.READY.clear()


def test_no_log_file_unless_the_app_enables_it(tmp_path, monkeypatch):
    app_startup._FILE_LOG = False
    app_startup.reset_logger()
    app_startup.log('from a test / the CLI')
    assert not (tmp_path / 'logs').exists()


def _get(port, path, host='127.0.0.1'):
    conn = http.client.HTTPConnection(host, port, timeout=10)
    conn.request('GET', path)
    resp = conn.getresponse()
    return resp.status, dict(resp.getheaders()), resp.read()


def _post(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    conn.request('POST', path, body=json.dumps(payload).encode(),
                 headers={'Content-Type': 'application/json'})
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read())


# ── GET /api/health + the readiness handshake ─────────────────────────────

def test_health_route_reports_server_db_and_handshake(test_server):
    status, headers, body = _get(test_server, '/api/health')
    assert status == 200
    data = json.loads(body)
    from utils import APP_NAME, APP_VERSION
    assert data['ok'] is True and data['app'] == APP_NAME and data['version'] == APP_VERSION
    assert data['db']['status'] == 'ok'
    assert data['ready'] is False and data['graphics'] in ('normal', 'safe')
    # the query string is tolerated (cache-busting probes)
    assert _get(test_server, '/api/health?t=1')[0] == 200


def test_client_log_ready_completes_the_handshake(test_server, tmp_path):
    assert not app_startup.READY.is_set()
    status, data = _post(test_server, '/api/client-log',
                         {'kind': 'ready', 'message': 'shell ready', 'attempt': 1, 'ms': 812})
    assert status == 200 and data == {'ok': True, 'kind': 'ready'}
    assert app_startup.READY.is_set()
    assert json.loads(_get(test_server, '/api/health')[2])['ready'] is True
    log = (tmp_path / 'logs' / 'startup.log').read_text(encoding='utf-8')
    assert 'page ready: shell ready' in log


def test_client_log_records_failures_and_rejects_unknown_kinds(test_server, tmp_path):
    _post(test_server, '/api/client-log',
          {'kind': 'load-failed', 'detail': 'Could not load http://localhost/ui/modules/x.js'})
    status, data = _post(test_server, '/api/client-log', {'kind': 'drop tables', 'message': 'x' * 5000})
    assert status == 200 and data['kind'] == 'info'
    log = (tmp_path / 'logs' / 'startup.log').read_text(encoding='utf-8')
    assert 'page load-failed' in log and 'x.js' in log
    assert 'x' * 700 not in log                        # messages are clipped
    assert not app_startup.READY.is_set()


# ── index.html: the startup guard is inlined, the port still injected ─────

def test_index_inlines_the_startup_guard_before_the_modules(test_server):
    status, headers, body = _get(test_server, '/')
    html = body.decode('utf-8')
    assert status == 200 and 'charset=utf-8' in headers['Content-Type']
    assert int(headers['Content-Length']) == len(body)
    assert '<!--cx:startup-guard-->' not in html          # the marker was replaced
    assert html.count('<script') == html.count('</script>')
    guard = html.index('__cxStartup')
    assert guard < html.index('<script type="module" src="/ui/app.js">')
    assert html.index('window.__SERVER_PORT__') < html.index('<script type="module" src="/ui/app.js">')
    assert 'Starting' in html                             # the cover is never a blank box


def test_inline_guard_falls_back_to_a_script_tag(monkeypatch):
    import server
    def boom(*a, **k):
        raise PermissionError(13, 'being used by another process')
    monkeypatch.setattr(server, '_read_ui_file', boom)
    out = server._inline_startup_guard('<head><!--cx:startup-guard--></head>')
    assert out == '<head><script src="/ui/startup_guard.js"></script></head>'
    out = server._inline_startup_guard('<head></head>')           # no marker: before </head>
    assert out == '<head><script src="/ui/startup_guard.js"></script></head>'


# ── static files: transient OSError -> retried, then 503 (never a dropped socket) ──

def test_static_file_transient_lock_is_retried(test_server, monkeypatch):
    import builtins
    import server
    real_open = builtins.open
    calls = {'n': 0}

    def flaky_open(path, *a, **k):
        if str(path).replace('\\', '/').endswith('ui/modules/format.js') and calls['n'] < 2:
            calls['n'] += 1
            raise PermissionError(13, 'The process cannot access the file because it is being used by another process')
        return real_open(path, *a, **k)
    monkeypatch.setattr(builtins, 'open', flaky_open)
    status, headers, body = _get(test_server, '/ui/modules/format.js')
    assert status == 200 and calls['n'] == 2
    assert headers['Content-Type'] == 'application/javascript'
    assert int(headers['Content-Length']) == len(body) and headers['Cache-Control'] == 'no-cache'


def test_static_file_persistent_lock_answers_503(test_server, monkeypatch):
    import server
    def locked(path, *a, **k):
        raise PermissionError(13, 'being used by another process')
    monkeypatch.setattr(server, '_read_ui_file', locked)
    status, headers, body = _get(test_server, '/ui/modules/format.js')
    assert status == 503 and headers.get('Retry-After') == '1'
    assert json.loads(body)['ok'] is False
    status, headers, body = _get(test_server, '/')
    assert status == 503


def test_locked_index_answers_a_self_retrying_starting_page(test_server, monkeypatch):
    """[startup:F1] BLACK-2: when index.html itself is locked (antivirus scanning the freshly
    unpacked exe files) the window used to show raw JSON on white and sat there until the
    45 s watchdog. It now gets a visible 'Starting' page that reloads itself with backoff
    and ends on an in-page Retry button (never alert/confirm - WebView2 no-ops)."""
    import server
    from utils import APP_NAME

    def locked(path, *a, **k):
        raise PermissionError(13, 'being used by another process')
    monkeypatch.setattr(server, '_read_ui_file', locked)
    status, headers, body = _get(test_server, '/')
    html = body.decode('utf-8')
    assert status == 503 and headers.get('Retry-After') == '1'
    assert headers['Content-Type'] == 'text/html; charset=utf-8'
    assert int(headers['Content-Length']) == len(body)
    assert '<meta charset="utf-8">' in html and 'background:#06090f' in html
    assert 'Starting ' + APP_NAME in html and 'id="cx-index-retry"' in html
    assert 'location.reload' in html and 'sessionStorage' in html
    for banned in ('alert(', 'confirm(', 'prompt('):
        assert banned not in html


def test_static_query_string_keeps_the_js_mime_type(test_server):
    status, headers, _ = _get(test_server, '/ui/app.js?v=2.8.0')
    assert status == 200 and headers['Content-Type'] == 'application/javascript'


# ── loopback: [::1] twin on the same port + a real backlog ────────────────

def test_server_answers_on_ipv6_loopback_too(test_server):
    if not socket.has_ipv6:
        pytest.skip('no IPv6 on this machine')
    try:
        s = socket.create_connection(('::1', test_server), timeout=2)
        s.close()
    except OSError:
        pytest.skip('::1 loopback not available here')
    status, _, body = _get(test_server, '/api/health', host='::1')
    assert status == 200 and json.loads(body)['ok'] is True


def test_listen_backlog_is_not_the_socketserver_default():
    import server
    assert server._LoopbackServer.request_queue_size >= 128
    srv = server._bind_loopback()
    try:
        assert srv.server_address[0] == '127.0.0.1'
        if srv.companion is not None:
            assert srv.companion.server_address[1] == srv.server_address[1]
    finally:
        srv.server_close()


def _burst_connect(host, port, n=40, timeout=5.0):
    """Open ``n`` connections at once to a listener that is NOT accepting (the moment the
    UI asks for ~40 files while the server thread is busy). Returns (connected, refused)."""
    fam = socket.AF_INET6 if ':' in host else socket.AF_INET
    socks, refused, lock = [], [], threading.Lock()

    def one():
        s = socket.socket(fam, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            with lock:
                socks.append(s)
        except OSError as exc:
            s.close()
            with lock:
                refused.append(exc)
    threads = [threading.Thread(target=one) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout + 2)
    for s in socks:
        s.close()
    return len(socks), refused


def test_a_burst_of_40_connections_is_queued_not_refused():
    """[startup:F3] BLACK-5, behaviour not just the attribute: with nobody accepting, the
    bound listeners (127.0.0.1 and the [::1] twin) queue a 40-request burst. socketserver's
    default backlog of 5 refused 35 of them on Windows (a refused module = black screen) —
    the control socket below proves this machine really refuses past a small backlog."""
    import server
    ctl = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ctl.bind(('127.0.0.1', 0))
    ctl.listen(5)                                     # the old default, as a control
    try:
        ok_small, _ = _burst_connect('127.0.0.1', ctl.getsockname()[1], timeout=3.0)
    finally:
        ctl.close()
    srv = server._bind_loopback()                     # bound + listening, never accepting
    try:
        port = srv.server_address[1]
        ok, refused = _burst_connect('127.0.0.1', port)
        assert ok == 40 and not refused, (ok, refused[:3])
        if srv.companion is not None:
            ok6, refused6 = _burst_connect('::1', port)
            assert ok6 == 40 and not refused6, (ok6, refused6[:3])
    finally:
        srv.server_close()
    if ok_small >= 40:
        pytest.skip('this OS queues past a backlog of 5 anyway (control not refused)')


def test_bind_loopback_skips_a_port_whose_ipv6_twin_is_taken(monkeypatch):
    import server
    if not socket.has_ipv6:
        pytest.skip('no IPv6')
    real = server._LoopbackServer6
    tries = {'n': 0}

    class Taken(real):
        def __init__(self, *a, **k):
            tries['n'] += 1
            if tries['n'] == 1:
                raise OSError(10048, 'address in use')
            super().__init__(*a, **k)
    monkeypatch.setattr(server, '_LoopbackServer6', Taken)
    try:
        srv = server._bind_loopback()
    except OSError:
        pytest.skip('::1 not bindable here')
    try:
        assert tries['n'] >= 2 and srv.companion is not None
    finally:
        srv.server_close()


def test_shutdown_stops_both_listeners(tmp_path, monkeypatch):
    import server
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    srv = server.make_server()
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    assert _get(srv.server_address[1], '/api/health')[0] == 200
    done = threading.Event()
    threading.Thread(target=lambda: (srv.shutdown(), done.set()), daemon=True).start()
    assert done.wait(5), 'shutdown() hung'
    srv.server_close()


# ── DB-open resilience ────────────────────────────────────────────────────

def _db_file(tmp_path):
    return tmp_path / 'controlyx.db'


def test_corrupt_db_is_set_aside_and_a_fresh_one_created(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    _db_file(tmp_path).write_bytes(b'this is not a sqlite database at all' * 200)
    st = db.open_db_resilient()
    assert st['status'] == 'recovered' and st['backup'].startswith('controlyx.db.corrupt-bak-')
    assert (tmp_path / st['backup']).read_bytes().startswith(b'this is not a sqlite')
    assert db.get_recent_projects() == []                 # the fresh DB works
    assert db.DB_STATUS['status'] == 'recovered'


def test_malformed_pages_are_recovered_too(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    db.init_db()
    with db.get_conn() as conn:
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    raw = bytearray(_db_file(tmp_path).read_bytes())
    for i in range(4096, min(len(raw), 4096 * 6)):       # smash the schema/table pages
        raw[i] = 0xA5
    _db_file(tmp_path).write_bytes(bytes(raw))
    st = db.open_db_resilient()
    assert st['status'] in ('recovered', 'ok')            # 'ok' only if SQLite never read them
    if st['status'] == 'recovered':
        assert db.get_recent_projects() == []


def test_locked_db_is_never_quarantined(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    db.init_db()

    def locked():
        raise sqlite3.OperationalError('database is locked')
    monkeypatch.setattr(db, 'init_db', locked)
    st = db.open_db_resilient()
    assert st['status'] == 'degraded' and 'locked' in st['detail'] and st['backup'] is None
    assert _db_file(tmp_path).exists()
    assert not [p for p in os.listdir(tmp_path) if 'corrupt-bak' in p]


def test_unexpected_error_is_degraded_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    monkeypatch.setattr(db, 'init_db', lambda: (_ for _ in ()).throw(PermissionError('denied')))
    st = db.open_db_resilient()
    assert st['status'] == 'degraded' and 'PermissionError' in st['detail']


def test_make_server_starts_on_a_corrupt_db_and_health_says_so(tmp_path, monkeypatch):
    import server
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    monkeypatch.setattr(db, 'schedules_dir', lambda: str(tmp_path / 'schedules'))
    _db_file(tmp_path).write_bytes(b'\x00garbage' * 1000)
    srv = server.make_server()                            # used to raise DatabaseError
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        data = json.loads(_get(srv.server_address[1], '/api/health')[2])
        assert data['db']['status'] == 'recovered' and data['db']['backup']
        status, _, body = _get(srv.server_address[1], '/api/history')
        assert status == 200 and json.loads(body) == []
    finally:
        srv.shutdown()
        srv.server_close()


def test_history_failure_answers_503_instead_of_dropping(test_server, monkeypatch):
    def broken(limit=10):
        raise sqlite3.DatabaseError('database disk image is malformed')
    monkeypatch.setattr(db, 'get_recent_projects', broken)
    status, _, body = _get(test_server, '/api/history')
    assert status == 503 and 'malformed' in json.loads(body)['error']


# ── app_startup: watchdog, safe graphics, launch bookkeeping, single instance ──

class _FakeWindow:
    def __init__(self, on_load=None):
        self.loads = []
        self.on_load = on_load

    def load_url(self, url):
        self.loads.append(url)
        if self.on_load:
            self.on_load()


def test_watchdog_does_nothing_when_the_page_is_ready():
    ev = threading.Event()
    ev.set()
    w = _FakeWindow()
    assert app_startup.watch_startup(w, 'http://localhost:1/', ready=ev, first_s=1, second_s=1) == 'ready'
    assert w.loads == []


def test_watchdog_reloads_once_then_recovers():
    ev = threading.Event()
    w = _FakeWindow(on_load=ev.set)
    assert app_startup.watch_startup(w, 'http://localhost:1/', ready=ev,
                                     first_s=0.05, second_s=1) == 'ready-after-reload'
    assert w.loads == ['http://localhost:1/']
    assert not app_startup.safe_graphics_enabled()


def test_watchdog_failure_turns_on_safe_graphics_for_next_launch(tmp_path):
    app_startup.begin_launch()
    w = _FakeWindow()
    assert app_startup.watch_startup(w, 'u', ready=threading.Event(), first_s=0.01, second_s=0.01) == 'failed'
    assert w.loads == ['u'] and app_startup.safe_graphics_enabled()
    state = json.loads((tmp_path / 'launch_state.json').read_text(encoding='utf-8'))
    assert state['watchdog'] == 'failed'
    env = {}
    assert app_startup.apply_graphics_mode(env) == 'safe'
    args = env['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS']
    assert '--disable-gpu' in args and app_startup.PYWEBVIEW_ARGS in args


def test_watchdog_stops_quietly_when_the_window_closes():
    closed = threading.Event()
    w = _FakeWindow()
    threading.Timer(0.1, closed.set).start()
    t = time.monotonic()
    assert app_startup.watch_startup(w, 'u', ready=threading.Event(), first_s=30, second_s=30,
                                     closed=closed) == 'closed'
    assert time.monotonic() - t < 5 and w.loads == []
    assert not app_startup.safe_graphics_enabled()


def test_graphics_normal_by_default_and_env_override(monkeypatch):
    env = {}
    assert app_startup.apply_graphics_mode(env) == 'normal' and env == {}
    monkeypatch.setenv(app_startup.SAFE_GRAPHICS_ENV, '1')
    assert app_startup.apply_graphics_mode(env) == 'safe'
    app_startup.enable_safe_graphics('test')
    monkeypatch.setenv(app_startup.SAFE_GRAPHICS_ENV, '0')
    env = {}
    assert app_startup.apply_graphics_mode(env) == 'normal' and env == {}


def test_help_safe_graphics_switch_round_trip(test_server, tmp_path, monkeypatch):
    """[startup:F3] BLACK-6: Help ▸ Contact & Support 'Safe graphics' — the saved choice is
    read by the NEXT launch (apply_graphics_mode), and turning it off is the way back to
    normal graphics after the app switched it on by itself."""
    monkeypatch.delenv(app_startup.RELAUNCH_ENV, raising=False)
    status, _, body = _get(test_server, '/api/graphics-mode')
    st = json.loads(body)
    assert status == 200 and st['ok'] and st['saved'] is False
    assert st['this_launch'] == 'normal' and st['forced'] is None

    status, st = _post(test_server, '/api/graphics-mode', {'safe': True})
    assert status == 200 and st['saved'] is True and st['reason'] == 'turned on in Help'
    assert st['since']
    env = {}
    assert app_startup.apply_graphics_mode(env) == 'safe'           # the next launch
    assert '--disable-gpu' in env['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS']
    assert '--disable-features=ElasticOverscroll' in env['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS']
    assert st['this_launch'] == 'normal'          # this window keeps the mode it started in

    status, st = _post(test_server, '/api/graphics-mode', {'safe': False})
    assert status == 200 and st['saved'] is False and st['reason'] is None
    assert not (tmp_path / 'safe_graphics.json').exists()
    env = {}
    assert app_startup.apply_graphics_mode(env) == 'normal' and env == {}
    log = (tmp_path / 'logs' / 'startup.log').read_text(encoding='utf-8')
    assert 'switched ON' in log and 'switched OFF' in log and 'turned off in Help' in log


def test_help_safe_graphics_switch_bad_request_and_unwritable_folder(test_server, monkeypatch):
    for bad in ({}, {'safe': 'yes'}, {'safe': 1}):
        status, st = _post(test_server, '/api/graphics-mode', bad)
        assert status == 400 and st['ok'] is False
    monkeypatch.setattr(app_startup, '_write_json', lambda path, obj: False)
    status, st = _post(test_server, '/api/graphics-mode', {'safe': True})
    assert status == 500 and st['ok'] is False and st['saved'] is False
    assert 'could not be saved' in st['error']


def test_turning_safe_graphics_off_with_a_locked_flag_file(tmp_path, monkeypatch):
    app_startup.enable_safe_graphics('auto')
    real_remove = os.remove

    def locked(path, *a, **k):
        if str(path).endswith('safe_graphics.json'):
            raise PermissionError(32, 'being used by another process')
        return real_remove(path, *a, **k)
    monkeypatch.setattr(app_startup.os, 'remove', locked)
    assert app_startup.disable_safe_graphics('turned off in Help') is True
    assert not app_startup.safe_graphics_enabled()                  # enabled=False written
    assert app_startup.graphics_status()['saved'] is False


def test_graphics_status_reports_a_user_override_but_not_a_relaunch(monkeypatch):
    monkeypatch.delenv(app_startup.RELAUNCH_ENV, raising=False)
    monkeypatch.setenv(app_startup.SAFE_GRAPHICS_ENV, '0')
    assert app_startup.graphics_status()['forced'] == '0'
    monkeypatch.setenv(app_startup.SAFE_GRAPHICS_ENV, '1')
    monkeypatch.setenv(app_startup.RELAUNCH_ENV, '1')        # set by the automatic relaunch
    assert app_startup.graphics_status()['forced'] is None


def test_closing_a_never_ready_window_is_remembered(tmp_path):
    app_startup.begin_launch()
    app_startup.T0 = time.monotonic() - 20                # the user sat on it for 20 s
    try:
        app_startup.end_launch()
    finally:
        app_startup.T0 = time.monotonic()
    prev = json.loads((tmp_path / 'launch_state.json').read_text(encoding='utf-8'))
    assert prev['ready'] is False and prev['closed_after_s'] >= 8
    assert app_startup.previous_launch_failed(prev)
    app_startup.begin_launch()                            # next launch: safe graphics
    assert app_startup.safe_graphics_enabled()


def test_a_normal_launch_leaves_graphics_alone(tmp_path):
    app_startup.begin_launch()
    app_startup.mark_ready()
    app_startup.end_launch()
    prev = json.loads((tmp_path / 'launch_state.json').read_text(encoding='utf-8'))
    assert prev['ready'] is True and not app_startup.previous_launch_failed(prev)
    app_startup.begin_launch()
    assert not app_startup.safe_graphics_enabled()
    # a quick close before ready (e.g. double-click then close) is not evidence either
    assert not app_startup.previous_launch_failed({'ready': False, 'closed_after_s': 2})
    assert not app_startup.previous_launch_failed(None)


@pytest.mark.skipif(os.name != 'nt', reason='named mutex is Windows-only')
def test_single_instance_never_blocks_without_a_usable_window():
    name = 'Local\\cx-test-%d-%d' % (os.getpid(), int(time.time() * 1000))
    title = 'cx-no-such-window-%d' % os.getpid()
    assert app_startup.single_instance(name, title, wait_s=0) is True     # first owner
    t = time.monotonic()
    assert app_startup.single_instance(name, title, wait_s=0.3, poll_s=0.05) is True
    assert time.monotonic() - t >= 0.25                   # it looked for the window first


@pytest.mark.skipif(os.name != 'nt', reason='Win32 windows')
def test_single_instance_defers_only_to_a_working_copy(tmp_path, monkeypatch):
    name = 'Local\cx-test2-%d-%d' % (os.getpid(), int(time.time() * 1000))
    assert app_startup.single_instance(name, 't', wait_s=0) is True
    focused = []
    monkeypatch.setattr(app_startup, '_find_window', lambda title: 4242)
    monkeypatch.setattr(app_startup, '_window_pid', lambda hwnd: 777)
    monkeypatch.setattr(app_startup, '_focus_window', lambda hwnd: focused.append(hwnd) or True)
    state = tmp_path / 'launch_state.json'
    # the running copy never became ready (black window): open a new one instead
    state.write_text(json.dumps({'pid': 777, 'ready': False}), encoding='utf-8')
    assert app_startup.single_instance(name, 't', wait_s=0.2, poll_s=0.05) is True
    assert focused == []
    # a working copy: bring it to the front and exit
    state.write_text(json.dumps({'pid': 777, 'ready': True}), encoding='utf-8')
    assert app_startup.single_instance(name, 't', wait_s=0.2, poll_s=0.05) is False
    assert focused == [4242]
    # a stale record from another process never counts as ready
    state.write_text(json.dumps({'pid': 1, 'ready': True}), encoding='utf-8')
    assert app_startup.single_instance(name, 't', wait_s=0.1, poll_s=0.05) is True


def test_attach_library_loggers_routes_pywebview_errors(tmp_path):
    import logging
    app_startup.attach_library_loggers(('pywebview-test',))
    logging.getLogger('pywebview-test').error('WebView2 initialization failed with exception: X')
    for h in app_startup.get_logger().handlers:
        h.flush()
    assert 'WebView2 initialization failed' in (tmp_path / 'logs' / 'startup.log').read_text(encoding='utf-8')
    for h in app_startup.get_logger().handlers:
        logging.getLogger('pywebview-test').removeHandler(h)


# ── [startup:F1] BLACK-3: WebView2 never shows the page -> relaunch once in safe graphics ──

def test_any_page_message_counts_as_page_contact():
    app_startup.PAGE_CONTACT.clear()
    app_startup.client_log({'kind': 'booted'})
    assert app_startup.PAGE_CONTACT.is_set()
    app_startup.PAGE_CONTACT.clear()


def test_pywebview_init_failure_is_detected_from_its_log(tmp_path):
    import logging
    app_startup.WEBVIEW_INIT_FAILED.clear()
    app_startup.attach_library_loggers(('pywebview-test2',))
    lg = logging.getLogger('pywebview-test2')
    try:
        lg.error('some other pywebview error')
        assert not app_startup.WEBVIEW_INIT_FAILED.is_set()
        lg.error('WebView2 initialization failed with exception:\n System.Exception: 0x8007139F')
        assert app_startup.WEBVIEW_INIT_FAILED.is_set()
    finally:
        for h in list(lg.handlers):
            lg.removeHandler(h)
        app_startup.WEBVIEW_INIT_FAILED.clear()


def test_watchdog_gives_up_at_once_when_webview2_failed_to_start(tmp_path):
    app_startup.begin_launch()
    failed = threading.Event()
    failed.set()
    w = _FakeWindow()
    t = time.monotonic()
    assert app_startup.watch_startup(w, 'u', ready=threading.Event(), first_s=30, second_s=30,
                                     abort=failed, contact=threading.Event()) == 'failed'
    assert time.monotonic() - t < 3
    assert w.loads == []                                # no point reloading a dead WebView
    assert app_startup.safe_graphics_enabled()
    assert app_startup.STATE['page_contact'] is False


def test_watchdog_reloads_early_when_the_page_never_made_contact():
    ev = threading.Event()
    w = _FakeWindow(on_load=ev.set)
    t = time.monotonic()
    assert app_startup.watch_startup(w, 'u', ready=ev, first_s=30, second_s=1, no_contact_s=0.1,
                                     contact=threading.Event()) == 'ready-after-reload'
    assert time.monotonic() - t < 3 and w.loads == ['u']


def test_watchdog_reports_a_running_page_so_app_py_does_not_relaunch(tmp_path):
    """The page is alive (its own Retry card is on screen) but never ready: the watchdog
    still reloads once and records the failure, but reports page_contact=True, so app.py
    does not relaunch over the page's own card. A running page keeps the full first_s."""
    app_startup.begin_launch()
    contact = threading.Event()
    contact.set()
    w = _FakeWindow()
    t = time.monotonic()
    assert app_startup.watch_startup(w, 'u', ready=threading.Event(), first_s=0.6,
                                     second_s=0.05, no_contact_s=0.01, contact=contact) == 'failed'
    assert time.monotonic() - t >= 0.55
    assert w.loads == ['u'] and app_startup.STATE['page_contact'] is True


def test_relaunch_in_safe_graphics_once_with_a_clean_environment(tmp_path):
    app_startup.begin_launch()
    calls = []

    def fake_popen(cmd, **kw):
        calls.append((cmd, kw))
    env = {'PATH': 'x', '_PYI_APPLICATION_HOME_DIR': r'C:\T\_MEI1', '_MEIPASS2': r'C:\T\_MEI1',
           '_PYI_PARENT_PROCESS_LEVEL': '1'}
    assert app_startup.relaunch_safe_graphics('never showed the page', popen=fake_popen, env=env)
    (cmd, kw), = calls
    child = kw['env']
    assert child[app_startup.RELAUNCH_ENV] == '1' and child[app_startup.SAFE_GRAPHICS_ENV] == '1'
    assert child['PYINSTALLER_RESET_ENVIRONMENT'] == '1' and child['PATH'] == 'x'
    assert not [k for k in child if k.startswith('_PYI_') or k == '_MEIPASS2']
    assert cmd == app_startup.relaunch_command()
    assert app_startup.safe_graphics_enabled()
    state = json.loads((tmp_path / 'launch_state.json').read_text(encoding='utf-8'))
    assert state['watchdog'] == 'failed' and state['relaunched'] is True
    # this copy hands over: closing its window must not overwrite the new copy's record
    (tmp_path / 'launch_state.json').write_text(json.dumps({'pid': 99, 'ready': True}), encoding='utf-8')
    app_startup.end_launch()
    assert json.loads((tmp_path / 'launch_state.json').read_text(encoding='utf-8')) == {'pid': 99, 'ready': True}
    # a relaunched copy never relaunches again (no loop)
    assert app_startup.relaunch_safe_graphics('again', popen=fake_popen, env=child) is False
    assert len(calls) == 1


def test_relaunch_command_frozen_and_dev(monkeypatch):
    import sys
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'argv', [r'C:\A\Controlyx.exe'])
    monkeypatch.setattr(sys, 'executable', r'C:\A\Controlyx.exe')
    assert app_startup.relaunch_command() == [r'C:\A\Controlyx.exe']
    monkeypatch.setattr(sys, 'frozen', False)
    monkeypatch.setattr(sys, 'argv', ['app.py'])
    cmd = app_startup.relaunch_command()
    assert cmd[0] == sys.executable and cmd[1].endswith('app.py') and os.path.isabs(cmd[1])


@pytest.mark.skipif(os.name != 'nt', reason='named mutex is Windows-only')
def test_a_relaunched_copy_does_not_wait_on_the_copy_it_replaces(monkeypatch):
    name = r'Local\cx-test3-%d-%d' % (os.getpid(), int(time.time() * 1000))
    assert app_startup.single_instance(name, 't', wait_s=0) is True
    monkeypatch.setenv(app_startup.RELAUNCH_ENV, '1')
    t = time.monotonic()
    assert app_startup.single_instance(name, 'cx-no-window', wait_s=5, poll_s=0.05) is True
    assert time.monotonic() - t < 1


def test_app_py_relaunches_only_when_the_page_never_made_contact():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.py'),
               encoding='utf-8').read()
    assert 'abort=app_startup.WEBVIEW_INIT_FAILED' in src and 'contact=app_startup.PAGE_CONTACT' in src
    assert 'app_startup.relaunch_safe_graphics(' in src and 'PAGE_CONTACT.is_set()' in src
