"""The final report HTML → PDF with headless Chrome — the SAME print pipeline every
feature report already uses (``--print-to-pdf``, no browser header/footer, the report's
own ``@page`` size/margins, ``print-color-adjust: exact`` from the theme).

This module is also the ONE place the whole tool finds and runs a browser:

* :func:`chrome_candidates` lists every Chromium we know of, in preference order —
  installed Google Chrome, then Microsoft Edge, then Chromium, then Playwright's headless
  shell, and Playwright's full Chromium LAST (on the owner's PC that one cannot start at
  all: ``[WinError 14001] … side-by-side configuration is incorrect``);
* :func:`find_working_chrome` PROBES them once (a real one-line headless print) and caches
  the first that works for the rest of the session — ``server._find_chrome()`` uses it;
* :func:`run_chrome` runs a job on the cached browser and, if that one cannot start or
  produces nothing, falls through to the next candidate — every PDF route, the Word
  export's chart pictures and the Special Report print through it.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import threading


def _pf(var, default):
    return os.environ.get(var) or default


def _installed_paths():
    """Fixed install locations, preferred browser first (Chrome → Edge → Chromium)."""
    pf = _pf('ProgramFiles', r'C:\Program Files')
    pf86 = _pf('ProgramFiles(x86)', r'C:\Program Files (x86)')
    local = os.environ.get('LOCALAPPDATA') or ''
    chrome = [os.path.join(pf, 'Google', 'Chrome', 'Application', 'chrome.exe'),
              os.path.join(pf86, 'Google', 'Chrome', 'Application', 'chrome.exe')]
    if local:                                            # per-user Chrome install
        chrome.append(os.path.join(local, 'Google', 'Chrome', 'Application', 'chrome.exe'))
    chrome += _app_paths('chrome.exe')
    edge = [os.path.join(pf86, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
            os.path.join(pf, 'Microsoft', 'Edge', 'Application', 'msedge.exe')]
    edge += _app_paths('msedge.exe')
    chromium = [os.path.join(pf, 'Chromium', 'Application', 'chrome.exe'),
                os.path.join(pf86, 'Chromium', 'Application', 'chrome.exe')]
    if local:
        chromium.append(os.path.join(local, 'Chromium', 'Application', 'chrome.exe'))
    return chrome + edge + chromium


def _app_paths(exe_name):
    """Windows 'App Paths' registration — finds Chrome/Edge installed somewhere unusual."""
    if sys.platform != 'win32':
        return []
    try:
        import winreg
    except ImportError:                                  # pragma: no cover
        return []
    out = []
    key = r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths' + '\\' + exe_name
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, key) as k:
                val, _ = winreg.QueryValueEx(k, None)
            if val:
                out.append(os.path.normpath(str(val).strip().strip('"')))
        except OSError:
            continue
    return out


def _playwright_paths():
    """Playwright's own browsers: the headless shell first, the full Chromium last."""
    roots = [os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or '']
    local = os.environ.get('LOCALAPPDATA') or ''
    if local:
        roots.append(os.path.join(local, 'ms-playwright'))
    shells, fulls = [], []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for name in ('chrome-headless-shell.exe', 'headless_shell.exe'):
            shells += sorted(glob.glob(os.path.join(root, 'chromium_headless_shell-*', '*', name)),
                             reverse=True)                 # newest build first
        fulls += sorted(glob.glob(os.path.join(root, 'chromium-*', 'chrome-win*', 'chrome.exe')),
                        reverse=True)
    return shells + fulls


def _on_path():
    """Last resort (non-standard installs, Linux/Mac dev boxes): whatever is on PATH."""
    out = []
    for name in ('chrome', 'msedge', 'google-chrome', 'chromium', 'chromium-browser'):
        p = shutil.which(name)
        if p:
            out.append(p)
    return out


def chrome_candidates(first=None):
    """``first`` (a caller's explicit choice), then every other Chromium we know of, in the
    order we prefer them — only paths that exist. A broken install (e.g. a Playwright
    Chromium whose side-by-side manifest fails to load) must not stop the export when a
    working browser is also present: :func:`run_chrome` falls through this list."""
    out = []
    for p in [first, *_installed_paths(), *_playwright_paths(), *_on_path()]:
        if p and p not in out and os.path.isfile(p):
            out.append(p)
    return out


# ── probe once, cache the first that works ─────────────────────────────────
_LOCK = threading.RLock()
_WORKING = None            # the browser that last printed successfully this session
_BROKEN = set()            # binaries that could not even start (OSError) — never retried

_BASE_FLAGS = ('--headless', '--disable-gpu', '--no-sandbox')
_PROBE_HTML = '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><p>ok</p></body></html>'


def _no_window():
    """Never flash a console window from the windowed app (the headless shell is a
    console program)."""
    flag = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    return {'creationflags': flag} if flag else {}


def _usable(exe):
    return bool(exe) and exe not in _BROKEN and os.path.isfile(exe)


def reset_chrome_cache():
    """Forget the cached browser and the broken list (tests; or after an install)."""
    global _WORKING
    with _LOCK:
        _WORKING = None
        _BROKEN.clear()


def probe_chrome(exe, timeout=30):
    """True when ``exe`` starts headless and prints a one-line page to a non-empty PDF."""
    if not exe or not os.path.isfile(exe):
        return False
    tmpdir = tempfile.mkdtemp(prefix='cx_probe_')
    try:
        html = os.path.join(tmpdir, 'probe.html')
        pdf = os.path.join(tmpdir, 'probe.pdf')
        with open(html, 'w', encoding='utf-8') as fh:
            fh.write(_PROBE_HTML)
        subprocess.run([exe, *_BASE_FLAGS, f'--user-data-dir={os.path.join(tmpdir, "profile")}',
                        f'--print-to-pdf={pdf}', '--no-pdf-header-footer',
                        'file:///' + html.replace(os.sep, '/')],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=timeout, **_no_window())
        return os.path.isfile(pdf) and os.path.getsize(pdf) > 0
    except OSError:                       # cannot start at all (missing DLL / side-by-side)
        with _LOCK:
            _BROKEN.add(exe)
        return False
    except subprocess.SubprocessError:    # non-zero exit or hung past the probe timeout
        return False
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def find_working_chrome(preferred=None):
    """The browser to print with: the one cached this session if it is still there, else
    the first candidate (``preferred`` first) that passes :func:`probe_chrome` — cached
    from then on. ``None`` when no browser on this machine can print."""
    global _WORKING
    with _LOCK:
        if _usable(_WORKING) and (not preferred or preferred == _WORKING):
            return _WORKING
        for exe in chrome_candidates(preferred):
            if exe in _BROKEN:
                continue
            if probe_chrome(exe):
                _WORKING = exe
                return exe
        return None


def _run_order(chrome):
    """``chrome`` (the caller's pick), the cached working browser, then every other
    candidate — existing, not known-broken, each once."""
    out = []
    for p in [chrome, _WORKING, *chrome_candidates()]:
        if _usable(p) and p not in out:
            out.append(p)
    return out


def _has_flag(args, flag):
    return any(a == flag or a.startswith(flag + '=') for a in args)


def _output_target(args):
    for a in args:
        for flag in ('--print-to-pdf=', '--screenshot='):
            if a.startswith(flag):
                return a[len(flag):]
    return None


def _produced(target):
    try:
        return os.path.getsize(target) > 0
    except OSError:
        return False


def _clear_target(target):
    """Remove an old file at the output path first, so 'the browser wrote it' is a fact and
    a stale earlier export can never pass for the new one. A file the user has open (a PDF
    viewer locks it) is a clear message, not a silent stale report."""
    if not target or not os.path.exists(target):
        return
    try:
        os.remove(target)
    except OSError as exc:
        raise RuntimeError(f'Cannot replace {os.path.basename(target)} - it is open in another '
                           'program. Close it and export again.') from exc


def run_chrome(chrome, args, timeout=180):
    """Run headless Chrome with ``args`` (everything after the executable). Tries
    ``chrome`` first, then the browser cached this session, then every other candidate:
    a binary that cannot start, exits with an error, or writes no ``--print-to-pdf`` /
    ``--screenshot`` output is skipped for the next one. Returns the executable that ran
    (and caches it). A job that runs past ``timeout`` stops with a clear error instead of
    re-running on every other browser. The base flags (``--headless``, ``--disable-gpu``,
    ``--no-sandbox``, a throw-away ``--user-data-dir``) are added unless ``args`` sets
    them (e.g. ``--headless=new``)."""
    global _WORKING
    args = list(args)
    if chrome is None and not _usable(_WORKING):
        chrome = find_working_chrome()                  # vet one before the real job
    target = _output_target(args)
    _clear_target(target)
    flags = [f for f in _BASE_FLAGS if not _has_flag(args, f)]
    own_profile = not _has_flag(args, '--user-data-dir')
    last = None
    for exe in _run_order(chrome):
        prof = tempfile.mkdtemp(prefix='cx_chrome_') if own_profile else None
        try:
            cmd = [exe, *flags, *([f'--user-data-dir={prof}'] if prof else []), *args]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=timeout, **_no_window())
        except subprocess.TimeoutExpired:
            raise RuntimeError(f'The browser ({os.path.basename(exe)}) did not finish printing '
                               f'within {timeout} s.')
        except OSError as exc:                          # cannot start (missing / side-by-side)
            with _LOCK:
                _BROKEN.add(exe)
                if _WORKING == exe:
                    _WORKING = None
            last = exc
            continue
        except subprocess.CalledProcessError as exc:
            last = exc
            continue
        finally:
            if prof:
                shutil.rmtree(prof, ignore_errors=True)
        if target and not _produced(target):
            last = RuntimeError(f'{os.path.basename(exe)} ran but wrote no output')
            continue
        with _LOCK:
            _WORKING = exe
        return exe
    raise RuntimeError('No working Chrome, Edge or Chromium found to print the report'
                       + (f' ({last})' if last else '')
                       + '. Install Google Chrome or Microsoft Edge and try again.')


def html_to_pdf(html, output_path, chrome=None, timeout=180):
    """Print ``html`` to ``output_path``. ``chrome`` = path from ``server._find_chrome()``
    (``None`` → the browser :func:`find_working_chrome` picks).
    The shared pagination layer (report_theme.with_pagination) is applied first — once —
    and a report that never declared a page size prints on A4 like its Word twin."""
    try:
        import report_theme
        html = report_theme.with_pagination(html)
    except Exception:
        pass
    with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w',
                                     encoding='utf-8') as tmp:
        tmp.write(html)
        html_path = tmp.name
    out = os.path.abspath(output_path)
    tmp_pdf = html_path[:-5] + '.pdf'           # print beside the temp HTML, then move into place
    try:
        run_chrome(chrome, [f'--print-to-pdf={tmp_pdf}', '--no-pdf-header-footer',
                            f'file:///{html_path.replace(os.sep, "/")}'], timeout=timeout)
        if not os.path.isfile(tmp_pdf) or os.path.getsize(tmp_pdf) == 0:
            raise RuntimeError('Chrome did not produce the PDF.')
        shutil.move(tmp_pdf, out)
    finally:
        for p in (html_path, tmp_pdf):
            try:
                os.unlink(p)
            except OSError:
                pass
    return out


def print_html_file(html_path, output_path, chrome=None, timeout=300):
    """Print an HTML file already on disk to ``output_path`` (the feature routes write
    their report HTML to a temp file first). Same fallback chain as :func:`run_chrome`."""
    return run_chrome(chrome, [f'--print-to-pdf={os.path.abspath(output_path)}',
                               '--no-pdf-header-footer',
                               'file:///' + os.path.abspath(html_path).replace(os.sep, '/')],
                      timeout=timeout)
