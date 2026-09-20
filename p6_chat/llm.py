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
import threading
import urllib.request

try:
    from utils import app_data_dir
except Exception:                                    # pragma: no cover - dev fallback
    def app_data_dir():
        p = os.path.join(os.path.expanduser('~'), '.controlyx')
        os.makedirs(p, exist_ok=True)
        return p

MODELS = {
    'fast': {
        'label': 'Faster · Qwen2.5 3B', 'size': '~2 GB',
        'file': 'qwen2.5-3b-instruct-q4_k_m.gguf', 'min': 1_600_000_000,   # real ~1.9 GB
        'url': ('https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/'
                'qwen2.5-3b-instruct-q4_k_m.gguf?download=true'),
    },
    'detailed': {
        'label': 'More detailed · Qwen2.5 7B', 'size': '~4.7 GB',
        'file': 'qwen2.5-7b-instruct-q4_k_m.gguf', 'min': 4_200_000_000,   # real ~4.7 GB
        'url': ('https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/'
                'qwen2.5-7b-instruct-q4_k_m.gguf?download=true'),
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


def set_model_key(key):
    if key not in MODELS:
        return get_model_key()
    try:
        with open(_settings_path(), 'w', encoding='utf-8') as f:
            json.dump({'model_key': key}, f)
    except Exception:
        pass
    return key


def _spec(key=None):
    return MODELS[key or get_model_key()]


def _models_dir():
    p = os.path.join(app_data_dir(), 'ai', 'models')
    os.makedirs(p, exist_ok=True)
    return p


def _model_path(key=None):
    return os.path.join(_models_dir(), _spec(key)['file'])


def _model_ready(key=None):
    try:
        return os.path.getsize(_model_path(key)) > _spec(key)['min']
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
    tmp = _model_path(key) + '.part'
    try:
        req = urllib.request.Request(_spec(key)['url'], headers={'User-Agent': 'Controlyx'})
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get('Content-Length') or 0)
            got = 0
            with open(tmp, 'wb') as f:
                while True:
                    chunk = r.read(1024 * 512)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        _DL['pct'] = round(got / total * 100, 1)
        os.replace(tmp, _model_path(key))
        with _DL_LOCK:
            _DL.update({'active': False, 'pct': 100, 'done': True})
        return {'ok': True}
    except Exception as exc:
        with _DL_LOCK:
            _DL.update({'active': False, 'error': str(exc)})
        try:
            os.remove(tmp)
        except OSError:
            pass
        return {'ok': False, 'error': str(exc)}


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
    if model in MODELS:
        set_model_key(model)
    return get_settings()


def pull(model=None):
    return setup(model)
