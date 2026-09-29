"""[startup:F4] BLACK-7 / DB-2 / BLACK-8.

BLACK-7  pywebview's default gave WebView2 a brand-new temporary profile at every launch
         (cold start while the window is black, folders left in %TEMP%). app_startup now
         keeps ONE folder per graphics mode under <app data>/webview and reuses it — never
         one a running WebView2 holds, a fresh one when another copy runs or on a relaunch,
         started afresh after a launch that never showed the page. The page keeps running
         InPrivate (its storage per launch exactly as before).
DB-2     the one-file exe shows a splash while it unpacks; app.py closes it when the window is
         shown (a second copy that hands over closes it too).
BLACK-8  startup.log gets the window-shown / page-loaded timings and the profile choice; Help
         can open the log folder; /api/health names the log file.
"""
import ast
import os
import struct
import sys
import types

import pytest

import app_startup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(app_startup, 'data_dir', lambda: str(tmp_path))
    monkeypatch.delenv(app_startup.RELAUNCH_ENV, raising=False)
    monkeypatch.delenv(app_startup.SAFE_GRAPHICS_ENV, raising=False)
    saved = dict(app_startup.STATE)
    app_startup.STATE.pop('other_copy', None)
    app_startup.STATE.pop('profile', None)
    app_startup.STATE['graphics'] = 'normal'
    app_startup._SPLASH['closed'] = False
    yield
    app_startup.STATE.clear()
    app_startup.STATE.update(saved)
    app_startup._SPLASH['closed'] = False


def _base(tmp_path):
    return os.path.join(str(tmp_path), app_startup.PROFILE_DIR)


# ── BLACK-7: which WebView2 folder ─────────────────────────────────────────

def test_sole_copy_keeps_one_folder_per_mode_and_reuses_it(tmp_path):
    first = app_startup.webview_profile('normal', previous=None, env={})
    assert first['kind'] == 'kept' and first['reason'] == 'created'
    assert first['path'] == os.path.join(_base(tmp_path), 'normal')
    assert os.path.isdir(first['path'])
    marker = os.path.join(first['path'], 'EBWebView', 'Local State')
    os.makedirs(os.path.dirname(marker))
    open(marker, 'w').close()
    again = app_startup.webview_profile('normal', previous={'ready': True}, env={})
    assert again['path'] == first['path'] and again['reason'] == 'reused'
    assert os.path.exists(marker)                              # same profile, not rebuilt
    safe = app_startup.webview_profile('safe', previous=None, env={})
    assert safe['kind'] == 'kept' and safe['path'] == os.path.join(_base(tmp_path), 'safe')
    assert app_startup.STATE['profile'] == safe


def test_another_running_copy_gets_a_fresh_folder(tmp_path):
    app_startup.STATE['other_copy'] = True
    res = app_startup.webview_profile('normal', env={})
    assert res['kind'] == 'fresh' and 'another copy' in res['reason']
    assert os.path.basename(res['path']).startswith(app_startup.FRESH_PREFIX)
    assert os.path.isdir(res['path'])


def test_relaunched_copy_never_shares_the_closing_windows_folder(tmp_path):
    res = app_startup.webview_profile('safe', env={app_startup.RELAUNCH_ENV: '1'})
    assert res['kind'] == 'fresh' and 'relaunched' in res['reason']


def test_single_instance_marks_another_copy(monkeypatch):
    if sys.platform != 'win32':
        pytest.skip('named mutex is Windows-only')
    name = 'Local\\controlyx-test-profile-%d' % os.getpid()
    assert app_startup.single_instance(name, 'no-such-window-title', wait_s=0) is True
    assert not app_startup.STATE.get('other_copy')
    first = app_startup._MUTEX
    try:
        assert app_startup.single_instance(name, 'no-such-window-title', wait_s=0) is True
        assert app_startup.STATE.get('other_copy') is True
    finally:
        import ctypes
        for h in {first, app_startup._MUTEX}:
            if h:
                ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(h))


def _hold_like_chromium(lock):
    """Open the lockfile the way Chromium does (write, share read only, delete-on-close)."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    h = k32.CreateFileW(lock, 0x40000000, 0x1, None, 2, 0x04000000, None)
    assert h and h != ctypes.c_void_p(-1).value, ctypes.get_last_error()
    return lambda: k32.CloseHandle(h)


@pytest.mark.skipif(sys.platform != 'win32', reason='WebView2 lockfile check is Windows-only')
def test_kept_folder_held_by_a_running_webview2_is_not_shared(tmp_path):
    kept = os.path.join(_base(tmp_path), 'normal')
    lock = os.path.join(kept, 'EBWebView', 'lockfile')
    release = _hold_like_chromium(lock)
    try:
        assert app_startup.profile_in_use(kept) is True
        res = app_startup.webview_profile('normal', env={})
        assert res['kind'] == 'fresh' and 'held' in res['reason']
    finally:
        release()
    assert app_startup.profile_in_use(kept) is False            # browser gone: free again
    open(lock, 'w').close()                                      # a stale, unheld lockfile
    assert app_startup.profile_in_use(kept) is False
    assert app_startup.webview_profile('normal', env={})['kind'] == 'kept'


def test_failed_previous_launch_starts_the_profile_afresh(tmp_path):
    kept = os.path.join(_base(tmp_path), 'normal')
    os.makedirs(os.path.join(kept, 'EBWebView', 'ShaderCache'))
    old = os.path.join(kept, 'EBWebView', 'Local State')
    open(old, 'w').close()
    res = app_startup.webview_profile('normal', previous={'ready': False, 'watchdog': 'failed'},
                                      env={})
    assert res['kind'] == 'kept' and 'afresh' in res['reason']
    assert os.path.isdir(kept) and not os.path.exists(old)
    assert not [n for n in os.listdir(_base(tmp_path)) if app_startup.OLD_MARK in n]


def test_leftover_folders_are_swept_but_never_one_in_use(tmp_path):
    base = _base(tmp_path)
    for name in ('fresh-111-1', 'normal.old-20260101-000000', 'unrelated'):
        os.makedirs(os.path.join(base, name, 'EBWebView'))
    busy = os.path.join(base, 'fresh-222-2')
    release = None
    if sys.platform == 'win32':
        release = _hold_like_chromium(os.path.join(busy, 'EBWebView', 'lockfile'))
    try:
        res = app_startup.webview_profile('normal', env={})
        assert res['kind'] == 'kept'
        left = set(os.listdir(base))
        assert 'fresh-111-1' not in left and 'normal.old-20260101-000000' not in left
        assert 'unrelated' in left and 'normal' in left
        if release:
            assert 'fresh-222-2' in left                          # a running WebView2's folder
    finally:
        if release:
            release()


def test_unwritable_data_folder_falls_back_to_pywebviews_temp(monkeypatch):
    monkeypatch.setattr(app_startup, '_writable_dir', lambda p: False)
    res = app_startup.webview_profile('normal', env={})
    assert res['path'] is None and res['kind'] == 'temp'


def test_profile_choice_never_raises(monkeypatch):
    def boom():
        raise OSError('no data folder')
    monkeypatch.setattr(app_startup, 'data_dir', boom)
    res = app_startup.webview_profile('normal', env={})
    assert res['path'] is None and res['kind'] == 'temp'


# ── BLACK-7: keep the folder at close (pywebview's private mode deletes it) ──

class _FakeEdge:
    """Stands in for webview.platforms.edgechromium.EdgeChrome (its private-mode close
    deletes the user-data folder)."""

    def __init__(self, folder):
        self.user_data_folder = folder

    def clear_user_data(self):
        import shutil
        shutil.rmtree(self.user_data_folder)


def test_kept_folder_survives_close_fresh_one_does_not(tmp_path, monkeypatch):
    mod = types.ModuleType('webview.platforms.edgechromium')
    mod.EdgeChrome = type('EdgeChrome', (_FakeEdge,), {})
    monkeypatch.setitem(sys.modules, 'webview.platforms.edgechromium', mod)
    kept = app_startup.webview_profile('normal', env={})
    assert app_startup.keep_profile_on_close() is True
    assert app_startup.keep_profile_on_close() is True                  # idempotent
    mod.EdgeChrome(kept['path']).clear_user_data()
    assert os.path.isdir(kept['path'])
    other = os.path.join(str(tmp_path), 'webview', 'fresh-9-9')
    os.makedirs(other)
    mod.EdgeChrome(other).clear_user_data()
    assert not os.path.exists(other)


def test_close_hook_only_for_a_kept_folder(monkeypatch):
    assert app_startup.keep_profile_on_close({'kind': 'fresh', 'path': 'x'}) is False
    monkeypatch.delitem(sys.modules, 'webview.platforms.edgechromium', raising=False)
    assert app_startup.keep_profile_on_close({'kind': 'kept', 'path': 'x'}) is False


def _pywebview_source(rel):
    import importlib.util
    spec = importlib.util.find_spec('webview')
    if spec is None or not spec.origin:
        pytest.skip('pywebview not installed')
    path = os.path.join(os.path.dirname(spec.origin), *rel.split('/'))
    with open(path, encoding='utf-8') as f:
        return f.read()


def test_installed_pywebview_matches_what_the_fix_relies_on():
    """The close hook patches EdgeChrome.clear_user_data (which reads self.user_data_folder
    and deletes it only in private mode); winforms uses storage_path as the WebView2 folder
    even in private mode. If a pywebview update changes this, this test says so."""
    edge = _pywebview_source('platforms/edgechromium.py')
    assert 'class EdgeChrome' in edge and 'def clear_user_data(self)' in edge
    assert 'self.user_data_folder' in edge and 'rmtree(self.user_data_folder)' in edge
    wf = _pywebview_source('platforms/winforms.py')
    assert "if not _state['private_mode'] or _state['storage_path']:" in wf
    assert "cache_dir = _state['storage_path'] or" in wf
    init = _pywebview_source('__init__.py')
    assert 'private_mode: bool = True' in init and 'storage_path: str | None = None' in init


# ── DB-2: splash ─────────────────────────────────────────────────────────

class _FakeSplash(types.ModuleType):
    def __init__(self):
        super().__init__('pyi_splash')
        self.alive, self.texts, self.closed = True, [], 0

    def is_alive(self):
        return self.alive

    def update_text(self, msg):
        self.texts.append(msg)

    def close(self):
        self.closed += 1
        self.alive = False


def test_splash_shows_stage_and_closes_once_when_the_window_is_shown(monkeypatch):
    fake = _FakeSplash()
    monkeypatch.setitem(sys.modules, 'pyi_splash', fake)
    app_startup.splash_text('Opening your projects...')
    assert fake.texts == ['Opening your projects...']
    app_startup.on_window_shown()
    assert fake.closed == 1
    assert app_startup.close_splash('again') is False and fake.closed == 1
    app_startup.splash_text('late')                              # after close: ignored
    assert fake.texts == ['Opening your projects...']


def test_no_splash_outside_the_exe(monkeypatch):
    monkeypatch.setitem(sys.modules, 'pyi_splash', None)          # import fails
    app_startup.splash_text('x')
    assert app_startup.close_splash() is False


def test_spec_builds_a_splash_from_the_product_name():
    spec = open(os.path.join(ROOT, 'controlyx.spec'), encoding='utf-8').read()
    assert 'Splash(' in spec and "'packaging' / 'splash.png'" in spec
    assert 'from utils import APP_TITLE as _SPLASH_TITLE' in spec
    assert 'always_on_top=False' in spec
    assert '*splash_parts,' in spec and spec.index('*splash_parts,') < spec.index('a.binaries,\n    a.zipfiles')
    png = open(os.path.join(ROOT, 'packaging', 'splash.png'), 'rb').read()
    assert png[:8] == b'\x89PNG\r\n\x1a\n'
    w, h = struct.unpack('>II', png[16:24])
    assert w <= 760 and h <= 480                                  # never resized (no PIL)


# ── BLACK-8: log folder + health ─────────────────────────────────────────

def test_open_log_folder(tmp_path):
    seen = []
    res = app_startup.open_log_folder(opener=seen.append)
    assert res['ok'] is True and res['path'].endswith(os.path.join('logs', 'startup.log'))
    assert seen == [os.path.dirname(res['path'])] and os.path.isdir(seen[0])

    def refuse(_p):
        raise OSError('no Explorer')
    bad = app_startup.open_log_folder(opener=refuse)
    assert bad['ok'] is False and bad['path'] == res['path']


def test_health_names_the_log_file():
    assert app_startup.health()['log_path'] == app_startup.log_path()


def test_window_timings_are_logged(tmp_path):
    app_startup.enable_file_log()
    try:
        app_startup.on_window_shown()
        app_startup.on_page_loaded()
        app_startup.reset_logger()
        text = open(app_startup.log_path(), encoding='utf-8').read()
    finally:
        app_startup._FILE_LOG = False
        app_startup.reset_logger()
    assert 'window shown' in text and 'page loaded by WebView2' in text


# ── app.py wiring (static: app.py opens a real window, never run in tests) ──

def _app_src():
    return open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()


def test_app_passes_the_profile_and_hooks_the_events():
    src = _app_src()
    tree = ast.parse(src)
    start = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == 'start'
             and getattr(n.func.value, 'id', '') == 'webview']
    assert len(start) == 1
    kw = {k.arg: ast.unparse(k.value) for k in start[0].keywords}
    assert kw.get('private_mode') == 'True'
    assert kw.get('storage_path') == "profile['path']"
    assert 'app_startup.webview_profile(graphics, previous=previous)' in src
    assert 'window.events.shown += app_startup.on_window_shown' in src
    assert 'window.events.loaded += app_startup.on_page_loaded' in src
    assert 'window.events.closed += app_startup.close_splash' in src
    assert 'app_startup.keep_profile_on_close()' in src
    exit_at = src.index('sys.exit(0)')
    assert 'close_splash' in src[src.rindex('\n', 0, exit_at - 80):exit_at]
    assert 'def open_log_folder(self)' in src


def test_relaunch_marks_the_kept_folder_so_the_next_launch_starts_it_afresh(tmp_path, monkeypatch):
    """The copy relaunched in safe graphics writes its own (ready) launch record, so the
    failed record is gone; the marker still makes the next launch in that mode reset the
    folder that never showed the page."""
    monkeypatch.setattr(app_startup, 'enable_safe_graphics', lambda reason: True)
    kept = app_startup.webview_profile('normal', env={})
    stale = os.path.join(kept['path'], 'EBWebView', 'Local State')
    os.makedirs(os.path.dirname(stale))
    open(stale, 'w').close()
    started = []
    assert app_startup.relaunch_safe_graphics('test', popen=lambda cmd, **kw: started.append(cmd),
                                              env={}) is True
    assert started and os.path.exists(kept['path'] + app_startup.RESET_SUFFIX)
    nxt = app_startup.webview_profile('normal', previous={'ready': True}, env={})
    assert nxt['kind'] == 'kept' and 'afresh' in nxt['reason']
    assert not os.path.exists(stale)
    assert not os.path.exists(kept['path'] + app_startup.RESET_SUFFIX)
    assert app_startup.webview_profile('normal', previous={'ready': True}, env={})['reason'] == 'reused'
