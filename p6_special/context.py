"""Parse-free result context for Special Report.

Gives providers cheap, memoized access to a project's results straight from the
DB (EVM, Audit, Calendar, settings, snapshots, extras) plus lazy XML
parse/compute for the features that must recompute (Update Analysis,
Constructability). Providers go through the context — they never touch the DB
or the parser directly.

``computed()`` reproduces exactly the config + compute used at import
(``config.json`` + ``auto_categories(data)`` + ``build_wbs_classifier``), so any
recomputed metric ties out to what is stored for the snapshot.
"""
import json
import os

import db
from utils import resource_path


class SpecialContext:
    def __init__(self, project_id, snapshot_id=None, inputs=None, mode='light'):
        self.project_id = project_id
        self._sid = snapshot_id
        # Extra user-attached inputs keyed by role, e.g.
        # {'baseline': 'C:/.../baseline.xer', 'previous': 'C:/.../update_sep.xml'}.
        self.inputs = dict(inputs or {})
        # Appearance mode for reused feature-report HTML (set per render).
        self.mode = mode or 'light'
        self._cache = {}

    # ── memo ────────────────────────────────────────────────────────────────
    def memo(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    # ── DB-backed (parse-free) ───────────────────────────────────────────────
    @property
    def evm(self):
        return self.memo('evm', lambda: db.get_project_result(self.project_id))

    @property
    def snapshot_id(self):
        if self._sid is None:
            evm = self.evm
            self._sid = (evm or {}).get('_snapshot_id') or db.get_latest_snapshot_id(self.project_id)
        return self._sid

    @property
    def audit(self):
        return self.memo('audit', lambda: db.get_audit_modules_for_snapshot(self.snapshot_id))

    @property
    def calendar(self):
        return self.memo('calendar', lambda: db.get_calendar_audit(self.snapshot_id))

    @property
    def settings(self):
        return self.memo('settings', lambda: db.get_project_settings(self.project_id) or {})

    @property
    def weather(self):
        return (self.settings or {}).get('last_weather')

    @property
    def extras(self):
        return self.memo('extras', lambda: db.get_evm_extras(self.snapshot_id))

    @property
    def snapshots(self):
        return self.memo('snapshots', lambda: db.get_project_snapshots(self.project_id))

    @property
    def project_name(self):
        return (self.evm or {}).get('project_name') or 'Project'

    @property
    def data_date(self):
        return (self.evm or {}).get('data_date')

    @property
    def meta(self):
        return {
            'project_name': self.project_name,
            'data_date': self.data_date,
            'snapshot_id': self.snapshot_id,
        }

    @property
    def xml_path(self):
        def _resolve():
            evm = self.evm or {}
            return db.resolve_xml_path(evm.get('_original_path'), evm.get('_cached_path'))
        return self.memo('xml_path', _resolve)

    def has_xml(self):
        p = self.xml_path
        return bool(p and os.path.exists(p))

    @property
    def config(self):
        def _load():
            with open(resource_path('config.json')) as f:
                return json.load(f)
        return self.memo('config', _load)

    # ── lazy parse / compute (recompute features) ────────────────────────────
    def parsed(self):
        """The parsed ScheduleData for the open file (memoized). None if no file."""
        def _parse():
            if not self.has_xml():
                return None
            from p6_evm.parser import parse_file
            return parse_file(self.xml_path)
        return self.memo('parsed', _parse)

    # ── user-attached inputs (two-/three-file features) ──────────────────────
    def input_path(self, role):
        """Path the user attached for a required ``role`` (or None)."""
        p = self.inputs.get(role)
        return p if (p and os.path.exists(p)) else None

    def has_input(self, role):
        return self.input_path(role) is not None

    def parsed_input(self, role):
        """Parsed ScheduleData for an attached input file (memoized), or None."""
        def _parse():
            p = self.input_path(role)
            if not p:
                return None
            from p6_evm.parser import parse_file
            return parse_file(p)
        return self.memo(f'parsed_input:{role}', _parse)

    def computed(self):
        """Full EVM result *including* ``records`` (memoized), matching import."""
        def _compute():
            data = self.parsed()
            if data is None:
                return None
            from p6_evm.metrics import compute
            from p6_evm.classify import auto_categories, build_wbs_classifier
            cfg = dict(self.config)
            cfg['categories'] = auto_categories(data)
            return compute(data, cfg, overrides={}, classifier=build_wbs_classifier(data))
        return self.memo('computed', _compute)
