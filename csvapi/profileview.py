from pathlib import Path

import pandas as pd
import sqlite3

from quart import send_from_directory
from quart.views import MethodView
from pandas_profiling import ProfileReport

from csvapi.errors import APIError
from csvapi.utils import get_db_info

from quart import current_app as app


class ProfileView(MethodView):

    def make_profile(self, db_info):
        dsn = 'file:{}?immutable=1'.format(db_info['db_path'])
        conn = sqlite3.connect(dsn)
        sql = 'SELECT * FROM [{}]'.format(db_info['table_name'])
        df = pd.read_sql(sql, con=conn)
        if(app.config['PANDAS_PROFILING_CONFIG_MIN']):
            profile = ProfileReport(df, config_file="profiling-minimal.yml")
        else:
            profile = ProfileReport(df)
        profile.to_file(db_info['profile_path'])
        return Path(db_info['profile_path'])

    async def get(self, urlhash):
        db_info = get_db_info(urlhash)
        p = Path(db_info['db_path'])
        if not p.exists():
            raise APIError('Database has probably been removed or does not exist yet.', status=404)

        path = Path(db_info['profile_path'])

        if not path.exists():
            try:
                path = self.make_profile(db_info)
            except (sqlite3.OperationalError, sqlite3.IntegrityError) as e:
                raise APIError('Error selecting data', status=400, payload=dict(details=str(e)))

        return await send_from_directory(path.parent, path.name)
