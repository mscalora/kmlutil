__author__ = 'mscalora'

import unittest
import json
from utils4test import *
from scripttest import TestFileEnvironment
from lxml import objectify, etree as lxml_et

env = TestFileEnvironment('../scratch', cwd='..')


class TestFromCommandLine(unittest.TestCase):

    def test_stats_text(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --stats')

        self.assertRegexpMatches(result.stdout, ur'Counts by Element Type')
        self.assertRegexpMatches(result.stdout, ur'Document\s*1\s*1')
        for line in result.stdout.splitlines():
            if '%' in line:
                fields = line.split()
                self.assertEqual(int(fields[1]), int(fields[2]), msg='Pre and post counts for %s should be equal ints but are %s and %s' % tuple(fields[:3]))

    def test_stats_detail_text(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --stats --stats-detail')

        self.assertRegexpMatches(result.stdout, ur'Counts by Element Type')
        self.assertRegexpMatches(result.stdout, ur'Coordinate Point Count by Element Type')
        self.assertRegexpMatches(result.stdout, ur'Document\s*1\s*1')
        for line in result.stdout.splitlines():
            if '%' in line:
                fields = line.split()
                self.assertEqual(int(fields[1]), int(fields[2]), msg='Pre and post counts for %s should be equal ints but are %s and %s' % tuple(fields[:3]))

    def test_stats_text_with_paths_only(self):
        env.clear()
        result = env.run('kmlutil --paths-only test-data/0-test-misc.kml --stats --stats-format text')

        self.assertRegexpMatches(result.stdout, ur'Counts by Element Type')
        self.assertRegexpMatches(result.stdout, ur'Document\s*1\s*1')
        for line in result.stdout.splitlines():
            if '%' in line:
                fields = line.split()
                if fields[0] == 'Point':
                    self.assertNotEqual(int(fields[1]), int(fields[2]), msg='Pre and post counts for %s should be not equal ints but are %s and %s' % tuple(fields[:3]))
                elif fields[0] == 'LineString':
                    self.assertEqual(int(fields[1]), int(fields[2]), msg='Pre and post counts for %s should be equal ints but are %s and %s' % tuple(fields[:3]))

    def test_stats_json(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --stats --stats-format json')

        raw = json.loads(result.stdout)

        self.assertIn('element_counts', raw)

        stats = stats_counts_to_dict(result.stdout)

        for tag in ['Document', "Point", "LineString", "Polygon", "Folder", "Style", "StyleMap", "Placemark"]:
            self.assertTrue(tag in stats and stats[tag].pre_count != 0, msg='Stats should have non 0 entry for %s' % tag)

        for tag in stats.keys():
            msg = "Counts not equal for %s, were %s and %s" % (tag, stats[tag].pre_count, stats[tag].post_count)
            self.assertEqual(stats[tag].pre_count, stats[tag].post_count, msg=msg)

    def test_stats_json_with_paths_only(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --extract "Path with Inline Style" --stats --stats-detail --stats-format json')

        stats = stats_counts_to_dict(result.stdout)

        count_should_change_by_tag = {
            'LineString': True,
            'Document': False,
        }
        for tag, should_change in count_should_change_by_tag.items():
            if should_change:
                msg = "Counts equal for %s, were %s and %s" % (tag, stats[tag].pre_count, stats[tag].post_count)
                self.assertNotEqual(stats[tag].pre_count, stats[tag].post_count, msg=msg)
            else:
                msg = "Counts not equal for %s, were %s and %s" % (tag, stats[tag].pre_count, stats[tag].post_count)
                self.assertEqual(stats[tag].pre_count, stats[tag].post_count, msg=msg)

        raw = AttrDict(json.loads(result.stdout))

        self.assertNotEqual(0, len(raw.path_style_counts), msg='Path Style stats missing')
        self.assertNotEqual(0, len(raw.point_counts), msg='Point count stats missing')

    def test_stats_detail_json_with_paths_only(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --paths-only --stats --stats-detail --stats-format json')

        raw = AttrDict(json.loads(result.stdout))
        for section in raw.point_counts:
            if section.tag == 'Point' or section.tag == 'Polygon':
                self.assertNotEqual(section.pre_count, section.post_count)
                self.assertEqual(0, section.post_count)
            elif section.tag == 'Document':
                self.assertNotEqual(section.pre_count, section.post_count)
            elif section.tag == 'LineString':
                self.assertEqual(section.pre_count, section.post_count)

        stats = stats_counts_to_dict(result.stdout)

        count_should_change_by_tag = {
            'LineString': False,
            'Document': False,
            'Point': True,
            'Polygon': True,
        }
        for tag, should_change in count_should_change_by_tag.items():
            if should_change:
                msg = "Counts equal for %s, were %s and %s" % (tag, stats[tag].pre_count, stats[tag].post_count)
                self.assertNotEqual(stats[tag].pre_count, stats[tag].post_count, msg=msg)
            else:
                msg = "Counts not equal for %s, were %s and %s" % (tag, stats[tag].pre_count, stats[tag].post_count)
                self.assertEqual(stats[tag].pre_count, stats[tag].post_count, msg=msg)
