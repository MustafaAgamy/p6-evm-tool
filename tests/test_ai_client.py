"""The stdlib Messages API client — every failure mode maps to a friendly AiError.
The network call is injected (`_opener`) so tests never touch the internet."""
import io
import json
import urllib.error

import pytest

from p6_ai.client import call_claude, AiError


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode('utf-8')

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok(payload):
    def opener(req, timeout=None):
        return _Resp(payload)
    return opener


def test_success_returns_parsed_structured_json():
    ai_json = {'project_type': 'Rail', 'illogical': []}
    payload = {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': json.dumps(ai_json)}]}
    out = call_claude({'model': 'm'}, 'key', _opener=_ok(payload))
    assert out == ai_json


def test_thinking_block_is_skipped_and_text_block_parsed():
    ai_json = {'ok': True}
    payload = {'stop_reason': 'end_turn', 'content': [
        {'type': 'thinking', 'thinking': ''},
        {'type': 'text', 'text': json.dumps(ai_json)}]}
    assert call_claude({'model': 'm'}, 'key', _opener=_ok(payload)) == ai_json


def test_no_key_raises():
    with pytest.raises(AiError) as e:
        call_claude({}, '', _opener=_ok({}))
    assert e.value.code == 'no_key'


def test_http_401_is_auth_error():
    def opener(req, timeout=None):
        raise urllib.error.HTTPError('http://x', 401, 'Unauthorized', {}, io.BytesIO(b'bad key'))
    with pytest.raises(AiError) as e:
        call_claude({'model': 'm'}, 'key', _opener=opener)
    assert e.value.code == 'auth'


def test_network_error_is_friendly():
    def opener(req, timeout=None):
        raise urllib.error.URLError('offline')
    with pytest.raises(AiError) as e:
        call_claude({'model': 'm'}, 'key', _opener=opener)
    assert e.value.code == 'network'


def test_refusal_stop_reason():
    payload = {'stop_reason': 'refusal', 'content': []}
    with pytest.raises(AiError) as e:
        call_claude({'model': 'm'}, 'key', _opener=_ok(payload))
    assert e.value.code == 'refusal'


def test_unparseable_text_raises_parse():
    payload = {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'not json at all'}]}
    with pytest.raises(AiError) as e:
        call_claude({'model': 'm'}, 'key', _opener=_ok(payload))
    assert e.value.code == 'parse'


# ── NET-5: a timeout / dropped connection is a network problem, not a "bad response" ──
class _SlowResp(_Resp):
    def __init__(self, exc):
        super().__init__({})
        self._exc = exc

    def read(self):
        raise self._exc


@pytest.mark.parametrize('exc, where', [
    (TimeoutError('timed out'), 'open'),                       # connect / first byte timed out
    (urllib.error.URLError(TimeoutError('timed out')), 'open'),
    (TimeoutError('The read operation timed out'), 'read'),    # the answer stopped arriving
])
def test_timeout_says_the_service_did_not_answer_in_time(exc, where):
    def opener(req, timeout=None):
        if where == 'open':
            raise exc
        return _SlowResp(exc)
    with pytest.raises(AiError) as e:
        call_claude({'model': 'm'}, 'key', _opener=opener)
    assert e.value.code == 'network'
    assert 'did not answer in time' in str(e.value)
    assert 'unexpected response' not in str(e.value)


@pytest.mark.parametrize('exc', [
    ConnectionResetError(10054, 'An existing connection was forcibly closed'),
    __import__('http.client').client.RemoteDisconnected('Remote end closed connection'),
    __import__('http.client').client.IncompleteRead(b''),
])
def test_dropped_connection_mid_answer_is_a_friendly_network_error(exc):
    def opener(req, timeout=None):
        return _SlowResp(exc)
    with pytest.raises(AiError) as e:
        call_claude({'model': 'm'}, 'key', _opener=opener)
    assert e.value.code == 'network'
    assert 'Could not reach the AI service' in str(e.value)
