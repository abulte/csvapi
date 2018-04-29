import os
import logging


import agate
import agatesql  # noqa

from csvapi.utils import get_db_info

log = logging.getLogger('__name__')

SNIFF_LIMIT = 2048


def is_binary(filepath):
    with os.popen('file {} -b --mime-type'.format(filepath)) as proc:
        return 'text/plain' not in proc.read().lower()


def detect_encoding(filepath):
    with os.popen('file {} -b --mime-encoding'.format(filepath)) as proc:
        return proc.read()


def from_csv(filepath, encoding='utf-8'):
    return agate.Table.from_csv(filepath, sniff_limit=SNIFF_LIMIT, encoding=encoding)


def from_excel(filepath):
    import agateexcel  # noqa
    return agate.Table.from_xls(filepath)


def to_sql(table, _hash, storage):
    db_info = get_db_info(storage, _hash)
    table.to_sql(db_info['dsn'], db_info['db_name'], overwrite=True)


def parse(filepath, _hash, storage='.'):
    if is_binary(filepath):
        table = from_excel(filepath)
    else:
        encoding = detect_encoding(filepath)
        table = from_csv(filepath, encoding=encoding)
    return to_sql(table, _hash, storage)
