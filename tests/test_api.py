import os
import uuid
from pathlib import Path

import pytest
from aioresponses import aioresponses

from csvapi.utils import get_hash
from csvapi.webservice import app as csvapi_app

MOCK_CSV_URL = 'http://domain.com/file.csv'
MOCK_CSV_URL_FILTERS = 'http://domain.com/filters.csv'
MOCK_CSV_HASH_FILTERS = get_hash(MOCK_CSV_URL_FILTERS)
MOCK_CSV_HASH = get_hash(MOCK_CSV_URL)
DB_ROOT_DIR = './tests/dbs'


pytestmark = pytest.mark.asyncio


@pytest.fixture
def rmock():
    with aioresponses() as m:
        yield m


@pytest.fixture
def app():
    csvapi_app.config.update({
        'DB_ROOT_DIR': DB_ROOT_DIR,
        'CSV_CACHE_ENABLED': False,
    })
    yield csvapi_app
    [db.unlink() for db in Path(DB_ROOT_DIR).glob('*.db')]


@pytest.fixture
def client(app):
    yield app.test_client()


@pytest.fixture
def csv():
    return '''col a<sep>col b<sep>col c
data à1<sep>data b1<sep>z
data ª2<sep>data b2<sep>a
'''


@pytest.fixture
def csv_col_mismatch():
    return '''col a<sep>col b
data à1<sep>data b1<sep>2
data ª2<sep>data b2<sep>4<sep>
'''


@pytest.fixture
def csv_hour():
    return '''id<sep>hour
a<sep>12:30
b<sep>9:15
c<sep>09:45
'''


@pytest.fixture
def csv_filters():
    return '''id,hour,value
first,12:30,1
second,9:15,2
third,09:45,3
'''


@pytest.fixture
def csv_siren_siret():
    return """id<sep>siren<sep>siret
a<sep>130025265<sep>13002526500013
b<sep>522816651<sep>52281665100056
"""


def random_url():
    return f"https://example.com/{uuid.uuid4()}.csv"


@pytest.fixture
async def uploaded_csv(rmock, csv, client):
    content = csv.replace('<sep>', ';').encode('utf-8')
    rmock.get(MOCK_CSV_URL, body=content)
    await client.get(f"/apify?url={MOCK_CSV_URL}")


async def test_apify_no_url(rmock, csv, client):
    res = await client.get('/apify')
    assert res.status_code == 400


async def test_apify_wrong_url(rmock, csv, client):
    res = await client.get('/apify?url=notanurl')
    assert res.status_code == 400


async def test_apify(rmock, csv, client):
    rmock.get(MOCK_CSV_URL, status=200, body=csv.encode('utf-8'))
    res = await client.get(f"/apify?url={MOCK_CSV_URL}")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['ok']
    assert 'endpoint' in jsonres
    assert f"/api/{MOCK_CSV_HASH}" in jsonres['endpoint']
    db_path = Path(DB_ROOT_DIR) / f"{MOCK_CSV_HASH}.db"
    assert db_path.exists()


async def test_apify_w_cache(app, rmock, csv, client):
    app.config.update({'CSV_CACHE_ENABLED': True})
    rmock.get(MOCK_CSV_URL, body=csv.encode('utf-8'))
    res = await client.get(f"/apify?url={MOCK_CSV_URL}")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['ok']
    assert 'endpoint' in jsonres
    assert f"/api/{MOCK_CSV_HASH}" in jsonres['endpoint']
    db_path = Path(DB_ROOT_DIR) / f"{MOCK_CSV_HASH}.db"
    assert db_path.exists()
    app.config.update({'CSV_CACHE_ENABLED': False})


async def test_apify_col_mismatch(rmock, csv_col_mismatch, client):
    rmock.get(MOCK_CSV_URL, body=csv_col_mismatch.replace('<sep>', ';').encode('utf-8'))
    res = await client.get(f"/apify?url={MOCK_CSV_URL}")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['ok']


async def test_apify_hour_format(rmock, csv_hour, client):
    content = csv_hour.replace('<sep>', ';').encode('utf-8')
    url = random_url()
    rmock.get(url, body=content)
    await client.get(f"/apify?url={url}")
    res = await client.get(f"/api/{get_hash(url)}")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['columns'] == ['rowid', 'id', 'hour']
    assert jsonres['total'] == 3
    assert jsonres['rows'] == [
        [1, 'a', '12:30'],
        [2, 'b', '9:15'],
        [3, 'c', '09:45'],
    ]


async def test_apify_siren_siret_format(rmock, csv_siren_siret, client):
    content = csv_siren_siret.replace('<sep>', ';').encode('utf-8')
    url = random_url()
    rmock.get(url, body=content)
    await client.get(f"/apify?url={url}")
    res = await client.get(f"/api/{get_hash(url)}")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['columns'] == ['rowid', 'id', 'siren', 'siret']
    assert jsonres['total'] == 2
    assert jsonres['rows'] == [
        [1, 'a', '130025265', '13002526500013'],
        [2, 'b', '522816651', '52281665100056'],
    ]


@pytest.mark.parametrize('separator', [';', ',', '\t'])
@pytest.mark.parametrize('encoding', ['utf-8', 'iso-8859-15', 'iso-8859-1'])
async def test_api(client, rmock, csv, separator, encoding):
    content = csv.replace('<sep>', separator).encode(encoding)
    rmock.get(MOCK_CSV_URL, body=content)
    await client.get(f"/apify?url={MOCK_CSV_URL}")
    res = await client.get(f"/api/{MOCK_CSV_HASH}")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['columns'] == ['rowid', 'col a', 'col b', 'col c']
    assert jsonres['total'] == 2
    assert jsonres['rows'] == [
        [1, 'data à1', 'data b1', 'z'],
        [2, 'data ª2', 'data b2', 'a'],
    ]


async def test_api_limit(client, rmock, uploaded_csv):
    res = await client.get(f"/api/{MOCK_CSV_HASH}?_size=1")
    assert res.status_code == 200
    jsonres = await res.json
    assert len(jsonres['rows']) == 1
    assert jsonres['rows'] == [
        [1, 'data à1', 'data b1', 'z'],
    ]


async def test_api_limit_offset(client, rmock, uploaded_csv):
    res = await client.get(f"/api/{MOCK_CSV_HASH}?_size=1&_offset=1")
    assert res.status_code == 200
    jsonres = await res.json
    assert len(jsonres['rows']) == 1
    assert jsonres['rows'] == [
        [2, 'data ª2', 'data b2', 'a'],
    ]


async def test_api_wrong_limit(client, rmock, uploaded_csv):
    res = await client.get(f"/api/{MOCK_CSV_HASH}?_size=toto")
    assert res.status_code == 400


async def test_api_wrong_shape(client, rmock, uploaded_csv):
    res = await client.get(f"/api/{MOCK_CSV_HASH}?_shape=toto")
    assert res.status_code == 400


async def test_api_objects_shape(client, rmock, uploaded_csv):
    res = await client.get(f"/api/{MOCK_CSV_HASH}?_shape=objects")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['rows'] == [{
            'rowid': 1,
            'col a': 'data à1',
            'col b': 'data b1',
            'col c': 'z',
        }, {
            'rowid': 2,
            'col a': 'data ª2',
            'col b': 'data b2',
            'col c': 'a',
    }]


async def test_api_objects_norowid(client, rmock, uploaded_csv):
    res = await client.get(f"/api/{MOCK_CSV_HASH}?_shape=objects&_rowid=hide")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['rows'] == [{
            'col a': 'data à1',
            'col b': 'data b1',
            'col c': 'z',
        }, {
            'col a': 'data ª2',
            'col b': 'data b2',
            'col c': 'a',
    }]


async def test_api_objects_nototal(client, rmock, uploaded_csv):
    res = await client.get(f"/api/{MOCK_CSV_HASH}?_total=hide")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres.get('total') is None


async def test_api_sort(client, rmock, uploaded_csv):
    res = await client.get(f"/api/{MOCK_CSV_HASH}?_sort=col c")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['rows'] == [
        [2, 'data ª2', 'data b2', 'a'],
        [1, 'data à1', 'data b1', 'z'],
    ]


async def test_api_sort_desc(client, rmock, uploaded_csv):
    res = await client.get(f"/api/{MOCK_CSV_HASH}?_sort_desc=col b")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['rows'] == [
        [2, 'data ª2', 'data b2', 'a'],
        [1, 'data à1', 'data b1', 'z'],
    ]


async def test_apify_file_too_big(app, client, rmock):
    original_max_file_size = app.config.get('MAX_FILE_SIZE')
    app.config.update({'MAX_FILE_SIZE': 1})
    here = os.path.dirname(os.path.abspath(__file__))
    content = open(f"{here}/samples/test.{'xls'}", 'rb')
    mock_url = MOCK_CSV_URL.replace('.csv', 'xls')
    rmock.get(mock_url, body=content.read())
    content.close()
    res = await client.get(f"/apify?url={mock_url}")
    assert res.status_code == 500
    jsonres = await res.json
    assert 'File too big' in jsonres['error']
    app.config.update({'MAX_FILE_SIZE': original_max_file_size})


@pytest.mark.parametrize('extension', ['xls', 'xlsx'])
async def test_api_excel(client, rmock, extension):
    here = os.path.dirname(os.path.abspath(__file__))
    content = open(f"{here}/samples/test.{extension}", 'rb')
    mock_url = MOCK_CSV_URL.replace('.csv', extension)
    mock_hash = get_hash(mock_url)
    rmock.get(mock_url, body=content.read())
    content.close()
    await client.get(f"/apify?url={mock_url}")
    res = await client.get(f"/api/{mock_hash}")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['columns'] == ['rowid', 'col a', 'col b', 'col c']
    assert jsonres['rows'] == [
        [1, 'a1', 'b1', 'z'],
        [2, 'a2', 'b2', 'a'],
    ]


async def test_api_filter_referrers(app, client):
    app.config.update({'REFERRERS_FILTER': ['toto.com']})
    res = await client.get(f"/api/{'404'}")
    assert res.status_code == 403
    res = await client.get(f"/apify?url={'http://toto.com'}")
    assert res.status_code == 403
    res = await client.get(f"/api/{'404'}", headers={'Referer': 'http://next.toto.com'})
    assert res.status_code == 404
    app.config.update({'REFERRERS_FILTER': None})


@pytest.mark.parametrize('csv_path', Path(__file__).parent.glob('samples/real_csv/*.csv'))
async def test_real_csv_files(client, rmock, csv_path):
    with open(csv_path, 'rb') as content:
        rmock.get(MOCK_CSV_URL, body=content.read())
    res = await client.get(f"/apify?url={MOCK_CSV_URL}")
    assert res.status_code == 200
    res = await client.get(f"/api/{MOCK_CSV_HASH}")
    # w/ no error and more than 1 column and row we should be OK
    assert res.status_code == 200
    jsonres = await res.json
    assert len(jsonres['columns']) > 1
    assert len(jsonres['rows']) > 1


@pytest.fixture
async def uploaded_csv_filters(rmock, csv_filters, client):
    content = csv_filters.encode('utf-8')
    rmock.get(MOCK_CSV_URL_FILTERS, body=content)
    await client.get(f"/apify?url={MOCK_CSV_URL_FILTERS}")


async def test_api_filters_exact_hour(rmock, uploaded_csv_filters, client):
    res = await client.get(f"/api/{MOCK_CSV_HASH_FILTERS}?hour__exact=12:30")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['total'] == 1
    assert jsonres['rows'] == [
        [1, 'first', '12:30', 1.0],
    ]


async def test_api_filters_contains_string(rmock, uploaded_csv_filters, client):
    res = await client.get(f"/api/{MOCK_CSV_HASH_FILTERS}?id__contains=fir")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['total'] == 1
    assert jsonres['rows'] == [
        [1, 'first', '12:30', 1.0],
    ]


async def test_api_filters_contains_exact_int(rmock, uploaded_csv_filters, client):
    res = await client.get(f"/api/{MOCK_CSV_HASH_FILTERS}?value__exact=1")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['total'] == 1
    assert jsonres['rows'] == [
        [1, 'first', '12:30', 1.0],
    ]


async def test_api_filters_contains_exact_float(rmock, uploaded_csv_filters, client):
    res = await client.get(f"/api/{MOCK_CSV_HASH_FILTERS}?value__exact=1.0")
    assert res.status_code == 200
    jsonres = await res.json
    assert jsonres['total'] == 1
    assert jsonres['rows'] == [
        [1, 'first', '12:30', 1.0],
    ]
