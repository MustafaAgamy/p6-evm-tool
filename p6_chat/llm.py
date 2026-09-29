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

_DL = {'active': False, 'pct': None, 'error': None, 'done': False, 'key': None}
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
           'downloading': _DL['active'], 'progress': _DL['pct'], 'detail': ''}
    if not eng:
        out['detail'] = "The AI engine didn't load in this build — grounded snapshots still work."
    elif _DL['active']:
        out['detail'] = 'Downloading the AI model…%s' % (
            (' %s%%' % _DL['pct']) if _DL['pct'] is not None else '')
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
        _DL.update({'active': True, 'pct': 0, 'error': None, 'done': False, 'key': key})
    parts = _parts(key)
    tmp = None
    try:
        for i, part in enumerate(parts):
            dest = os.path.join(_models_dir(), part['file'])
            if os.path.isfile(dest) and os.path.getsize(dest) > part['min']:
                continue                                 # this part is already complete
            tmp = dest + '.part'
            _download(part['url'], tmp, i, len(parts))
            os.replace(tmp, dest)
            tmp = None
        with _DL_LOCK:
            _DL.update({'active': False, 'pct': 100, 'done': True})
        return {'ok': True}
    except Exception as exc:
        msg = _download_error(exc)
        with _DL_LOCK:
            _DL.update({'active': False, 'error': msg})
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return {'ok': False, 'error': msg}


class _DownloadProblem(RuntimeError):
    """A download that must not be installed (cut short / no room) — message is user-facing."""


def _download(url, tmp, index, count):
    """Stream one file to `tmp`, updating _DL['pct'] across all `count` parts. Refuses to
    start without room on the disk, and raises when the connection drops before the whole
    file arrived (urllib does NOT raise on a short read) so a cut-short model is never
    installed."""
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers.get('Content-Length') or 0)
        if total:
            try:
                free = shutil.disk_usage(os.path.dirname(tmp)).free
            except OSError:
                free = None
            if free is not None and free < total + 200 * 1024 * 1024:
                raise _DownloadProblem(
                    'Not enough free disk space for the AI model (needs about %.1f GB free on the '
                    'drive that holds your data folder). Free some space and try again.'
                    % ((total + 200 * 1024 * 1024) / 1e9))
        got = 0
        with open(tmp, 'wb') as f:
            while True:
                chunk = r.read(1024 * 512)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if total:
                    _DL['pct'] = round((index + got / total) / count * 100, 1)
        if total and got < total:
            raise _DownloadProblem(
                'The AI model download was cut short (the internet connection dropped at '
                '%d%%). Nothing was installed — try again.' % int(got / total * 100))


def _download_error(exc):
    if isinstance(exc, _DownloadProblem):
        return str(exc)
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
