"""The offline AI brain manager.

The brain is a **local model server** the app talks to over localhost — an
Ollama runtime (default) or any OpenAI-compatible local server. This keeps the
tool itself small and adds no Python native dependency: the model is downloaded
once (via the runtime) into the user's machine, then every answer is generated
locally with no internet, no key and no cost.

Everything here is guarded and offline-safe:
* ``status()`` probes the local runtime (never the public internet) and reports
  whether the engine is running and the model is present.
* ``pull()`` asks the runtime to download the model — the one-time "set up the
  brain" step.
* ``generate()`` produces an answer locally; raises :class:`LlmNotReady` when the
  brain isn't set up, so the service layer can fall back gracefully.

Only stdlib (urllib/json) is used, so this imports cleanly in dev and in the exe.
"""
import json
import os
import urllib.request
import urllib.error

try:
    from utils import app_data_dir
except Exception:                                    # pragma: no cover - dev fallback
    def app_data_dir():
        p = os.path.join(os.path.expanduser('~'), '.controlyx')
        os.makedirs(p, exist_ok=True)
        return p

# A small, capable instruct model that runs on a normal modern PC (CPU/8-16GB).
DEFAULT_BASE_URL = 'http://127.0.0.1:11434'          # Ollama's local port
DEFAULT_MODEL = 'qwen2.5:3b-instruct'
_SETTINGS_NAME = 'chat_brain.json'


class LlmError(RuntimeError):
    pass


class LlmNotReady(LlmError):
    """Raised by generate() when the brain isn't set up yet."""


# ── settings (base URL + model), stored per user ────────────────────────────
def _settings_path():
    return os.path.join(app_data_dir(), _SETTINGS_NAME)


def get_settings():
    s = {'base_url': DEFAULT_BASE_URL, 'model': DEFAULT_MODEL}
    try:
        with open(_settings_path(), encoding='utf-8') as f:
            s.update({k: v for k, v in json.load(f).items() if v})
    except Exception:
        pass
    return s


def save_settings(base_url=None, model=None):
    s = get_settings()
    if base_url:
        s['base_url'] = base_url.rstrip('/')
    if model:
        s['model'] = model
    try:
        with open(_settings_path(), 'w', encoding='utf-8') as f:
            json.dump(s, f)
    except Exception:
        pass
    return s


# ── tiny HTTP helpers (localhost only) ──────────────────────────────────────
def _get(url, timeout):
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _post(url, payload, timeout):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _is_ollama(base):
    return not base.rstrip('/').endswith('/v1')


# ── status ──────────────────────────────────────────────────────────────────
def status():
    """Probe the local runtime. Returns a dict the UI renders a setup card from:
    {engine, model, ready, backend, base_url, model_name, models, detail}."""
    s = get_settings()
    base = s['base_url'].rstrip('/')
    want = s['model']
    out = {'engine': False, 'model': False, 'ready': False,
           'backend': 'ollama' if _is_ollama(base) else 'openai',
           'base_url': base, 'model_name': want, 'models': [], 'detail': ''}
    try:
        if _is_ollama(base):
            tags = _get(base + '/api/tags', timeout=1.5)
            names = [m.get('name') for m in (tags.get('models') or [])]
        else:
            data = _get(base + '/models', timeout=1.5)
            names = [m.get('id') for m in (data.get('data') or [])]
        out['engine'] = True
        out['models'] = [n for n in names if n]
        # match exact or by prefix (Ollama tags like 'qwen2.5:3b-instruct')
        out['model'] = any(n == want or n.startswith(want.split(':')[0]) for n in out['models'] if n)
        out['ready'] = out['engine'] and out['model']
        if not out['model']:
            out['detail'] = "Runtime is running but the model isn't downloaded yet."
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        out['detail'] = ("No local AI runtime detected. Install one (Ollama) so the "
                         "chat can run fully offline on your PC.")
        out['error'] = str(exc)
    return out


# ── one-time model download ──────────────────────────────────────────────────
def pull(model=None, timeout=3600):
    """Ask the local runtime to download the model (the one-time brain setup).
    Blocking; streams Ollama's progress and returns {ok, error}. Only reachable
    when the runtime is installed."""
    s = get_settings()
    base = s['base_url'].rstrip('/')
    model = model or s['model']
    if not _is_ollama(base):
        return {'ok': False, 'error': 'Automatic download is only supported via the '
                                      'Ollama runtime; pull the model in your server.'}
    try:
        data = json.dumps({'name': model, 'stream': False}).encode('utf-8')
        req = urllib.request.Request(base + '/api/pull', data=data,
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            last = {}
            for line in r:                                   # NDJSON progress
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line.decode('utf-8'))
                except ValueError:
                    continue
                if last.get('error'):
                    return {'ok': False, 'error': last['error']}
        save_settings(model=model)
        return {'ok': True}
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {'ok': False, 'error': str(exc)}


# ── generation (fully offline) ───────────────────────────────────────────────
def generate(system, user, temperature=0.3, max_tokens=1100, timeout=180):
    """Generate one answer locally. Raises LlmNotReady if the brain isn't set up."""
    s = get_settings()
    base = s['base_url'].rstrip('/')
    model = s['model']
    st = status()
    if not st.get('ready'):
        raise LlmNotReady(st.get('detail') or 'The offline AI brain is not set up yet.')
    try:
        if _is_ollama(base):
            resp = _post(base + '/api/chat', {
                'model': model, 'stream': False,
                'options': {'temperature': temperature, 'num_predict': max_tokens},
                'messages': [{'role': 'system', 'content': system},
                             {'role': 'user', 'content': user}],
            }, timeout=timeout)
            return (resp.get('message') or {}).get('content', '').strip()
        resp = _post(base + '/chat/completions', {
            'model': model, 'temperature': temperature, 'max_tokens': max_tokens,
            'messages': [{'role': 'system', 'content': system},
                         {'role': 'user', 'content': user}],
        }, timeout=timeout)
        return (resp['choices'][0]['message']['content'] or '').strip()
    except LlmError:
        raise
    except (urllib.error.URLError, OSError, TimeoutError, KeyError, ValueError) as exc:
        raise LlmError('The local AI brain could not answer: %s' % exc)
