def _read_text(path):
    for enc in ('cp1252', 'utf-8'):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, encoding='latin-1') as f:
        return f.read()


def read_xer_tables(path):
    """Parse an XER file into {table_name: [row_dict, ...]}."""
    tables = {}
    current = None
    fields = []
    for line in _read_text(path).splitlines():
        if not line:
            continue
        parts = line.split('\t')
        tag = parts[0]
        if tag == '%T':
            current = parts[1]
            fields = []
            tables[current] = []
        elif tag == '%F':
            fields = parts[1:]
        elif tag == '%R' and current is not None:
            values = parts[1:]
            row = {}
            for i, name in enumerate(fields):
                row[name] = values[i] if i < len(values) else ''
            tables[current].append(row)
        # ERMHDR, %E, and anything else are ignored
    return tables
