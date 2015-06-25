__author__ = 'mscalora'

import unittest
import json
from utils4test import *
from scripttest import TestFileEnvironment
from lxml import objectify, etree as lxml_et
import utils4test

env = TestFileEnvironment('scratch', cwd='.')

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

    def test_path_and_style_and_coordinates_optimization1(self):
        env.clear()
        result = env.run('kmlutil test-data/3-large-google-earth.kml --optimize-paths --optimize-styles --optimize-coordinates --stats --stats-format json -vvvvv', expect_stderr=True)

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

    def test_path_and_style_and_coordinates_optimization2(self):
        env.clear()
        result = env.run('kmlutil test-data/3-large-google-earth.kml --optimize-paths --optimize-styles --optimize-coordinates --stats --stats-format json')

        raw = AttrDict(json.loads(result.stdout))

        counts_by_tag = AttrDict({item.tag: item for item in raw.element_counts})
        self.assertGreater(counts_by_tag.Style.pre_count, counts_by_tag.Style.post_count)
        self.assertGreater(counts_by_tag.StyleMap.pre_count, counts_by_tag.StyleMap.post_count)
        self.assertGreater(counts_by_tag.IconStyle.pre_count, counts_by_tag.IconStyle.post_count)
        self.assertGreater(counts_by_tag.Icon.pre_count, counts_by_tag.Icon.post_count)

        points_by_tag = AttrDict({item.tag: item for item in raw.point_counts})
        self.assertGreater(points_by_tag.Document.pre_count, points_by_tag.Document.post_count)
        self.assertGreater(points_by_tag.LineString.pre_count, points_by_tag.LineString.post_count)
        self.assertEqual(points_by_tag.Point.pre_count, points_by_tag.Point.post_count)

    def test_region_clipping_simple(self):
        env.clear()
        result = env.run('kmlutil --tree test-data/5-poly-geojson.kml -r SimplePoly --list-detail --list-format json')

        raw = json.loads(result.stdout)

        counts_by_name = AttrDict({})
        for item in raw:
            name = item['name'] if 'name' in item else None
            if name not in counts_by_name:
                counts_by_name[name] = 1
            else:
                counts_by_name[name] += 1

        self.assertFalse('Out' in counts_by_name)
        self.assertFalse('Complex' in counts_by_name)
        self.assertEqual(counts_by_name.Simple, 1)
        self.assertEqual(counts_by_name.In, 3)
        self.assertEqual(counts_by_name.MostlyIn, 2)
        self.assertEqual(counts_by_name.MostlyOut, 2)

    def test_region_clipping_simple(self):
        env.clear()
        result = env.run('kmlutil --tree test-data/5-poly-geojson.kml -r SimplePoly --list-detail --list-format json')

        raw = json.loads(result.stdout)

        counts_by_name = AttrDict({})
        for item in raw:
            name = item['name'] if 'name' in item else None
            if name not in counts_by_name:
                counts_by_name[name] = 1
            else:
                counts_by_name[name] += 1

        self.assertFalse('Out' in counts_by_name)
        self.assertFalse('Complex' in counts_by_name)
        self.assertEqual(counts_by_name.Simple, 1)
        self.assertEqual(counts_by_name.In, 3)
        self.assertEqual(counts_by_name.MostlyIn, 2)
        self.assertEqual(counts_by_name.MostlyOut, 2)

    def test_region_clipping_complex(self):
        env.clear()
        result = env.run('kmlutil --tree test-data/5-poly-geojson.kml -r ComplexPoly --list-detail --list-format json')

        raw = json.loads(result.stdout)

        counts_by_name = AttrDict({})
        for item in raw:
            name = item['name'] if 'name' in item else None
            if name not in counts_by_name:
                counts_by_name[name] = 1
            else:
                counts_by_name[name] += 1

        self.assertFalse('Out' in counts_by_name)
        self.assertFalse('Simple' in counts_by_name)
        self.assertEqual(counts_by_name.Complex, 1)
        self.assertEqual(counts_by_name.In, 3)
        self.assertEqual(counts_by_name.MostlyIn, 2)
        self.assertEqual(counts_by_name.MostlyOut, 2)

    def test_region_clipping_complex_external(self):
        env.clear()
        result = env.run('kmlutil --tree test-data/5-poly-geojson.kml -r ExternalComplexPoly --list-detail --list-format json --region-file test-data/6-polys-geojson.kml')

        raw = json.loads(result.stdout)

        counts_by_name = AttrDict({})
        for item in raw:
            name = item['name'] if 'name' in item else None
            if name not in counts_by_name:
                counts_by_name[name] = 1
            else:
                counts_by_name[name] += 1

        self.assertFalse('Out' in counts_by_name)
        self.assertFalse('Simple' in counts_by_name)
        self.assertEqual(counts_by_name.Complex, 1)
        self.assertEqual(counts_by_name.In, 3)
        self.assertEqual(counts_by_name.MostlyIn, 2)
        self.assertEqual(counts_by_name.MostlyOut, 2)

    def test_dump_path(self):
        env.clear()
        result = env.run('kmlutil --tree test-data/0-test-misc.kml --dump-path "Pole Canyon Trail"')

        for line in result.stdout.split("\n"):
            if line.strip() != '':
                self.assertRegexpMatches(line, ur'(-?\d+(?:\.\d*)?,){1,2}-?\d+(?:\.\d*)?')

    def test_multi_flatten(self):
        env.clear()
        result = env.run('kmlutil --multi-flatten test-data/7-multigeometry.kml --stats --stats-detail --stats-format json')

        counts = utils4test.stats_counts_to_dict(result.stdout)

        self.assertLess(counts.Placemark.pre_count, counts.Placemark.post_count)
        self.assertNotEqual(counts.MultiGeometry.pre_count, 0)
        self.assertEquals(counts.MultiGeometry.post_count, 0)
