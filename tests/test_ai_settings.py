"""Per-user AI settings — the API key round-trips through a JSON file and never
falls back to a bundled value."""
from p6_ai import settings


def test_round_trip(tmp_path):
    p = str(tmp_path / 'ai.json')
    assert settings.get_api_key(p) is None
    assert settings.has_api_key(p) is False
    settings.set_api_key('sk-test-123', p)
    assert settings.get_api_key(p) == 'sk-test-123'
    assert settings.has_api_key(p) is True


def test_blank_key_reads_as_none(tmp_path):
    p = str(tmp_path / 'ai.json')
    settings.set_api_key('   ', p)
    assert settings.get_api_key(p) is None
    assert settings.has_api_key(p) is False


def test_config_defaults(tmp_path):
    cfg = settings.get_config(str(tmp_path / 'missing.json'))
    assert cfg['model'] == 'claude-sonnet-5'
    assert cfg['effort'] == 'medium'
    assert cfg['ai'] == {}
