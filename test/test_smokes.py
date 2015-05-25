__author__ = 'mscalora'

import unittest
import json

from scripttest import TestFileEnvironment

from xml.etree import ElementTree as et
from lxml import objectify, etree as lxml_et

env = TestFileEnvironment('../scratch', cwd='..')


class TestFromCommandLine(unittest.TestCase):
    def test_help(self):
        env.clear()
        result = env.run('kmlutil --help')
        assert 'For the purposes of list and tree filtering' in result.stdout

    def test_kml_output(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml')
        assert result.stdout.startswith('<kml ')
        etree = et.fromstring(result.stdout)
        assert '{http://www.opengis.net/kml/2.2}kml' == etree.tag

    def test_list_text_output(self):
        env.clear()
        result = env.run('kmlutil --list test-data/0-test-misc.kml')
        assert 'Path with Inline Style' in result.stdout
        assert 'Folder' in result.stdout
        assert 'Polygon' in result.stdout
        assert 'Path' in result.stdout
        assert 'Point' in result.stdout

    def test_list_json_output(self):
        env.clear()
        result = env.run('kmlutil --list --list-format json test-data/0-test-misc.kml')
        doc = json.loads(result.stdout)
        assert doc[0]['type'] is not None

    def test_geojson_output(self):
        env.clear()
        result = env.run('kmlutil --geojson test-data/0-test-misc.kml')
        assert 'FeatureCollection' in result.stdout
        doc = json.loads(result.stdout)
        assert doc[u'type'] == 'FeatureCollection'


if __name__ == '__main__':
    unittest.main()
