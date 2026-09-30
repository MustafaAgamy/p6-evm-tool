"""App-wide screen preferences, kept in <app data>/ui_prefs.json.

Appearance mode, Report Contents picks, remembered table columns, chart styles … are
written by the page into its own browser storage (localStorage). In the app that storage
never survived a restart: the window is a WebView2 started in private (InPrivate) mode
(pywebview's default ``private_mode=True``) and the page is served from a new random local
port at every launch (a new web origin = a new, empty storage). So every such setting went
back to its default each time the app was opened (owner comment 31 b).

The fix keeps the page's storage as it is and mirrors it here: server.py injects the saved
preferences into index.html (``window.__UI_PREFS__``) before any other script runs, and
ui/prefs_bridge.js loads them into the page's storage and sends every later change to
POST /api/ui-prefs. Project settings (weights, weather, milestones, lag reasons …) are NOT
kept here — they belong to the project in the database.

Plain strings only (what browser storage holds). Every function takes the folder so tests
(and the server) decide where the file lives.
"""
import json
import os
import threading
import time

FILE_NAME = 'ui_prefs.json'
MAX_KEY_LEN = 200
MAX_VALUE_LEN = 512 * 1024          # one value (a picker selection is a few hundred bytes)
MAX_TOTAL_LEN = 4 * 1024 * 1024     # the whole file
MAX_KEYS = 2000
# Keys kept elsewhere, never here: the Baseline Narrative project setup ('bn_setup_<id>')
# holds logos + a layout drawing (often over MAX_VALUE_LEN, and everything here is inlined
# into index.html at every start) — it is saved per schedule in the database instead
# (POST /api/narrative/setup). ui/prefs_bridge.js does not send these keys either.
EXCLUDED_PREFIXES = ('bn_setup_',)

_LOCK = threading.Lock()


class PrefsUnavailable(OSError):
    """The preferences file exists but could not be read (locked) — never overwrite it."""


def prefs_path(store_dir):
    return os.path.join(store_dir, FILE_NAME)


def _clean(data):
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items()
            if isinstance(k, str) and isinstance(v, str) and 0 < len(k) <= MAX_KEY_LEN
            and not k.startswith(EXCLUDED_PREFIXES)}


def _read(path, attempts=5):
    """The stored dict. Missing → {}. Damaged (not JSON) → set aside as .bad and {}.
    Locked (antivirus / another reader) → retried, then PrefsUnavailable."""
    last = None
    for i in range(attempts):
        try:
            with open(path, encoding='utf-8') as f:
                return _clean(json.load(f))
        except FileNotFoundError:
            return {}
        except ValueError:
            try:
                os.replace(path, path + '.bad')
            except OSError:
                pass
            return {}
        except OSError as exc:
            last = exc
            time.sleep(0.05 * (i + 1))
    raise PrefsUnavailable(str(last))


def load(store_dir):
    """The saved preferences {key: value}; never raises ({} when unreadable)."""
    try:
        return _read(prefs_path(store_dir))
    except OSError:
        return {}


def _write_atomic(path, data, attempts=5):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        f.flush()
        os.fsync(f.fileno())
    last = None
    for i in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except OSError as exc:            # the target held open for a moment (antivirus)
            last = exc
            time.sleep(0.05 * (i + 1))
    raise last


def update(store_dir, set_=None, remove=None):
    """Apply {key: value} sets and key removals. Returns (count, skipped_keys).

    A key or value that is not a string, is too long, or would push the file past its
    size limit is skipped (listed) — the rest are saved. Raises ValueError for a request
    that is not understood and OSError when the file cannot be read or written (the page
    keeps the change and retries)."""
    set_ = {} if set_ is None else set_
    remove = [] if remove is None else remove
    if not isinstance(set_, dict) or not isinstance(remove, list):
        raise ValueError('Preferences were not understood.')
    path = prefs_path(store_dir)
    with _LOCK:
        cur = _read(path)
        for k in remove:
            if isinstance(k, str):
                cur.pop(k, None)
        skipped = []
        size = len(json.dumps(cur, ensure_ascii=False))
        for k, v in set_.items():
            if (not isinstance(k, str) or not k or len(k) > MAX_KEY_LEN
                    or k.startswith(EXCLUDED_PREFIXES)
                    or not isinstance(v, str) or len(v) > MAX_VALUE_LEN):
                skipped.append(k if isinstance(k, str) else repr(k))
                continue
            grow = len(json.dumps({k: v}, ensure_ascii=False)) - len(json.dumps({k: cur[k]}, ensure_ascii=False)) \
                if k in cur else len(json.dumps({k: v}, ensure_ascii=False))
            if (k not in cur and len(cur) >= MAX_KEYS) or size + grow > MAX_TOTAL_LEN:
                skipped.append(k)
                continue
            cur[k] = v
            size += grow
        _write_atomic(path, cur)
        return len(cur), skipped


def script_json(prefs):
    """The preferences as a JS literal that is safe inside an inline <script>."""
    return (json.dumps(prefs or {}, ensure_ascii=False, separators=(',', ':'))
            .replace('<', '\\u003c').replace('>', '\\u003e')
            .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))
