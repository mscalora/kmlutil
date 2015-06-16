__author__ = 'mscalora'

import unittest
import json
from utils4test import *
from scripttest import TestFileEnvironment
from lxml import objectify, etree as lxml_et

env = TestFileEnvironment('../scratch', cwd='..')


class TestFromCommandLine(unittest.TestCase):

    def test_delete_styles(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --delete-styles --stats --stats-format json')

        counts = stats_counts_to_dict(result.stdout)

        self.assertEqual(0, counts.Style.post_count)
        self.assertEqual(0, counts.StyleMap.post_count)

    def test_validate_styles(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --validate-styles --no-kml-out')

        self.assertRegexpMatches(result.stdout, ur'orphan')

    def test_optimize_styles(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --optimize-styles --stats --stats-format json')

        counts = stats_counts_to_dict(result.stdout)

        self.assertGreater(counts.Style.pre_count, counts.Style.post_count)
        self.assertGreater(counts.StyleMap.pre_count, counts.StyleMap.post_count)
