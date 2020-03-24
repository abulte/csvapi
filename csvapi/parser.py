import os
import uuid

import agate
import agatesql  # noqa
import cchardet as chardet

from csvapi.utils import add_entry_to_sys_db
from csvapi.type_tester import agate_tester

SNIFF_LIMIT = 4096


def is_binary(filepath):
    with os.popen('file {} -b --mime-type'.format(filepath)) as proc:
        return 'text/plain' not in proc.read().lower()


def detect_encoding(filepath):
    with open(filepath, 'rb') as f:
        return chardet.detect(f.read()).get('encoding')


def from_csv(filepath, encoding='utf-8', sniff_limit=SNIFF_LIMIT):
    """Try first w/ sniffing and then w/o sniffing if it fails"""
    try:
        return agate.Table.from_csv(filepath, sniff_limit=sniff_limit, encoding=encoding, column_types=agate_tester())
    except ValueError:
        return agate.Table.from_csv(filepath, encoding=encoding, column_types=agate_tester())


def from_excel(filepath):
    import agateexcel  # noqa
    return agate.Table.from_xls(filepath, column_types=agate_tester())


def to_sql(table, urlhash, filehash, storage):
    db_name = str(uuid.uuid4())
    db_dsn = f"sqlite:///{storage}/{db_name}.db"
    table.to_sql(db_dsn, urlhash, overwrite=True)
    add_entry_to_sys_db(db_name, urlhash, filehash)


def parse(filepath, urlhash, filehash, storage, encoding=None, sniff_limit=SNIFF_LIMIT):
    if is_binary(filepath):
        table = from_excel(filepath)
    else:
        encoding = detect_encoding(filepath) if not encoding else encoding
        table = from_csv(filepath, encoding=encoding, sniff_limit=sniff_limit)
    return to_sql(table, urlhash, filehash, storage)