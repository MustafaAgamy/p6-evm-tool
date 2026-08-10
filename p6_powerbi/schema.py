"""Single source of truth for the Power BI star schema.

Both the Excel dataset writer (dataset.py) and the semantic-model generator
(pbip.py) read from here so column names/order/types can never drift apart.
A test asserts the written workbook headers match TABLES exactly.

dtype is the Analysis Services (TMSL) data type name.
"""

# table -> ordered list of (column_name, tmsl_dtype)
TABLES = {
    'dim_project': [
        ('project_id', 'int64'),
        ('p6_project_id', 'string'),
        ('project_name', 'string'),
    ],
    'dim_snapshot': [
        ('snapshot_id', 'int64'),
        ('project_id', 'int64'),
        ('project_name', 'string'),
        ('data_date', 'dateTime'),
        ('imported_at', 'dateTime'),
        ('activity_count', 'int64'),
    ],
    'fact_metrics': [
        ('snapshot_id', 'int64'),
        ('project_id', 'int64'),
        ('project_name', 'string'),
        ('data_date', 'dateTime'),
        ('pv', 'double'),
        ('ev', 'double'),
        ('ac', 'double'),
        ('spi', 'double'),
        ('cpi', 'double'),
        ('delay_days', 'int64'),
        ('overall_planned_pct', 'double'),
        ('overall_actual_pct', 'double'),
        ('variance', 'double'),
    ],
    'fact_category': [
        ('snapshot_id', 'int64'),
        ('project_id', 'int64'),
        ('project_name', 'string'),
        ('data_date', 'dateTime'),
        ('category', 'string'),
        ('weight', 'double'),
        ('planned_pct', 'double'),
        ('actual_pct', 'double'),
        ('bac', 'double'),
        ('ac', 'double'),
        ('activity_count', 'int64'),
    ],
}

# table -> list of (measure_name, DAX, formatString)
MEASURES = {
    'fact_metrics': [
        ('SPI', 'AVERAGE(fact_metrics[spi])', '0.00'),
        ('CPI', 'AVERAGE(fact_metrics[cpi])', '0.00'),
        ('Delay (wd)', 'MAX(fact_metrics[delay_days])', '0'),
        ('Complete %', 'AVERAGE(fact_metrics[overall_actual_pct])', '0.0%'),
        ('Planned %', 'AVERAGE(fact_metrics[overall_planned_pct])', '0.0%'),
    ],
    'fact_category': [
        ('Actual', 'AVERAGE(fact_category[actual_pct])', '0.0%'),
        ('Planned', 'AVERAGE(fact_category[planned_pct])', '0.0%'),
    ],
}

# many-side -> one-side: (fromTable, fromColumn, toTable, toColumn)
RELATIONSHIPS = [
    ('fact_metrics', 'project_id', 'dim_project', 'project_id'),
    ('fact_category', 'project_id', 'dim_project', 'project_id'),
]


def columns(table):
    return [name for name, _ in TABLES[table]]


def measure_names(table):
    return [name for name, _, _ in MEASURES.get(table, [])]


def all_field_names(table):
    """Every column and measure a visual may legally reference on this table."""
    return set(columns(table)) | set(measure_names(table))
