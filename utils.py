import sys
import os

# ── Branding ────────────────────────────────────────────────────────────────
# Single source of truth for the product name shown to users (window title,
# headers, CLI banner). Internal identifiers — the ``p6_evm`` package, the
# ``%APPDATA%\\P6EVMTool`` data folder, ``p6evm.db`` and the UI localStorage
# keys — intentionally keep their original names so existing installs keep
# their local database, cached schedules and settings.
APP_NAME = 'Controlyx'                     # brand / product name
APP_EDITION = '2026'                       # edition (year)
APP_TITLE = f'{APP_NAME} {APP_EDITION}'    # full display name, e.g. "Controlyx 2026"


def resource_path(rel):
    """Resolve a path relative to the project root — works in dev and PyInstaller bundle."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)

def exe_dir():
    """Directory next to the .exe (prod) or project root (dev). Legacy — prefer app_data_dir()."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _migrate_data_dir(legacy, new):
    """Return the per-user data dir to use, migrating the legacy 'P6EVMTool'
    folder to the branded 'Controlyx' one on first access. If the new dir
    already exists or there is no legacy dir, nothing moves. If the rename
    fails (e.g. the folder is in use), fall back to the legacy dir in place so
    existing data (DB, cached schedules, knowledge base, settings) is never
    lost — a whole-directory rename moves every sub-path together."""
    if os.path.isdir(new) or not os.path.isdir(legacy):
        return new
    try:
        os.rename(legacy, new)
        return new
    except OSError:
        return legacy


def app_data_dir():
    """Per-user app data directory. Each OS user gets an isolated folder.

    Rebranded from the legacy 'P6EVMTool' name to 'Controlyx'; any existing
    per-user data is migrated automatically the first time this runs."""
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
        path = _migrate_data_dir(os.path.join(base, 'P6EVMTool'),
                                 os.path.join(base, 'Controlyx'))
    else:
        path = _migrate_data_dir(os.path.expanduser('~/.p6evmtool'),
                                 os.path.expanduser('~/.controlyx'))
    os.makedirs(path, exist_ok=True)
    return path

def schedules_dir():
    """Folder where cached XML copies are stored."""
    path = os.path.join(app_data_dir(), 'schedules')
    os.makedirs(path, exist_ok=True)
    return path
