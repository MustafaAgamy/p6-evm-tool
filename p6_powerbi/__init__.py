"""Power BI live dashboards — isolated package.

Turns everything the tool already computed (read from the SQLite DB) into a
star-schema Excel workbook Power BI connects to, and generates a ready-made
PBIP dashboard project pointed at it. Read path only — never recomputes a
number, never touches p6_evm/.
"""

from p6_powerbi.dataset import write_dataset

__all__ = ['write_dataset']
