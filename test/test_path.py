__author__ = 'mscalora'

import unittest
import json
from utils4test import *
from scripttest import TestFileEnvironment
from lxml import objectify, etree as lxml_et

env = TestFileEnvironment('../scratch', cwd='..')


class TestFromCommandLine(unittest.TestCase):

    def test_path_optimization(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --optimize-paths --stats --stats-format json')

        raw = AttrDict(json.loads(result.stdout))

        for count in raw.element_counts:
            if count.tag == 'LineString':
                self.assertEqual(count.pre_count, count.post_count)
            elif count.tag == 'Style' or count.tag == 'StyleMap':
                self.assertEqual(count.pre_count, count.post_count)

        for count in raw.point_counts:
            if count.tag == 'LineString':
                self.assertGreater(count.pre_count, count.post_count)
            elif count.tag == 'Point':
                self.assertEqual(count.pre_count, count.post_count)

    def test_path_and_style_optimization(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --optimize-paths --optimize-styles --stats --stats-format json')

        raw = AttrDict(json.loads(result.stdout))

        for count in raw.point_counts:
            if count.tag == 'LineString':
                self.assertGreater(count.pre_count, count.post_count)
            elif count.tag == 'Point':
                self.assertEqual(count.pre_count, count.post_count)

        for count in raw.element_counts:
            if count.tag == 'LineString':
                self.assertEqual(count.pre_count, count.post_count)
            elif count.tag == 'Style' or count.tag == 'StyleMap':
                self.assertGreater(count.pre_count, count.post_count)

    def test_path_and_style_and_coordinates_optimization(self):
        env.clear()
        result = env.run('kmlutil test-data/3-large-google-earth.kml --optimize-paths --optimize-styles --optimize-coordinates --stats --stats-format json')

        raw = AttrDict(json.loads(result.stdout))

        for count in raw.point_counts:
            if count.tag == 'LineString':
                self.assertGreater(count.pre_count, count.post_count)
            elif count.tag == 'Point':
                self.assertEqual(count.pre_count, count.post_count)

        for count in raw.element_counts:
            if count.tag == 'LineString':
                self.assertEqual(count.pre_count, count.post_count)
            elif count.tag == 'Style' or count.tag == 'StyleMap':
                self.assertGreater(count.pre_count, count.post_count)
