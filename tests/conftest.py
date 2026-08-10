"""Shared fixtures for the P6 EVM Tool test suite."""
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

import pytest

# Ensure project root is importable (pytest.ini sets pythonpath=. but this
# also helps editors and direct test runs).
sys.path.insert(0, str(Path(__file__).parent.parent))

import db


@pytest.fixture(scope='session')
def xml_path():
    """Path to the minimal valid P6 XML fixture."""
    return Path(__file__).parent / 'fixtures' / 'minimal.xml'


@pytest.fixture
def test_config():
    """Single-category config with weight 1.0 — gives exact, predictable EVM math."""
    return {
        'categories': [
            {'name': 'Construction', 'weight': 1.0, 'wbs_match': 'Phase I Construction Works'}
        ]
    }


def _redirect_powerbi(tmp_path, monkeypatch):
    """Keep the Power BI live dataset/dashboard out of the real %APPDATA% in tests."""
    try:
        import p6_powerbi.paths as _pbi_paths
        monkeypatch.setattr(_pbi_paths, 'app_data_dir', lambda: str(tmp_path))
    except Exception:
        pass


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Redirect all DB I/O to a temp directory; return the directory path."""
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    monkeypatch.setattr(db, 'schedules_dir', lambda: str(tmp_path / 'schedules'))
    (tmp_path / 'schedules').mkdir()
    _redirect_powerbi(tmp_path, monkeypatch)
    db.init_db()
    return tmp_path


@pytest.fixture
def test_server(tmp_path, monkeypatch):
    """Start a real HTTP server backed by a fresh temp DB; yield the port number."""
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    monkeypatch.setattr(db, 'schedules_dir', lambda: str(tmp_path / 'schedules'))
    (tmp_path / 'schedules').mkdir()
    _redirect_powerbi(tmp_path, monkeypatch)

    import server as srv
    httpd = srv.make_server()
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield port
    httpd.shutdown()
