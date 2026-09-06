"""Tests for named Special Report template persistence."""
import db
from p6_special import templates as T


def test_save_and_list(temp_db):
    pid = db.upsert_project('P1', 'X')
    rec = T.save_template(pid, {'name': 'October Board', 'item_ids': ['evm:planned_pct']})
    assert rec['id'] == 'sr1'
    lst = T.list_templates(pid)
    assert len(lst) == 1
    assert lst[0]['name'] == 'October Board'
    assert lst[0]['item_ids'] == ['evm:planned_pct']


def test_second_template_gets_new_id(temp_db):
    pid = db.upsert_project('P1', 'X')
    T.save_template(pid, {'name': 'A'})
    r2 = T.save_template(pid, {'name': 'B'})
    assert r2['id'] == 'sr2'
    assert len(T.list_templates(pid)) == 2


def test_update_existing(temp_db):
    pid = db.upsert_project('P1', 'X')
    r = T.save_template(pid, {'name': 'A', 'item_ids': []})
    T.save_template(pid, {'id': r['id'], 'name': 'A2', 'item_ids': ['evm:spi'], 'mode': 'dark'})
    lst = T.list_templates(pid)
    assert len(lst) == 1
    assert lst[0]['name'] == 'A2'
    assert lst[0]['item_ids'] == ['evm:spi']
    assert lst[0]['mode'] == 'dark'


def test_get_template(temp_db):
    pid = db.upsert_project('P1', 'X')
    r = T.save_template(pid, {'name': 'A'})
    assert T.get_template(pid, r['id'])['name'] == 'A'
    assert T.get_template(pid, 'nope') is None


def test_delete(temp_db):
    pid = db.upsert_project('P1', 'X')
    r = T.save_template(pid, {'name': 'A'})
    T.delete_template(pid, r['id'])
    assert T.list_templates(pid) == []


def test_does_not_clobber_other_settings(temp_db):
    pid = db.upsert_project('P1', 'X')
    db.save_project_settings(pid, {'location': {'lat': 1.0, 'lon': 2.0}})
    T.save_template(pid, {'name': 'A'})
    s = db.get_project_settings(pid)
    assert 'location' in s          # untouched
    assert 'special_reports' in s   # added alongside
