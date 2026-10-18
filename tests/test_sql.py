import re
import unittest

import yaml
from pglast import parse_sql

from core.contracts import ROOT


class SQLAndContainers(unittest.TestCase):
    def test_postgresql_parses_every_sql_file(self):
        for path in (ROOT/'BD').glob('*.sql'):
            self.assertTrue(parse_sql(path.read_text()),path.name)

    def test_images_use_immutable_digests(self):
        for name in ['compose.yaml','compose.test.yaml']:
            d=yaml.safe_load((ROOT/name).read_text())
            for service in d['services'].values():
                if 'build' not in service:
                    self.assertRegex(service['image'],r'@sha256:[0-9a-f]{64}$')

    def test_db_not_exposed_and_reader_separated(self):
        d=yaml.safe_load((ROOT/'compose.yaml').read_text())
        self.assertNotIn('ports',d['services']['db'])
        self.assertEqual(d['services']['web']['environment']['DB_USER'],'routing_web')
        self.assertTrue(d['services']['web']['ports'][0].startswith('127.0.0.1:'))

    def test_web_depends_on_successful_etl(self):
        d=yaml.safe_load((ROOT/'compose.yaml').read_text())
        self.assertEqual(d['services']['web']['depends_on']['etl']['condition'],'service_completed_successfully')

    def test_test_database_has_no_persistent_volume(self):
        d=yaml.safe_load((ROOT/'compose.test.yaml').read_text())
        self.assertIn('/var/lib/postgresql/data',d['services']['dbtest']['tmpfs'])
        self.assertNotIn('volumes',d['services']['dbtest'])

if __name__=='__main__':unittest.main()
