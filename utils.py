import sys
import os

# ── Branding ────────────────────────────────────────────────────────────────
# Single source of truth for the product name shown to users (window title,
# headers, CLI banner). Some internal identifiers — the ``p6_evm`` package and
# the UI localStorage keys — intentionally keep their original names so imports
# and existing per-user UI state don't break. The per-user data folder is
# ``.controlyx`` (holding ``controlyx.db``), migrated automatically from the
# older ``P6EVMTool`` / ``Controlyx`` / ``.p6evmtool`` folders on first run.
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

def _migrate_data_dir(legacies, new):
    """Return the per-user data dir to use (`new`), migrating the first existing
    legacy folder (tried in `legacies` order) into it on first access. If `new`
    already exists, or no legacy folder is found, nothing moves. If the rename
    fails (e.g. the folder is in use), fall back to that legacy dir in place so
    existing data (DB, cached schedules, knowledge base, settings) is never
    lost — a whole-directory rename moves every sub-path together."""
    if os.path.isdir(new):
        return new
    for legacy in legacies:
        if os.path.isdir(legacy):
            try:
                os.rename(legacy, new)
                return new
            except OSError:
                return legacy
    return new


def app_data_dir():
    """Per-user app data directory. Each OS user gets an isolated folder.

    The folder is `.controlyx` (Windows: %APPDATA%/.controlyx; Mac/Linux:
    ~/.controlyx). Data from the older 'Controlyx' / 'P6EVMTool' / '.p6evmtool'
    folders is migrated into it automatically the first time this runs."""
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
        path = _migrate_data_dir([os.path.join(base, 'Controlyx'),
                                  os.path.join(base, 'P6EVMTool')],
                                 os.path.join(base, '.controlyx'))
    else:
        home = os.environ.get('HOME', os.path.expanduser('~'))
        path = _migrate_data_dir([os.path.join(home, '.p6evmtool')],
                                 os.path.join(home, '.controlyx'))
    os.makedirs(path, exist_ok=True)
    return path

def schedules_dir():
    """Folder where cached XML copies are stored."""
    path = os.path.join(app_data_dir(), 'schedules')
    os.makedirs(path, exist_ok=True)
    return path
