__author__ = 'mscalora'

import unittest
import json
from utils4test import *

from scripttest import TestFileEnvironment

from xml.etree import ElementTree as et
from lxml import objectify, etree as lxml_et

env = TestFileEnvironment('../scratch', cwd='..')


class TestFromCommandLine(unittest.TestCase):

    def test_paths_only(self):
        env.clear()
        result = env.run('kmlutil --paths-only test-data/Test-Data.kml --pretty')
        assert result.stdout.startswith('<kml ')
        etree = lxml_et.fromstring(result.stdout)
        doc = etree.getroottree()
        n = xpath_count(doc, ur'//k:LineString')
        m = xpath_count(doc, ur'//k:Point|//k:Polygon|//k:Folder')
        assert n > 0 and m == 0

    def test_paths_only_stats(self):
        env.clear()
        for test_file in ['Test-Data.kml', 'Positively-4th-Street.kml']:
            result = env.run('kmlutil --paths-only test-data/%s --stats --stats-format json' % test_file)
            doc = json.loads(result.stdout)
            counts = {
                'LineString': None,
                'Point': None,
                'Polygon': None,
                'Folder': None,
            }
            for entry in doc['element_counts']:
                if entry['tag'] in counts:
                    counts[entry['tag']] = int(entry['post_count'])
            assert counts['Point'] == 0
            assert counts['Polygon'] == 0 or counts['Polygon'] is None
            assert counts['Folder'] == 0
            assert counts['LineString'] != 0


if __name__ == '__main__':
    unittest.main()
