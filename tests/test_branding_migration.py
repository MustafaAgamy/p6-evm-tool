"""Tests for the Controlyx rebrand storage migration.

The per-user data folder (`P6EVMTool` → `Controlyx`) and the database
(`p6evm.db` → `controlyx.db`) must migrate to the branded names without losing
data, and fall back safely to the legacy location if the rename cannot happen.
"""
import os
import sqlite3

import db
import utils


# ── DB file migration (db._db_path) ─────────────────────────────────────────

def test_db_path_uses_branded_name_on_fresh_install(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    assert db._db_path() == os.path.join(str(tmp_path), 'controlyx.db')


def test_db_path_migrates_legacy_db_in_place(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    legacy = tmp_path / 'p6evm.db'
    conn = sqlite3.connect(str(legacy))
    conn.execute('CREATE TABLE marker (v TEXT)')
    conn.execute("INSERT INTO marker VALUES ('kept')")
    conn.commit()
    conn.close()

    path = db._db_path()

    assert path == str(tmp_path / 'controlyx.db')
    assert (tmp_path / 'controlyx.db').exists()
    assert not legacy.exists()
    conn = sqlite3.connect(path)
    assert conn.execute('SELECT v FROM marker').fetchone()[0] == 'kept'
    conn.close()


def test_db_path_never_overwrites_existing_branded_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'app_data_dir', lambda: str(tmp_path))
    (tmp_path / 'controlyx.db').write_text('new')
    (tmp_path / 'p6evm.db').write_text('legacy')
    assert db._db_path() == str(tmp_path / 'controlyx.db')
    assert (tmp_path / 'p6evm.db').read_text() == 'legacy'  # left untouched


# ── Data folder migration (utils.app_data_dir) ──────────────────────────────

def test_app_data_dir_migrates_legacy_folder(tmp_path, monkeypatch):
    # Force the POSIX branch and resolve ~ under tmp_path via $HOME.
    monkeypatch.setattr(utils.sys, 'platform', 'linux')
    monkeypatch.setenv('HOME', str(tmp_path))
    legacy = tmp_path / '.p6evmtool'
    legacy.mkdir()
    (legacy / 'controlyx.db').write_text('data')

    path = utils.app_data_dir()

    assert path == str(tmp_path / '.controlyx')
    assert (tmp_path / '.controlyx' / 'controlyx.db').exists()
    assert not legacy.exists()


def test_app_data_dir_fresh_when_no_legacy(tmp_path, monkeypatch):
    monkeypatch.setattr(utils.sys, 'platform', 'linux')
    monkeypatch.setenv('HOME', str(tmp_path))
    path = utils.app_data_dir()
    assert path == str(tmp_path / '.controlyx')
    assert os.path.isdir(path)
