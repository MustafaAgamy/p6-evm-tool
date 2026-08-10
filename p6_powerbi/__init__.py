"""Power BI live dashboards — isolated package.

Turns everything the tool already computed (read from the SQLite DB) into a
star-schema Excel workbook Power BI connects to, and generates a ready-made
PBIP dashboard project pointed at it. Read path only — never recomputes a
number, never touches p6_evm/.
"""

from p6_powerbi.dataset import write_dataset
from p6_powerbi.pbip import generate_pbip
from p6_powerbi.validate import validate_pbip

__all__ = ['write_dataset', 'generate_pbip', 'validate_pbip', 'build_all']


def build_all(workbook_path=None):
    """Refresh the dataset, (re)generate the PBIP, and structurally validate it.

    Returns {'dataset': path, 'pbip': path, 'errors': [...]}.
    """
    ds = write_dataset(workbook_path=workbook_path)
    pbip_path = generate_pbip(workbook_path=ds['workbook'])
    errors = validate_pbip(pbip_path)
    return {'dataset': ds['workbook'], 'pbip': pbip_path, 'errors': errors}
