"""The offline AI brain — bundled, no separate install.

The AI engine (llama.cpp, via llama-cpp-python) ships *inside* the app, so there
is nothing for the user to install. The only one-time step is a model download,
which the app does itself on first use into the user's data folder
(``%APPDATA%\\.controlyx\\ai\\models``). After that every answer is generated
locally — no internet, no key, no cost.

Everything is guarded and offline-safe:
* ``status()``  — is the engine present and the model downloaded?
* ``setup()``   — download the model (blocking; run in a background thread; live
  progress via the module ``_DL`` dict, surfaced by ``status()``).
* ``generate()``— produce an answer locally; raises :class:`LlmNotReady` before the
  model is downloaded so the service can fall back honestly.

If the bundled engine somehow fails to load, ``status().engine`` is False and the
chat degrades to grounded snapshots rather than crashing.
"""
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

# A small, capable instruct model that runs on a normal modern PC (CPU / 8-16 GB).
MODEL_NAME = 'qwen2.5-3b-instruct-q4_k_m.gguf'
MODEL_LABEL = 'Qwen2.5 3B Instruct (Q4)'
MODEL_URL = ('https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/'
             'qwen2.5-3b-instruct-q4_k_m.gguf?download=true')
_MIN_MODEL_BYTES = 200_000_000                       # sanity floor (real file ~1.9 GB)

_DL = {'active': False, 'pct': None, 'error': None, 'done': False}
_DL_LOCK = threading.Lock()
_LLM = None
_LLM_LOCK = threading.Lock()


class LlmError(RuntimeError):
    pass


class LlmNotReady(LlmError):
    """Raised by generate() before the model is downloaded."""


def _models_dir():
    p = os.path.join(app_data_dir(), 'ai', 'models')
    os.makedirs(p, exist_ok=True)
    return p


def _model_path():
    return os.path.join(_models_dir(), MODEL_NAME)


def _model_ready():
    try:
        return os.path.getsize(_model_path()) > _MIN_MODEL_BYTES
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
    mdl = _model_ready()
    out = {'engine': eng, 'model': mdl, 'ready': bool(eng and mdl),
           'model_name': MODEL_LABEL, 'downloading': _DL['active'], 'progress': _DL['pct'],
           'detail': ''}
    if not eng:
        out['detail'] = "The AI engine didn't load in this build — grounded snapshots still work."
    elif _DL['active']:
        out['detail'] = 'Downloading the AI model…%s' % (
            (' %s%%' % _DL['pct']) if _DL['pct'] is not None else '')
    elif not mdl:
        out['detail'] = 'One-time model download needed (~2 GB); after that it runs fully offline.'
    if _DL['error']:
        out['error'] = _DL['error']
    return out


# ── one-time model download (blocking; call in a background thread) ───────────
def setup(model=None):
    with _DL_LOCK:
        if _DL['active']:
            return {'ok': True, 'started': True}
        if _model_ready():
            return {'ok': True, 'already': True}
        if not _engine_ok():
            return {'ok': False, 'error': 'The AI engine is not available in this build.'}
        _DL.update({'active': True, 'pct': 0, 'error': None, 'done': False})
    tmp = _model_path() + '.part'
    try:
        req = urllib.request.Request(MODEL_URL, headers={'User-Agent': 'Controlyx'})
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
        os.replace(tmp, _model_path())
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
    global _LLM
    with _LLM_LOCK:
        if _LLM is None:
            from llama_cpp import Llama
            _LLM = Llama(model_path=_model_path(), n_ctx=4096,
                         n_threads=max(2, (os.cpu_count() or 4) - 1), verbose=False)
        return _LLM


def generate(system, user, temperature=0.3, max_tokens=900, timeout=None):
    if not status().get('ready'):
        raise LlmNotReady('The offline AI brain is not set up yet.')
    try:
        r = _get_llm().create_chat_completion(
            messages=[{'role': 'system', 'content': system},
                      {'role': 'user', 'content': user}],
            temperature=temperature, max_tokens=max_tokens)
        return (r['choices'][0]['message']['content'] or '').strip()
    except LlmError:
        raise
    except Exception as exc:
        raise LlmError('The local AI brain could not answer: %s' % exc)


# ── API compatibility (the in-process brain has no server URL to configure) ──
def get_settings():
    return {'model': MODEL_LABEL, 'model_path': _model_path()}


def save_settings(base_url=None, model=None):
    return get_settings()


def pull(model=None):
    return setup(model)
