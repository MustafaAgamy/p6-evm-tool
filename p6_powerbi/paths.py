"""Fixed output locations for the Power BI live dataset + dashboard.

Everything lives under the per-user app-data dir (one per OS user, gitignored),
never in the repo. Folders are created on demand.
"""
import os
from utils import app_data_dir


def powerbi_dir():
    path = os.path.join(app_data_dir(), 'powerbi')
    os.makedirs(path, exist_ok=True)
    return path


def dataset_dir():
    path = os.path.join(powerbi_dir(), 'dataset')
    os.makedirs(path, exist_ok=True)
    return path


def dashboard_dir():
    path = os.path.join(powerbi_dir(), 'dashboard')
    os.makedirs(path, exist_ok=True)
    return path


def dataset_workbook():
    """The single Excel workbook Power BI connects to (live)."""
    return os.path.join(dataset_dir(), 'p6evm.xlsx')
