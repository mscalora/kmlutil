__author__ = 'mscalora'

import unittest
import json
from utils4test import *
from scripttest import TestFileEnvironment
from lxml import objectify, etree as lxml_et

env = TestFileEnvironment('../scratch', cwd='..')


class TestFromCommandLine(unittest.TestCase):

    def test_file_not_found(self):
        env.clear()
        result = env.run('kmlutil test-data/does-not-exist.kml', expect_error=True)

        self.assertRegexpMatches(result.stderr, ur'^KMLUTIL ERROR.*I/O error')

    def test_parse_error(self):
        env.clear()
        result = env.run('kmlutil README.md', expect_error=True)

        self.assertRegexpMatches(result.stderr, ur'^KMLUTIL ERROR.*parsing error')

    def test_region_file_not_found(self):
        env.clear()
        result = env.run('kmlutil test-data/5-poly-geojson.kml --region Test --region-file test-data/does-not-exist.kml', expect_error=True)

        self.assertRegexpMatches(result.stderr, ur'^KMLUTIL ERROR.*Unable to read')

    def test_region_parse_error(self):
        env.clear()
        result = env.run('kmlutil test-data/5-poly-geojson.kml --region Test --region-file README.md', expect_error=True)

        self.assertRegexpMatches(result.stderr, ur'^KMLUTIL ERROR.*(Error parsing|parsing error)')
