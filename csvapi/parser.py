import os

import agate
import agatesql  # noqa
import cchardet as chardet

from csvapi.utils import get_db_info
from csvapi.type_tester import agate_tester

SNIFF_LIMIT = 4096
CSV_FILETYPES = ('text/plain', 'application/csv')


def detect_type(filepath):
    with os.popen(f'file {filepath} -b --mime-type') as proc:
        return proc.read().lower()


def detect_encoding(filepath):
    with open(filepath, 'rb') as f:
        return chardet.detect(f.read()).get('encoding')


def from_csv(filepath, encoding='utf-8', sniff_limit=SNIFF_LIMIT):
    """Try first w/ sniffing and then w/o sniffing if it fails,
    and then again by forcing ';' delimiter w/o sniffing"""
    kwargs = {
        'sniff_limit': sniff_limit,
        'encoding': encoding,
        'column_types': agate_tester()
    }
    try:
        return agate.Table.from_csv(filepath, **kwargs)
    except ValueError:
        try:
            kwargs.pop('sniff_limit')
            return agate.Table.from_csv(filepath, **kwargs)
        except ValueError:
            kwargs['delimiter'] = ';'
            return agate.Table.from_csv(filepath, **kwargs)


def from_excel(filepath, xlsx=False):
    # Function exists to prevent side-effects after monckey patching with import
    import agateexcel  # noqa
    if xlsx:
        return agate.Table.from_xlsx(filepath, column_types=agate_tester())
    return agate.Table.from_xls(filepath, column_types=agate_tester())


def to_sql(table, urlhash, storage):
    db_info = get_db_info(urlhash, storage=storage)
    table.to_sql(db_info['dsn'], db_info['db_name'], overwrite=True)


def parse(filepath, urlhash, storage, encoding=None, sniff_limit=SNIFF_LIMIT):
    file_type = detect_type(filepath)
    if 'application/vnd.ms-excel' in file_type:
        table = from_excel(filepath)
    elif 'application/vnd.openxml' in file_type:
        table = from_excel(filepath, xlsx=True)
    elif any([supported in file_type for supported in CSV_FILETYPES]):
        encoding = detect_encoding(filepath) if not encoding else encoding
        table = from_csv(filepath, encoding=encoding, sniff_limit=sniff_limit)
    else:
        raise Exception(f'Unsupported file type {file_type}')
    return to_sql(table, urlhash, storage)
