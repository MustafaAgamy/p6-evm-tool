"""The offline AI brain — bundled, no separate install, streaming, model-choice.

The AI engine (llama.cpp, via llama-cpp-python) ships *inside* the app, so there
is nothing for the user to install. The only one-time step is a model download,
which the app does itself into the user's data folder. After that every answer is
generated locally — no internet, no key, no cost.

The user can pick how detailed/large the brain is:
  * 'fast'     — Qwen2.5 3B  (~2 GB, quicker)
  * 'detailed' — Qwen2.5 7B  (~4.7 GB, more detailed, slower on CPU)

Public surface: ``status`` / ``setup`` / ``generate`` / ``generate_stream`` /
``get_settings`` / ``save_settings`` / ``pull``. Everything is guarded and
offline-safe; if the bundled engine fails to load, ``status().engine`` is False
and the chat degrades to grounded snapshots + charts rather than crashing.
"""
import json
import os
import shutil
import threading
import time
import urllib.request

try:
    from utils import app_data_dir
except Exception:                                    # pragma: no cover - dev fallback
    def app_data_dir():
        p = os.path.join(os.path.expanduser('~'), '.controlyx')
        os.makedirs(p, exist_ok=True)
        return p

try:                                                 # honest, brand-built User-Agent + messages
    from utils import USER_AGENT, network_error_message
except Exception:                                    # pragma: no cover - utils ships with the app
    USER_AGENT = 'P6-schedule-analysis/1.0'

    def network_error_message(exc, service='this online service', needs=''):
        return f'Could not reach {service} ({exc}).'

_HF = 'https://huggingface.co/Qwen/'

MODELS = {
    'fast': {
        'label': 'Faster · Qwen2.5 3B', 'size': '~2 GB',
        'file': 'qwen2.5-3b-instruct-q4_k_m.gguf', 'min': 1_600_000_000,   # real ~1.9 GB
        'url': ('https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/'
                'qwen2.5-3b-instruct-q4_k_m.gguf?download=true'),
    },
    # The publisher ships the 7B q4_k_m as a TWO-PART split GGUF — the single-file name
    # returns HTTP 404 (this was the default brain, so its download always failed). Both
    # parts are downloaded into the same folder; llama.cpp loads the whole split when it is
    # pointed at part 1 ('file').
    'detailed': {
        'label': 'More detailed · Qwen2.5 7B', 'size': '~4.7 GB',
        'file': 'qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf',
        'parts': [
            {'file': 'qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf', 'min': 3_900_000_000,  # real 3.99 GB
             'url': (_HF + 'Qwen2.5-7B-Instruct-GGUF/resolve/main/'
                     'qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf?download=true')},
            {'file': 'qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf', 'min': 650_000_000,    # real 0.69 GB
             'url': (_HF + 'Qwen2.5-7B-Instruct-GGUF/resolve/main/'
                     'qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf?download=true')},
        ],
    },
}
DEFAULT_KEY = 'detailed'                             # the smarter 7B by default (quality first)
MAX_TOKENS = 2048                                    # allow long, detailed answers
_SETTINGS_NAME = 'chat_brain.json'

_DL = {'active': False, 'pct': None, 'error': None, 'done': False, 'key': None, 'note': None}
_DL_LOCK = threading.Lock()
_LLMS = {}                                           # model_path -> Llama instance
_LLM_LOCK = threading.Lock()


class LlmError(RuntimeError):
    pass


class LlmNotReady(LlmError):
    pass


# ── chosen model (persisted) ─────────────────────────────────────────────────
def _settings_path():
    return os.path.join(app_data_dir(), _SETTINGS_NAME)


def get_model_key():
    try:
        with open(_settings_path(), encoding='utf-8') as f:
            k = json.load(f).get('model_key')
            if k in MODELS:
                return k
    except Exception:
        pass
    return DEFAULT_KEY


def _write_model_key(key):
    """Keep the chosen brain in <app data>/chat_brain.json so it survives an app restart.
    Written to a temp file then swapped in (a crash mid-write never leaves a broken file
    that would silently fall back to the default); any other keys in the file are kept.
    Returns True when the choice is on disk."""
    path = _settings_path()
    data = {}
    try:
        with open(path, encoding='utf-8') as f:
            old = json.load(f)
        if isinstance(old, dict):
            data = old
    except Exception:
        data = {}
    data['model_key'] = key
    tmp = path + '.tmp'
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def set_model_key(key):
    if key not in MODELS:
        return get_model_key()
    _write_model_key(key)
    return key


def _spec(key=None):
    return MODELS[key or get_model_key()]


def _models_dir():
    p = os.path.join(app_data_dir(), 'ai', 'models')
    os.makedirs(p, exist_ok=True)
    return p


def _model_path(key=None):
    return os.path.join(_models_dir(), _spec(key)['file'])


def _parts(key=None):
    """The file(s) a model needs: [{'file', 'url', 'min'}] (one for a single-file model)."""
    spec = _spec(key)
    return spec.get('parts') or [{'file': spec['file'], 'url': spec['url'], 'min': spec['min']}]


def _model_ready(key=None):
    try:
        return all(os.path.getsize(os.path.join(_models_dir(), p['file'])) > p['min']
                   for p in _parts(key))
    except OSError:
        return False


def _engine_ok():
    try:
        import llama_cpp  # noqa: F401
        return True
    except Exception:
        return False


# ── status ──────────────────────────────────────────────────────────────────
def status():
    eng = _engine_ok()
    key = get_model_key()
    mdl = _model_ready(key)
    options = [{'key': k, 'label': v['label'], 'size': v['size'],
                'downloaded': _model_ready(k)} for k, v in MODELS.items()]
    out = {'engine': eng, 'model': mdl, 'ready': bool(eng and mdl),
           'model_key': key, 'model_name': _spec(key)['label'], 'options': options,
           'downloading': _DL['active'], 'progress': _DL['pct'], 'detail': '',
           'retrying': bool(_DL['active'] and _DL.get('note')),
           'resume_pct': None if (mdl or _DL['active']) else _resume_pct(key)}
    if not eng:
        out['detail'] = "The AI engine didn't load in this build — grounded snapshots still work."
    elif _DL['active']:
        pct = (' %s%%' % _DL['pct']) if _DL['pct'] is not None else ''
        out['detail'] = (('%s Downloaded so far:%s.' % (_DL['note'], pct or ' 0%'))
                         if _DL.get('note') else 'Downloading the AI model…' + pct)
    elif not mdl and out['resume_pct'] is not None:
        out['detail'] = ('A previous download of this AI model stopped at %s%% — "Set up the AI '
                         'brain" continues from there (it does not start again from zero).'
                         % out['resume_pct'])
    elif not mdl:
        out['detail'] = ('One-time %s model download needed, then it runs fully offline.'
                         % _spec(key)['size'])
    if _DL['error']:
        out['error'] = _DL['error']
    return out


# ── one-time model download (blocking; call in a background thread) ───────────
def setup(model=None):
    key = model if model in MODELS else get_model_key()
    with _DL_LOCK:
        if _DL['active']:
            # A download is already running; don't repoint the selected model to a
            # different key mid-download (that would mis-associate the file).
            return {'ok': True, 'started': True}
        if _model_ready(key):
            if model in MODELS:
                set_model_key(key)
            return {'ok': True, 'already': True}
        if not _engine_ok():
            return {'ok': False, 'error': 'The AI engine is not available in this build.'}
        if model in MODELS:                              # persist only when we actually start
            set_model_key(key)
        _DL.update({'active': True, 'pct': 0, 'error': None, 'done': False, 'key': key,
                    'note': None})
    parts = _parts(key)
    try:
        for i, part in enumerate(parts):
            dest = os.path.join(_models_dir(), part['file'])
            if os.path.isfile(dest) and os.path.getsize(dest) > part['min']:
                continue                                 # this part is already complete
            tmp = dest + '.part'
            _fetch_part(part['url'], tmp, i, len(parts))
            if os.path.getsize(tmp) <= part['min']:      # e.g. an error page, not the model
                _discard(tmp)
                raise _DownloadProblem(
                    'The downloaded AI model file is smaller than expected, so it was not '
                    'installed. Try again later.')
            os.replace(tmp, dest)
            _discard(tmp)                                # only the progress note is left
        with _DL_LOCK:
            _DL.update({'active': False, 'pct': 100, 'done': True, 'note': None})
        return {'ok': True}
    except Exception as exc:
        msg = _download_error(exc)
        kept = _resume_pct(key)
        if kept is not None:
            # The part already downloaded is KEPT (the owner's connection drops often and the
            # model is 2-4.7 GB): the next "Set up" continues from here, never from zero.
            msg += (' Nothing was installed yet; the %s%% already downloaded is kept — press '
                    '"Set up the AI brain" again when the internet is back and it continues '
                    'from where it stopped.' % kept)
        with _DL_LOCK:
            _DL.update({'active': False, 'error': msg, 'note': None})
        return {'ok': False, 'error': msg}


# A dropped / failed connection is retried after these waits (seconds), each time resuming
# from the bytes already on disk (HTTP Range). A try that got further resets the count, so a
# long download on a patchy connection keeps going; a connection that is simply down gives
# up after the last wait with a plain message (the part stays for the next "Set up").
_RETRY_DELAYS = (3, 10, 30)
_sleep = time.sleep                                  # patched by the tests


class _DownloadProblem(RuntimeError):
    """A download that must not be installed and is not worth retrying (no room on the disk,
    wrong file) — the message is user-facing."""


class _CutShort(OSError):
    """The connection dropped before the whole file arrived (urllib does NOT raise on a
    short read). Retried / resumed like any other connection failure."""

    def __init__(self, got, total):
        super().__init__('cut short at %d of %d bytes' % (got, total))
        self.pct = int(got / total * 100) if total else 0


class _Restart(Exception):
    """The saved part does not belong to the file on the server (it changed, or the server
    refused the resume point): the part was discarded — download again from zero."""


def _meta_path(tmp):
    return tmp + '.json'


def _read_meta(tmp):
    try:
        with open(_meta_path(tmp), encoding='utf-8') as f:
            meta = json.load(f)
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {}


def _write_meta(tmp, meta):
    try:
        with open(_meta_path(tmp), 'w', encoding='utf-8') as f:
            json.dump(meta, f)
    except OSError:
        pass                        # without the note the part is simply not resumed later


def _discard(tmp):
    """Remove a part file and its progress note."""
    for p in (tmp, _meta_path(tmp)):
        try:
            os.remove(p)
        except OSError:
            pass


def _part_size(tmp):
    try:
        return os.path.getsize(tmp)
    except OSError:
        return 0


def _resume_pct(key=None):
    """How much of the model sits on disk from a download that stopped (0-100), or None
    when there is no resumable part."""
    parts = _parts(key)
    done, partial = 0.0, False
    for p in parts:
        dest = os.path.join(_models_dir(), p['file'])
        if _part_size(dest) > p['min']:
            done += 1
            continue
        tmp = dest + '.part'
        size, total = _part_size(tmp), _read_meta(tmp).get('total') or 0
        if size and total:
            done += min(size / total, 1.0)
            partial = True
    return round(done / len(parts) * 100, 1) if partial else None


def _content_range(value):
    """'bytes 100-199/2000' -> (100, 2000); anything else -> (None, None)."""
    try:
        unit, rng = (value or '').split(' ', 1)
        span, total = rng.split('/', 1)
        return int(span.split('-', 1)[0]), int(total)
    except (ValueError, AttributeError):
        return None, None


def _transient(exc):
    """True for a failure worth retrying: the connection dropped / timed out / could not be
    made, or the server is busy. A 404 or a refusal is final; a full disk is final."""
    import errno
    import http.client
    import urllib.error
    if isinstance(exc, (_DownloadProblem, _Restart)):
        return False
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (408, 425, 429, 500, 502, 503, 504)
    if getattr(exc, 'errno', None) == errno.ENOSPC:
        return False
    return isinstance(exc, (OSError, http.client.HTTPException))


def _fetch_part(url, tmp, index, count):
    """Download one file to `tmp`, retrying a dropped connection with backoff and resuming
    from what is already on disk. Raises the last error when it gives up."""
    tries = restarts = 0
    while True:
        before = _part_size(tmp)
        try:
            _download(url, tmp, index, count)
            _DL['note'] = None
            return
        except _Restart:
            restarts += 1
            if restarts > 2:
                raise _DownloadProblem(
                    'The AI model file on the download server kept changing while it was '
                    'downloading, so nothing was installed. Try again later.')
        except Exception as exc:
            if not _transient(exc):
                raise
            if _part_size(tmp) > before:
                tries = 0                            # it got further: keep going
            if tries >= len(_RETRY_DELAYS):
                raise
            delay = _RETRY_DELAYS[tries]
            tries += 1
            _DL['note'] = ('The internet connection dropped — trying again in %d s (try %d of %d); '
                           'the part already downloaded is kept.'
                           % (delay, tries + 1, len(_RETRY_DELAYS) + 1))
            _sleep(delay)


def _download(url, tmp, index, count):
    """One try at streaming `url` into `tmp`, updating _DL['pct'] across all `count` parts.
    Resumes from the bytes already in `tmp` with an HTTP Range request when the progress note
    says they came from this same address; checks the server's answer (resume point, file
    size, ETag) so a changed file is never stitched onto an old part. Refuses to start
    without room on the disk; raises _CutShort when the connection drops early."""
    import urllib.error
    have = _part_size(tmp)
    meta = _read_meta(tmp) if have else {}
    if have and meta.get('url') != url:              # a part from another address: start over
        _discard(tmp)
        have, meta = 0, {}
    headers = {'User-Agent': USER_AGENT}
    if have:
        headers['Range'] = 'bytes=%d-' % have
    req = urllib.request.Request(url, headers=headers)
    try:
        r = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and have:                 # nothing after that point: part is not ours
            _discard(tmp)
            raise _Restart() from None
        raise
    with r:
        status = getattr(r, 'status', None) or 200
        length = int(r.headers.get('Content-Length') or 0)
        etag = r.headers.get('ETag') or ''
        if have and status == 206:
            start, total = _content_range(r.headers.get('Content-Range'))
            if (start != have or not total
                    or (meta.get('total') and total != meta['total'])
                    or (meta.get('etag') and etag and etag != meta['etag'])):
                _discard(tmp)                        # the file on the server changed
                raise _Restart()
            mode = 'ab'
        else:                                        # fresh start (or the server sent it all again)
            have, total, mode = 0, length, 'wb'
        need = total - have
        if need > 0:
            try:
                free = shutil.disk_usage(os.path.dirname(tmp)).free
            except OSError:
                free = None
            if free is not None and free < need + 200 * 1024 * 1024:
                raise _DownloadProblem(
                    'Not enough free disk space for the AI model (needs about %.1f GB free on the '
                    'drive that holds your data folder). Free some space and try again.'
                    % ((need + 200 * 1024 * 1024) / 1e9))
        _write_meta(tmp, {'url': url, 'total': total, 'etag': etag})
        got = have
        with open(tmp, mode) as f:
            while True:
                chunk = r.read(1024 * 512)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if total:
                    _DL['pct'] = round((index + min(got / total, 1.0)) / count * 100, 1)
        if total and got < total:
            raise _CutShort(got, total)
        if total and got > total:                    # more than the server announced
            _discard(tmp)
            raise _Restart()


def _download_error(exc):
    if isinstance(exc, _DownloadProblem):
        return str(exc)
    if isinstance(exc, _CutShort):
        return ('The AI model download was cut short — the internet connection dropped at '
                '%d%% of this file.' % exc.pct)
    return network_error_message(exc, 'the AI model download (Hugging Face)',
                                 needs='the one-time AI model download')


# ── generation (fully offline, in-process) ───────────────────────────────────
def _get_llm():
    path = _model_path()
    with _LLM_LOCK:
        if path not in _LLMS:
            from llama_cpp import Llama
            _LLMS[path] = Llama(model_path=path, n_ctx=8192,
                                n_threads=max(2, (os.cpu_count() or 4) - 1), verbose=False)
        return _LLMS[path]


def _messages(system, user):
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def generate(system, user, temperature=0.3, max_tokens=MAX_TOKENS, timeout=None):
    if not status().get('ready'):
        raise LlmNotReady('The offline AI brain is not set up yet.')
    try:
        r = _get_llm().create_chat_completion(messages=_messages(system, user),
                                              temperature=temperature, max_tokens=max_tokens)
        return (r['choices'][0]['message']['content'] or '').strip()
    except LlmError:
        raise
    except Exception as exc:
        raise LlmError('The local AI brain could not answer: %s' % exc)


def generate_stream(system, user, temperature=0.3, max_tokens=MAX_TOKENS):
    """Yield answer text incrementally (token deltas) for live streaming."""
    if not status().get('ready'):
        raise LlmNotReady('The offline AI brain is not set up yet.')
    try:
        stream = _get_llm().create_chat_completion(
            messages=_messages(system, user), temperature=temperature,
            max_tokens=max_tokens, stream=True)
    except Exception as exc:
        raise LlmError('The local AI brain could not answer: %s' % exc)
    for chunk in stream:
        try:
            delta = (chunk.get('choices') or [{}])[0].get('delta', {}).get('content')
        except Exception:
            delta = None
        if delta:
            yield delta


# ── API compatibility ────────────────────────────────────────────────────────
def get_settings():
    key = get_model_key()
    return {'model_key': key, 'model': _spec(key)['label']}


def save_settings(base_url=None, model=None):
    """Save the chosen brain. The answer says whether it was kept (``saved``) so the chat
    screen can say so when the choice could not be written (it would revert on restart)."""
    saved = None
    if model is not None:
        saved = bool(model in MODELS and _write_model_key(model))
    out = get_settings()
    if saved is not None:
        out['saved'] = saved
        if not saved:
            out['error'] = ('That AI brain is not one of the offered choices.' if model not in MODELS
                            else 'Your AI brain choice could not be saved on this PC '
                                 '(the app data folder is not writable).')
    return out


def pull(model=None):
    return setup(model)
