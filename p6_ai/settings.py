"""Per-user AI settings (API key + model/config), stored outside the repo.

The Anthropic API key lives in ``%APPDATA%/Controlyx/ai_settings.json`` — the same
per-user area as the database — never in the bundle or the repo. It leaves the
machine only in the Authorization header of the review call the user triggers.
"""
import json
import os

from utils import app_data_dir

# Cost-efficient high-quality default for construction reasoning; overridable via
# ai_settings.json "model" (e.g. "claude-opus-5" for maximum quality).
DEFAULT_MODEL = 'claude-sonnet-5'


def _default_path():
    return os.path.join(app_data_dir(), 'ai_settings.json')


def _load(path):
    p = path or _default_path()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(data, path):
    p = path or _default_path()
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def get_api_key(path=None):
    key = (_load(path).get('api_key') or '').strip()
    return key or None


def set_api_key(key, path=None):
    data = _load(path)
    data['api_key'] = (key or '').strip()
    _save(data, path)


def has_api_key(path=None):
    return bool(get_api_key(path))


def get_config(path=None):
    """Model + tunable score config (the `ai` block); falls back to defaults."""
    data = _load(path)
    return {
        'model': data.get('model') or DEFAULT_MODEL,
        'effort': data.get('effort') or 'medium',
        'ai': data.get('ai') or {},
    }
