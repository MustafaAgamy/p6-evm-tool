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


def test_graphics_normal_by_default_and_env_override(monkeypatch):
    env = {}
    assert app_startup.apply_graphics_mode(env) == 'normal' and env == {}
    monkeypatch.setenv(app_startup.SAFE_GRAPHICS_ENV, '1')
    assert app_startup.apply_graphics_mode(env) == 'safe'
    app_startup.enable_safe_graphics('test')
    monkeypatch.setenv(app_startup.SAFE_GRAPHICS_ENV, '0')
    env = {}
    assert app_startup.apply_graphics_mode(env) == 'normal' and env == {}


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


def test_attach_library_loggers_routes_pywebview_errors(tmp_path):
    import logging
    app_startup.attach_library_loggers(('pywebview-test',))
    logging.getLogger('pywebview-test').error('WebView2 initialization failed with exception: X')
    for h in app_startup.get_logger().handlers:
        h.flush()
    assert 'WebView2 initialization failed' in (tmp_path / 'logs' / 'startup.log').read_text(encoding='utf-8')
    for h in app_startup.get_logger().handlers:
        logging.getLogger('pywebview-test').removeHandler(h)
