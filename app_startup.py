"""Startup reliability for the desktop app — the "black screen" fixes (stdlib only).

The owner reported that the app *sometimes* opens on a black screen and only a close +
reopen helps. The audit (startup BLACK-1..9, DB-1/2) found the window background and the
anti-flash cover are both near-black, and several independent failures left the page
stuck on them with no message and no trace. This module holds the app-side pieces:

* a **startup log** (``<app data>/logs/startup.log``, rotating) — every startup step,
  every page-side failure reported through ``POST /api/client-log`` and every request
  handler crash lands here, so the next black screen leaves evidence;
* the **readiness handshake** — the page reports ``ready`` once its shell is built
  (``mark_ready``); ``watch_startup`` (run by app.py) reloads the page once when that
  never happens and records the failure;
* an evidence-gated **safe-graphics mode** for WebView2 (``--disable-gpu``) that is only
  switched on for the next launches after a launch on THIS machine never became ready
  (closed on a non-ready window, or the watchdog gave up) — never for everyone;
* a **single-instance guard** (named mutex) that brings the running window to the front
  instead of opening a second copy — but never blocks a launch when the other copy has
  no usable window (a leftover or hung process).

Nothing here may raise into the caller: every public function is best-effort.
"""
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

T0 = time.monotonic()
READY = threading.Event()                 # set when the page reports its shell is built
STATE = {'ready_after_s': None, 'graphics': 'normal', 'watchdog': None}

# pywebview sets its own AdditionalBrowserArguments; WebView2 lets the environment variable
# override that value, so the safe-graphics value repeats pywebview's flag.
PYWEBVIEW_ARGS = '--disable-features=ElasticOverscroll'
SAFE_GRAPHICS_ARGS = PYWEBVIEW_ARGS + ' --disable-gpu --disable-gpu-compositing'
SAFE_GRAPHICS_ENV = 'CONTROLYX_SAFE_GRAPHICS'          # '1' forces on, '0' forces off
NOT_READY_CLOSE_S = 8.0     # a window closed this long after launch without ever being ready


# ── Paths / log ────────────────────────────────────────────────────────────

def data_dir():
    """Per-user data folder (utils.app_data_dir); tests monkeypatch this."""
    from utils import app_data_dir
    return app_data_dir()


_LOGGER = None
_LOG_LOCK = threading.Lock()


def log_path():
    return os.path.join(data_dir(), 'logs', 'startup.log')


def get_logger():
    """The startup logger (file handler created lazily; never raises)."""
    global _LOGGER
    with _LOG_LOCK:
        if _LOGGER is not None:
            return _LOGGER
        lg = logging.getLogger('controlyx.startup')
        lg.setLevel(logging.INFO)
        lg.propagate = False
        for h in list(lg.handlers):
            lg.removeHandler(h)
        try:
            path = log_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            h = RotatingFileHandler(path, maxBytes=256 * 1024, backupCount=2,
                                    encoding='utf-8', delay=True)
            h.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(message)s'))
            lg.addHandler(h)
        except Exception:
            lg.addHandler(logging.NullHandler())
        _LOGGER = lg
        return lg


def reset_logger():
    """Drop the cached logger (tests switch data folders between cases)."""
    global _LOGGER
    with _LOG_LOCK:
        if _LOGGER is not None:
            for h in list(_LOGGER.handlers):
                try:
                    h.close()
                except Exception:
                    pass
                _LOGGER.removeHandler(h)
        _LOGGER = None


def log(msg, *args, level=logging.INFO):
    try:
        get_logger().log(level, '[+%.2fs] ' + msg, time.monotonic() - T0, *args)
    except Exception:
        pass


def log_exception(msg, *args):
    try:
        get_logger().exception('[+%.2fs] ' + msg, time.monotonic() - T0, *args)
    except Exception:
        pass


def attach_library_loggers(names=('pywebview',)):
    """Route a library's own logger (pywebview reports 'WebView2 initialization failed'
    there) into the startup log — in the windowed exe it otherwise goes nowhere."""
    try:
        handlers = get_logger().handlers
        for name in names:
            lg = logging.getLogger(name)
            for h in handlers:
                if h not in lg.handlers:
                    lg.addHandler(h)
    except Exception:
        pass


# ── Page → app messages (POST /api/client-log) ─────────────────────────────

_CLIENT_KINDS = {'ready', 'booted', 'error', 'load-failed', 'timeout', 'retry',
                 'rejection', 'notice', 'info'}


def _clip(v, n=600):
    s = '' if v is None else str(v)
    return s if len(s) <= n else s[:n] + '…'


def client_log(payload):
    """Record a message from the page's startup guard. ``kind == 'ready'`` completes the
    readiness handshake. Returns the normalised record (for tests)."""
    p = payload if isinstance(payload, dict) else {}
    kind = str(p.get('kind') or 'info')
    kind = kind if kind in _CLIENT_KINDS else 'info'
    rec = {'kind': kind, 'message': _clip(p.get('message')), 'detail': _clip(p.get('detail')),
           'attempt': p.get('attempt') if isinstance(p.get('attempt'), int) else None,
           'ms': p.get('ms') if isinstance(p.get('ms'), (int, float)) else None}
    level = logging.INFO if kind in ('ready', 'booted', 'info', 'notice') else logging.WARNING
    log('page %s: %s %s (attempt=%s, ms=%s)', kind, rec['message'], rec['detail'],
        rec['attempt'], rec['ms'], level=level)
    if kind == 'ready':
        mark_ready(rec)
    return rec


def mark_ready(info=None):
    if not READY.is_set():
        STATE['ready_after_s'] = round(time.monotonic() - T0, 2)
        READY.set()
        _update_launch_state(ready=True, ready_after_s=STATE['ready_after_s'])


def health():
    """The app-side half of GET /api/health."""
    return {'ready': READY.is_set(), 'ready_after_s': STATE.get('ready_after_s'),
            'graphics': STATE.get('graphics', 'normal'),
            'uptime_s': round(time.monotonic() - T0, 1)}


# ── Launch state + evidence-gated safe graphics ────────────────────────────

def _launch_state_path():
    return os.path.join(data_dir(), 'launch_state.json')


def _graphics_flag_path():
    return os.path.join(data_dir(), 'safe_graphics.json')


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            v = json.load(f)
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def _write_json(path, obj):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(obj, f, indent=1)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


_LAUNCH = {}
_LAUNCH_LOCK = threading.Lock()


def _update_launch_state(**fields):
    with _LAUNCH_LOCK:
        if not _LAUNCH:
            return
        _LAUNCH.update(fields)
        _write_json(_launch_state_path(), dict(_LAUNCH))


def previous_launch_failed(prev):
    """True when the previous launch never showed a working page: the user closed a
    non-ready window after NOT_READY_CLOSE_S, or the watchdog gave up on it."""
    if not isinstance(prev, dict) or prev.get('ready'):
        return False
    if prev.get('watchdog') == 'failed':
        return True
    closed = prev.get('closed_after_s')
    return isinstance(closed, (int, float)) and closed >= NOT_READY_CLOSE_S


def begin_launch():
    """Record this launch; if the previous one on this machine never became ready, turn on
    safe graphics for this and later launches. Returns the previous launch record."""
    prev = _read_json(_launch_state_path())
    if previous_launch_failed(prev) and not safe_graphics_enabled():
        enable_safe_graphics('previous launch never showed a working page (%s)' % (
            'watchdog gave up' if prev.get('watchdog') == 'failed'
            else 'closed after %.0fs without becoming ready' % prev.get('closed_after_s', 0)))
    with _LAUNCH_LOCK:
        _LAUNCH.clear()
        _LAUNCH.update({'started': datetime.now().isoformat(timespec='seconds'),
                        'pid': os.getpid(), 'ready': False})
        _write_json(_launch_state_path(), dict(_LAUNCH))
    return prev


def end_launch():
    """Called when the window closes."""
    if not READY.is_set():
        secs = round(time.monotonic() - T0, 1)
        log('window closed after %.1fs without the page ever becoming ready', secs,
            level=logging.WARNING)
        _update_launch_state(closed_after_s=secs)
    else:
        _update_launch_state(closed_after_s=round(time.monotonic() - T0, 1))


def safe_graphics_enabled():
    env = os.environ.get(SAFE_GRAPHICS_ENV, '').strip()
    if env in ('0', '1'):
        return env == '1'
    flag = _read_json(_graphics_flag_path())
    return bool(flag and flag.get('enabled'))


def enable_safe_graphics(reason):
    ok = _write_json(_graphics_flag_path(), {
        'enabled': True, 'reason': reason,
        'since': datetime.now().isoformat(timespec='seconds'),
        'note': 'WebView2 runs with --disable-gpu. Delete this file (or set %s=0) to '
                'return to normal graphics.' % SAFE_GRAPHICS_ENV})
    log('safe graphics mode switched ON for the next launches: %s', reason,
        level=logging.WARNING)
    return ok


def apply_graphics_mode(env=None):
    """Set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS when safe graphics is on. Must run
    before the first window is created. Returns 'safe' or 'normal'."""
    env = os.environ if env is None else env
    mode = 'safe' if safe_graphics_enabled() else 'normal'
    if mode == 'safe' and not env.get('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'):
        env['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = SAFE_GRAPHICS_ARGS
    STATE['graphics'] = mode
    return mode


# ── Readiness watchdog (app.py runs this through webview.start(func)) ─────

def watch_startup(window, url, ready=None, first_s=45.0, second_s=30.0):
    """Wait for the page's ``ready``. If it never comes (WebView2 failed to initialise,
    the renderer died, the page never loaded), reload the page once; if that also never
    becomes ready, record the failure so the next launch uses safe graphics."""
    ready = READY if ready is None else ready
    if ready.wait(first_s):
        log('page ready after %ss', STATE.get('ready_after_s'))
        STATE['watchdog'] = 'ready'
        return 'ready'
    log('page not ready after %.0fs — reloading it once', first_s, level=logging.WARNING)
    try:
        window.load_url(url)
    except Exception:
        log_exception('reload failed')
    if ready.wait(second_s):
        log('page ready after the reload (%ss)', STATE.get('ready_after_s'))
        STATE['watchdog'] = 'ready-after-reload'
        return 'ready-after-reload'
    log('page never became ready (%.0fs)', first_s + second_s, level=logging.ERROR)
    STATE['watchdog'] = 'failed'
    _update_launch_state(watchdog='failed')
    if not safe_graphics_enabled():
        enable_safe_graphics('the page never became ready in %.0fs' % (first_s + second_s))
    return 'failed'


def hook_renderer_recovery(window):
    """Reload the page when WebView2 reports a crashed/unresponsive renderer (otherwise
    the window stays blank until restarted). Best-effort; logs when unavailable."""
    try:
        from System import Action                      # pythonnet (WinForms backend)
        wv = window.native.browser.webview

        def on_failed(sender, args):
            try:
                kind = str(args.ProcessFailedKind)
            except Exception:
                kind = '?'
            log('WebView2 process failed: %s', kind, level=logging.ERROR)
            if 'Render' in kind or 'Frame' in kind:
                try:
                    sender.Reload()
                    log('reloaded the page after the renderer failure')
                except Exception:
                    log_exception('reload after renderer failure failed')

        def attach():
            wv.CoreWebView2.ProcessFailed += on_failed

        wv.Invoke(Action(attach))
        log('renderer-failure recovery attached')
        return True
    except Exception as exc:
        log('renderer-failure recovery unavailable: %r', exc)
        return False


# ── Single instance ────────────────────────────────────────────────────────

_MUTEX = None
ERROR_ALREADY_EXISTS = 183


def _find_window(title):
    import ctypes
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return None
    try:
        if user32.IsHungAppWindow(hwnd):
            return None
    except Exception:
        pass
    return hwnd


def _focus_window(hwnd):
    import ctypes
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def single_instance(name, title, wait_s=12.0, poll_s=0.25):
    """Return True to continue launching, False when another running copy's window was
    brought to the front instead. Never blocks a launch when the other copy has no usable
    window within ``wait_s`` (it may still be starting — then we wait — or be a leftover
    or hung process — then we launch anyway)."""
    global _MUTEX
    if sys.platform != 'win32':
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, name)
        already = kernel32.GetLastError() == ERROR_ALREADY_EXISTS
        _MUTEX = handle                                 # keep it for the process lifetime
        if not already:
            return True
        log('another copy is already running — looking for its window')
        deadline = time.monotonic() + max(0.0, wait_s)
        while True:
            hwnd = _find_window(title)
            if hwnd:
                _focus_window(hwnd)
                log('brought the running copy to the front; this launch exits')
                return False
            if time.monotonic() >= deadline:
                break
            time.sleep(poll_s)
        log('the other copy has no usable window — launching anyway', level=logging.WARNING)
        return True
    except Exception:
        log_exception('single-instance check failed — launching anyway')
        return True
