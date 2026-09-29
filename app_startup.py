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
PAGE_CONTACT = threading.Event()          # set by ANY message from the page: WebView2 is
                                          # rendering our page (even if it then fails)
WEBVIEW_INIT_FAILED = threading.Event()   # pywebview logged 'WebView2 initialization failed'
STATE = {'ready_after_s': None, 'graphics': 'normal', 'watchdog': None, 'page_contact': None}
RELAUNCH_ENV = 'CONTROLYX_RELAUNCHED'     # set in a copy started by relaunch_safe_graphics()

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
_FILE_LOG = False           # only the desktop app (app.py) writes the log file; tests,
                            # the CLI and harnesses importing server.py stay silent


def enable_file_log():
    """Turn on the startup.log file (app.py calls this first thing)."""
    global _FILE_LOG
    _FILE_LOG = True
    reset_logger()


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
            if not _FILE_LOG:
                raise RuntimeError('file log not enabled')
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
        handlers = list(get_logger().handlers)
        for name in names:
            lg = logging.getLogger(name)
            for h in handlers + [_InitFailureWatcher()]:
                if h not in lg.handlers and not (isinstance(h, _InitFailureWatcher) and any(
                        isinstance(x, _InitFailureWatcher) for x in lg.handlers)):
                    lg.addHandler(h)
    except Exception:
        pass


class _InitFailureWatcher(logging.Handler):
    """pywebview's EdgeChromium backend logs 'WebView2 initialization failed' and simply
    returns: the window then stays on its (black) background forever. Turn that log line
    into WEBVIEW_INIT_FAILED so the watchdog can act at once instead of after a timeout."""

    def __init__(self):
        super().__init__(level=logging.ERROR)

    def emit(self, record):
        try:
            if 'initialization failed' in record.getMessage():
                WEBVIEW_INIT_FAILED.set()
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
    PAGE_CONTACT.set()                    # the page is running (whatever it says next)
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
            'uptime_s': round(time.monotonic() - T0, 1),
            'log_path': log_path()}


# ── Start-up timings, splash, log folder (startup DB-2 / BLACK-8) ──────────
# Each step of a start lands in startup.log with its time since launch ([+N.NNs]):
# starting -> graphics mode -> WebView2 profile -> database -> server listening -> window
# created -> window shown (splash closed) -> page loaded (WebView2 navigated) -> page booted
# / ready (the page's own report). A black screen then shows which step never came.

_SPLASH = {'closed': False}


def _splash_module():
    """PyInstaller's splash control (only inside the one-file exe built with a splash)."""
    try:
        import pyi_splash                          # noqa: provided by the bootloader
        return pyi_splash
    except Exception:
        return None


def splash_text(msg):
    """Show a start-up stage on the exe's splash picture (no-op without one)."""
    mod = _splash_module()
    try:
        if mod is not None and not _SPLASH['closed'] and mod.is_alive():
            mod.update_text(str(msg))
    except Exception:
        pass


def close_splash(why=''):
    """Close the exe's splash picture once the app window is on screen. Returns True when
    it was closed now."""
    if _SPLASH['closed']:
        return False
    mod = _splash_module()
    if mod is None:
        return False
    try:
        if mod.is_alive():
            mod.close()
            _SPLASH['closed'] = True
            log('splash closed (%s)', why or 'done')
            return True
    except Exception:
        log_exception('closing the splash failed')
    return False


def on_window_shown():
    """window.events.shown: the app window is on screen (its dark background)."""
    log('window shown')
    close_splash('window shown')


def on_page_loaded():
    """window.events.loaded: WebView2 finished navigating to the page."""
    log('page loaded by WebView2')


def open_log_folder(opener=None):
    """Help ▸ Contact & Support ▸ 'Open log folder': open the folder that holds
    startup.log in Explorer. Returns {'ok', 'path'} (path = the log file) — the page shows
    the path whether or not the folder could be opened."""
    path = log_path()
    folder = os.path.dirname(path)
    try:
        os.makedirs(folder, exist_ok=True)
        if opener is None:
            opener = getattr(os, 'startfile', None)
        if opener is None:
            return {'ok': False, 'path': path}
        opener(folder)
        return {'ok': True, 'path': path}
    except Exception as exc:
        log('could not open the log folder (%r)', exc)
        return {'ok': False, 'path': path}


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


def disable_safe_graphics(reason):
    """Back to normal (GPU) graphics from the next launch — the Help ▸ Contact & Support
    'Safe graphics' switch. Removes the flag file (a locked file is overwritten with
    enabled=False instead). Returns True when the saved setting is now off. A launch that
    again never shows the page switches it back on by itself (begin_launch/watchdog)."""
    path = _graphics_flag_path()
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        if not _write_json(path, {'enabled': False, 'reason': reason,
                                  'since': datetime.now().isoformat(timespec='seconds')}):
            return False
    log('safe graphics mode switched OFF for the next launches: %s', reason,
        level=logging.WARNING)
    return not bool((_read_json(path) or {}).get('enabled'))


def graphics_status():
    """What the Help screen shows: the saved choice (used from the next launch), why and
    since when it was switched on, the mode THIS window started in, and whether an
    environment variable set by the user overrides the saved choice."""
    flag = _read_json(_graphics_flag_path()) or {}
    on = bool(flag.get('enabled'))
    env = os.environ.get(SAFE_GRAPHICS_ENV, '').strip()
    forced = env if env in ('0', '1') and os.environ.get(RELAUNCH_ENV) != '1' else None
    return {'saved': on,
            'reason': flag.get('reason') if on else None,
            'since': flag.get('since') if on else None,
            'this_launch': STATE.get('graphics') or 'normal',
            'forced': forced}


def apply_graphics_mode(env=None):
    """Set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS when safe graphics is on. Must run
    before the first window is created. Returns 'safe' or 'normal'."""
    env = os.environ if env is None else env
    mode = 'safe' if safe_graphics_enabled() else 'normal'
    if mode == 'safe' and not env.get('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'):
        env['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = SAFE_GRAPHICS_ARGS
    STATE['graphics'] = mode
    return mode


# ── Readiness watchdog (app.py runs this on a daemon thread) ──────────────

def _wait(ready, seconds, closed, step=0.25, abort=None):
    """ready.wait(seconds), but give up as soon as the window is closed (None) or
    ``abort`` is set ('abort')."""
    deadline = time.monotonic() + seconds
    poll = closed is not None or abort is not None
    while True:
        if abort is not None and abort.is_set() and not ready.is_set():
            return 'abort'
        left = deadline - time.monotonic()
        if left <= 0:
            return ready.is_set()
        if ready.wait(min(step, left) if poll else left):
            return True
        if closed is not None and closed.is_set():
            return None


def watch_startup(window, url, ready=None, first_s=45.0, second_s=30.0, closed=None,
                  abort=None, contact=None, no_contact_s=20.0):
    """Wait for the page's ``ready``. If it never comes (WebView2 failed to initialise,
    the renderer died, the page never loaded), reload the page once; if that also never
    becomes ready, record the failure so the next launch uses safe graphics. Stops
    quietly ('closed') when ``closed`` (the window's closed event) is set first.

    ``abort`` (WEBVIEW_INIT_FAILED) ends the wait at once: WebView2 never started, so a
    reload cannot help. ``contact`` (PAGE_CONTACT): while the page has said nothing at
    all, the reload comes after ``no_contact_s`` instead of ``first_s`` (a running page
    that is merely slow keeps the full ``first_s``). STATE['page_contact'] tells the
    caller whether WebView2 ever ran the page (app.py relaunches only when it did not)."""
    ready = READY if ready is None else ready
    t_start = time.monotonic()
    if contact is not None and no_contact_s < first_s:
        got = _wait(ready, no_contact_s, closed, abort=abort)
        if got is False and contact.is_set():
            got = _wait(ready, first_s - no_contact_s, closed, abort=abort)
    else:
        got = _wait(ready, first_s, closed, abort=abort)
    if got is None:
        return 'closed'
    if got == 'abort':
        return _startup_failed('WebView2 failed to start (the pywebview error is logged above)',
                               contact)
    if got:
        log('page ready after %ss', STATE.get('ready_after_s'))
        STATE['watchdog'] = 'ready'
        return 'ready'
    log('page not ready after %.0fs (%s): reloading it once', time.monotonic() - t_start,
        'no word from the page' if contact is not None and not contact.is_set()
        else 'the page is running', level=logging.WARNING)
    try:
        window.load_url(url)
    except Exception:
        log_exception('reload failed')
    got = _wait(ready, second_s, closed, abort=abort)
    if got is None:
        return 'closed'
    if got is True:
        log('page ready after the reload (%ss)', STATE.get('ready_after_s'))
        STATE['watchdog'] = 'ready-after-reload'
        return 'ready-after-reload'
    return _startup_failed('WebView2 failed to start (the pywebview error is logged above)'
                           if got == 'abort' else
                           'the page never became ready in %.0fs' % (time.monotonic() - t_start),
                           contact)


def _startup_failed(reason, contact):
    STATE['page_contact'] = None if contact is None else contact.is_set()
    log('%s%s', reason, '' if contact is None else (
        ' - the page is running (its own Retry card is on screen)' if contact.is_set()
        else ' - the page never ran'), level=logging.ERROR)
    STATE['watchdog'] = 'failed'
    _update_launch_state(watchdog='failed')
    if not safe_graphics_enabled():
        enable_safe_graphics(reason)
    return 'failed'


def relaunch_command():
    """The command that starts this app again: the exe itself when frozen, else
    ``python app.py``."""
    if getattr(sys, 'frozen', False):
        return [sys.executable] + list(sys.argv[1:])
    return [sys.executable, os.path.abspath(sys.argv[0])] + list(sys.argv[1:])


def relaunch_safe_graphics(reason, popen=None, env=None):
    """Start ONE fresh copy of the app in safe graphics mode and hand over to it (the
    caller then closes its window). Used when WebView2 never showed the page at all, so
    the owner does not have to close and reopen by hand. A copy that is itself a relaunch
    never relaunches again. Returns True when the new copy was started."""
    env = dict(os.environ if env is None else env)
    if env.get(RELAUNCH_ENV) == '1':
        log('not relaunching (this copy is already a relaunch): %s', reason, level=logging.ERROR)
        return False
    try:
        if not safe_graphics_enabled():
            enable_safe_graphics(reason)
        _update_launch_state(watchdog='failed', relaunched=True)
        with _LAUNCH_LOCK:                 # hand over: closing this window must not
            _LAUNCH.clear()                # overwrite the new copy's launch record
        for k in [k for k in env if k.startswith('_PYI_') or k == '_MEIPASS2']:
            env.pop(k, None)               # the new copy unpacks its own files (PyInstaller)
        env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        env[RELAUNCH_ENV] = '1'
        env[SAFE_GRAPHICS_ENV] = '1'
        if popen is None:
            import subprocess
            popen = subprocess.Popen
        cmd = relaunch_command()
        popen(cmd, env=env, close_fds=True)
        log('relaunched in safe graphics mode (%s): %s', reason, cmd, level=logging.WARNING)
        return True
    except Exception:
        log_exception('relaunch failed')
        return False


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


# ── WebView2 profile folder (BLACK-7) ──────────────────────────────────────
# pywebview's default (private mode, no storage_path) gives WebView2 a brand-new user-data
# folder in %TEMP% at EVERY launch: a cold profile is built while the window shows only its
# dark background, and a copy that did not close cleanly leaves the folder behind. The app
# now keeps ONE profile folder per graphics mode under <app data>\webview\ and reuses it.
#
# The page itself still runs InPrivate (private_mode=True): the page comes from a new random
# local port each launch, i.e. a new web origin, so page storage kept on disk would pile up
# one copy per launch (Narrative setups carry logos and drawings) and could bring back a
# removed preference when a port repeats. Preferences live in ui_prefs.json / the database
# (ui/prefs_bridge.js) exactly as before; only the WebView2 folder is kept.
#
# A kept folder is only used when no other WebView2 is using it — WebView2 refuses to share a
# folder between browsers started with different options (a safe-graphics relaunch while the
# black window is closing), and a hung browser on it would hang this window too. Otherwise a
# fresh folder is used for this launch only (deleted at close; leftovers swept later). After
# a launch that never showed the page, the folder of the current mode is started afresh.

PROFILE_DIR = 'webview'
FRESH_PREFIX = 'fresh-'
OLD_MARK = '.old-'


def _profile_base():
    return os.path.join(data_dir(), PROFILE_DIR)


def profile_in_use(folder):
    """True when a running WebView2 browser holds this user-data folder. Chromium keeps
    ``EBWebView\\lockfile`` open with delete-on-close while it runs, so opening it without
    FILE_SHARE_DELETE fails with a sharing violation (32); a closed profile's lockfile opens
    (or is absent). Any other failure to check counts as in use (the safe answer)."""
    lock = os.path.join(folder, 'EBWebView', 'lockfile')
    if not os.path.exists(lock):
        return False
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.HANDLE)
        GENERIC_READ, SHARE_RW, OPEN_EXISTING = 0x80000000, 0x1 | 0x2, 3
        h = k32.CreateFileW(lock, GENERIC_READ, SHARE_RW, None, OPEN_EXISTING, 0, None)
        if h is None or h == ctypes.c_void_p(-1).value:
            return ctypes.get_last_error() != 2       # 2 = gone meanwhile; 32 = held
        k32.CloseHandle(h)
        return False
    except Exception:
        return True


def _writable_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, '.write-test-%d' % os.getpid())
        with open(probe, 'w') as f:
            f.write('ok')
        os.remove(probe)
        return True
    except Exception:
        return False


def _rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.exists(path)


def _sweep_profiles(base, keep):
    """Remove fresh-* folders of earlier launches and profiles set aside after a failed
    launch — never one a running WebView2 still holds. Returns the names removed."""
    removed = []
    try:
        names = os.listdir(base)
    except OSError:
        return removed
    for name in names:
        path = os.path.join(base, name)
        if os.path.normcase(path) == os.path.normcase(keep) or not os.path.isdir(path):
            continue
        if not (name.startswith(FRESH_PREFIX) or OLD_MARK in name):
            continue
        if profile_in_use(path):
            continue
        if _rmtree(path):
            removed.append(name)
    return removed


def _reset_profile(folder):
    """Set a profile aside (then delete it) so this launch starts WebView2 afresh."""
    if not os.path.isdir(folder):
        return True
    aside = folder + OLD_MARK + datetime.now().strftime('%Y%m%d-%H%M%S')
    try:
        os.replace(folder, aside)
    except OSError:
        return False
    _rmtree(aside)
    return True


def webview_profile(graphics=None, previous=None, env=None):
    """Choose this launch's WebView2 user-data folder (app.py passes it to webview.start as
    ``storage_path`` with ``private_mode=True``). Returns ``{'path', 'kind', 'reason'}``:
    kind 'kept' = <app data>\\webview\\<normal|safe>, reused between launches;
    'fresh' = <app data>\\webview\\fresh-<pid>-<time>, this launch only; 'temp' = path None,
    pywebview's own temporary folder (the app data folder is not writable). Never raises."""
    env = os.environ if env is None else env
    try:
        mode = graphics or STATE.get('graphics') or 'normal'
        base = _profile_base()
        kept = os.path.join(base, 'safe' if mode == 'safe' else 'normal')
        why = None
        if env.get(RELAUNCH_ENV) == '1':
            why = 'relaunched copy (the window it replaces may still hold its folder)'
        elif STATE.get('other_copy'):
            why = 'another copy of the app is running'
        elif profile_in_use(kept):
            why = 'the kept profile is still held by a WebView2 process'
        if why is None:
            note = 'reused' if os.path.isdir(kept) else 'created'
            if previous_launch_failed(previous):
                if _reset_profile(kept):
                    note = 'started afresh after a launch that never showed the page'
                else:
                    why = 'the kept profile could not be reset after a failed launch'
            if why is None and _writable_dir(kept):
                res = {'path': kept, 'kind': 'kept', 'reason': note}
                swept = _sweep_profiles(base, kept)
                if swept:
                    res['swept'] = swept
                STATE['profile'] = res
                return res
            why = why or 'the kept profile folder is not writable'
        fresh = os.path.join(base, '%s%d-%d' % (FRESH_PREFIX, os.getpid(), int(time.time())))
        if _writable_dir(fresh):
            res = {'path': fresh, 'kind': 'fresh', 'reason': why}
        else:
            res = {'path': None, 'kind': 'temp', 'reason': why + '; app data not writable'}
    except Exception as exc:
        res = {'path': None, 'kind': 'temp', 'reason': 'profile check failed: %r' % (exc,)}
    STATE['profile'] = res
    return res


def keep_profile_on_close(profile=None):
    """pywebview in private mode deletes the WebView2 user-data folder when the window
    closes (EdgeChrome.clear_user_data: dispose, wait up to 3 s, rmtree). For the KEPT
    folder skip that — exactly pywebview's own non-private close path — so the next launch
    reuses it; a 'fresh' folder is still deleted. Call once webview.start() has loaded the
    backend (app.py does it from the webview.start func). Returns True when in place."""
    profile = STATE.get('profile') if profile is None else profile
    if not isinstance(profile, dict) or profile.get('kind') != 'kept' or not profile.get('path'):
        return False
    mod = sys.modules.get('webview.platforms.edgechromium')
    cls = getattr(mod, 'EdgeChrome', None) if mod is not None else None
    orig = getattr(cls, 'clear_user_data', None) if cls is not None else None
    if orig is None:
        log('WebView2 profile: pywebview close hook not found; the folder may be deleted at '
            'close (as before)', level=logging.WARNING)
        return False
    keep = os.path.normcase(os.path.abspath(profile['path']))
    if getattr(orig, '_keeps', None) == keep:
        return True
    base_fn = getattr(orig, '_wrapped', orig)

    def clear_user_data(self, *args, **kwargs):
        try:
            folder = os.path.normcase(os.path.abspath(str(getattr(self, 'user_data_folder', ''))))
        except Exception:
            folder = ''
        if folder == keep:
            return None
        return base_fn(self, *args, **kwargs)

    clear_user_data._keeps = keep
    clear_user_data._wrapped = base_fn
    cls.clear_user_data = clear_user_data
    return True


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


def _window_pid(hwnd):
    import ctypes
    pid = ctypes.c_ulong(0)
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _running_copy_is_ready(hwnd):
    """True when the running copy that owns ``hwnd`` reported a working page (its launch
    record, written by begin_launch/mark_ready, names its pid)."""
    state = _read_json(_launch_state_path())
    try:
        return bool(state and state.get('ready') and state.get('pid') == _window_pid(hwnd))
    except Exception:
        return False


def single_instance(name, title, wait_s=12.0, poll_s=0.25):
    """Return True to continue launching, False when another running copy's window was
    brought to the front instead. Only a copy whose page is WORKING is brought forward;
    a copy that is still starting is waited for up to ``wait_s``, and one that never
    became ready (a black or blank window), is hung, or has no window at all never
    blocks this launch. A copy started by relaunch_safe_graphics() does not wait on the
    copy it replaces (that one is closing its never-shown window)."""
    global _MUTEX
    if sys.platform != 'win32':
        return True
    if os.environ.get(RELAUNCH_ENV) == '1':
        wait_s = 0.0
    try:
        import ctypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
        handle = kernel32.CreateMutexW(None, False, name)
        already = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        _MUTEX = handle                                 # keep it for the process lifetime
        if not already:
            return True
        STATE['other_copy'] = True          # its WebView2 folder is not ours to reuse
        log('another copy is already running: looking for its window')
        deadline = time.monotonic() + max(0.0, wait_s)
        seen = False
        while True:
            hwnd = _find_window(title)
            if hwnd:
                seen = True
                if _running_copy_is_ready(hwnd):
                    _focus_window(hwnd)
                    log('brought the running copy to the front; this launch exits')
                    return False
            if time.monotonic() >= deadline:
                break
            time.sleep(poll_s)
        log('the running copy %s: launching anyway' % (
            'never showed a working page' if seen else 'has no usable window'),
            level=logging.WARNING)
        return True
    except Exception:
        log_exception('single-instance check failed: launching anyway')
        return True
