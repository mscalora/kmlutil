__author__ = 'mscalora'

import unittest
import json
from utils4test import *
from scripttest import TestFileEnvironment
from lxml import objectify, etree as lxml_et

env = TestFileEnvironment('../scratch', cwd='..')


class TestFromCommandLine(unittest.TestCase):

    def test_delete_path_by_name_not_found(self):
        env.clear()
        result = env.run('kmlutil test-data/5-poly-geojson.kml --no-kml-out --delete does-not-exist', expect_stderr=True)

        self.assertRegexpMatches(result.stderr, ur'Deleteing 0 item', 'No feature should have been found')

    def test_delete_path_by_xpath_not_found(self):
        env.clear()
        result = env.run('kmlutil test-data/5-poly-geojson.kml --no-kml-out --delete "/*/*/*[100]"', expect_stderr=True)

        self.assertRegexpMatches(result.stderr, ur'Deleteing 0 item', 'No feature should have been found')

    def test_delete_path_by_feature_type_not_found(self):
        env.clear()

        result = env.run('kmlutil test-data/6-polys-geojson.kml --no-kml-out --delete \'@Point\'', expect_stderr=True)

        self.assertRegexpMatches(result.stderr, ur'Deleteing 0 item', 'No feature should have been found')

        result = env.run('kmlutil test-data/6-polys-geojson.kml --no-kml-out --delete \'@LineString\'', expect_stderr=True)

        self.assertRegexpMatches(result.stderr, ur'Deleteing 0 item', 'No feature should have been found')

        result = env.run('kmlutil test-data/6-polys-geojson.kml --no-kml-out --delete \'@Point\'', expect_stderr=True)

        self.assertRegexpMatches(result.stderr, ur'Deleteing 0 item', 'No feature should have been found')

    def test_delete_path_by_name(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --tree --delete \'Pole Canyon Trail\'', expect_stderr=True)

        self.assertRegexpMatches(result.stderr, ur'Deleteing 1 item', 'One feature should have been deleted')

    def test_delete_placemarks_by_name_wildcard(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --tree --delete \'%*n\'', expect_stderr=True)

        # should delete one Point and one Polygon
        self.assertRegexpMatches(result.stderr, ur'Deleteing 2 item', 'Two features should have been deleted')

    def test_delete_by_xpath(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --tree --delete \'//kml:Folder/*[kml:Point]|//*[kml:LineString and kml:name[contains(text(), "Map")]]\'', expect_stderr=True)

        self.assertRegexpMatches(result.stderr, ur'Deleteing 3 item', 'Three feature should have been deleted')

    def test_delete_folder_by_name(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --delete \'Other Stuff\' --stats --stats-format json', expect_stderr=True)

        self.assertRegexpMatches(result.stderr, ur'Deleteing 1 item', 'One feature should have been deleted')

        stats = AttrDict(stats_counts_to_dict(result.stdout))

        # one folder
        self.assertEqual(stats.Folder.pre_count, stats.Folder.post_count + 1)
        # folder contents should be deleted with the folder
        self.assertGreater(stats.Placemark.pre_count, stats.Placemark.post_count)

    def test_rename_folder_by_name(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --list --rename "Other Stuff" "Not Paths"')

        self.assertRegexpMatches(result.stdout, ur'Not Paths\s*Folder', 'One feature should have been deleted')

    def test_rename_all_paths(self):
        env.clear()
        result = env.run('kmlutil test-data/0-test-misc.kml --list --rename "@Path" track')

        self.assertRegexpMatches(result.stdout, ur'track\s*Path', 'Paths should be renamed to "track"')

    def test_folderize(self):
        env.clear()
        result = env.run('kmlutil --tree test-data/A-folderize-acid-test.kml --folderize "Crop Circles" --folderize Rect -v', expect_stderr=True)

        self.assertRegexpMatches(result.stderr, ur"Folder:\s*'Crop Circles'\D*\d*?[1-9]", 'Some children should have been moved')
        self.assertRegexpMatches(result.stderr, ur"Folder:\s*'Rect'\D*\d*?[1-9]", 'Some children should have been moved')

    def NOT_test_next(self):
        result = env.run('')
        raw = json.loads(result.stdout)

        self.assertIn('element_counts', raw)

        stats = stats_counts_to_dict(result.stdout)

        for tag in ['Document', "Point", "LineString", "Polygon", "Folder", "Style", "StyleMap", "Placemark"]:
            self.assertTrue(tag in stats and stats[tag].pre_count != 0, msg='Stats should have non 0 entry for %s' % tag)

        for tag in stats.keys():
            msg = "Counts not equal for %s, were %s and %s" % (tag, stats[tag].pre_count, stats[tag].post_count)
            self.assertEqual(stats[tag].pre_count, stats[tag].post_count, msg=msg)
