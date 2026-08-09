"""Anthropic Messages API client — stdlib ``urllib`` only.

The rest of the app is dependency-light and already reaches external services
(Open-Meteo weather, geocoding) with stdlib HTTP, and ships as a lean offline
PyInstaller ``.exe``. Adding the full ``anthropic`` SDK for one structured-output
call would bloat the bundle and complicate the build, so this makes the single
``POST /v1/messages`` call directly. It returns the parsed JSON object the model
produced under structured outputs.
"""
import json
import urllib.error
import urllib.request

API_URL = 'https://api.anthropic.com/v1/messages'
API_VERSION = '2023-06-01'


class AiError(Exception):
    """A user-facing AI failure. ``code`` classifies it; ``str`` is the message."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _friendly_http(status, body_text):
    if status in (401, 403):
        return AiError('auth', 'The AI API key was rejected. Check your Anthropic API key in Settings.')
    if status == 429:
        return AiError('rate_limit', 'The AI service is rate-limited right now — wait a moment and try again.')
    if status == 400:
        return AiError('bad_request', f'The AI request was rejected: {body_text[:300]}')
    if status >= 500:
        return AiError('server', 'The AI service had a temporary error — try again shortly.')
    return AiError('http', f'AI request failed (HTTP {status}).')


def call_claude(request, api_key, *, timeout=120, _opener=None):
    """POST ``request`` to the Messages API and return the parsed structured JSON.

    ``_opener`` is an injection seam for tests (defaults to ``urllib.request.urlopen``).
    Raises :class:`AiError` for every failure mode, with a plain-language message.
    """
    if not api_key:
        raise AiError('no_key', 'No Anthropic API key is set. Add one in Settings to use the AI review.')

    data = json.dumps(request).encode('utf-8')
    http_req = urllib.request.Request(API_URL, data=data, method='POST', headers={
        'x-api-key': api_key,
        'anthropic-version': API_VERSION,
        'content-type': 'application/json',
    })
    opener = _opener or urllib.request.urlopen

    try:
        with opener(http_req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = ''
        try:
            body = e.read().decode('utf-8', 'replace')
        except Exception:
            pass
        raise _friendly_http(e.code, body)
    except urllib.error.URLError:
        raise AiError('network', 'Could not reach the AI service. Check your internet connection and try again.')
    except (ValueError, TimeoutError):
        raise AiError('bad_response', 'The AI service returned an unexpected response. Try again.')

    if payload.get('stop_reason') == 'refusal':
        raise AiError('refusal', 'The AI declined to review this schedule. Nothing was changed.')

    for block in payload.get('content', []):
        if block.get('type') == 'text':
            try:
                return json.loads(block['text'])
            except (ValueError, KeyError):
                raise AiError('parse', 'The AI response could not be read. Try running the review again.')
    raise AiError('empty', 'The AI returned no review. Try again.')
