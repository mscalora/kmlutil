__author__ = 'mscalora'

import unittest
from utils4test import *
from scripttest import TestFileEnvironment
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
            counts = stats_counts_to_dict(result.stdout)
            assert counts.LineString.post_count > 0
            assert counts.Point.post_count == 0
            assert counts.Polygon.post_count == 0
            assert counts.Folder.post_count == 0

    def test_extract(self):
        env.clear()
        # { file-name: { KML_ID-to-extract: { [ tag: post_count,...]},...},...}
        tests = {'Test-Data.kml': {'Path with Inline Style': {'LineString': 1, 'Point': 0, 'Polygon': 0, 'Folder': 0},
                                   '/*/*/*[20]': {'LineString': 1, 'Point': 0, 'Polygon': 0, 'Folder': 0},
                                   'Out': {'Point': 1, 'LineString': 0, 'Polygon': 0, 'Folder': 0},
                                   '/*/*/*[21]/*[5]/*[4]': {'Point': 1, 'LineString': 0, 'Polygon': 0, 'Folder': 0},
                                   'Other Stuff': {'Folder': 1, 'LineString': 0},
                                   '/*/*/*[21]/*[5]': {'Folder': 1, 'LineString': 0}},
                 'us_states_5m.kml': {'Hawaii': {'Placemark': 1, 'Folder': 0},
                                      'Utah': {'Polygon': 1, 'MultiGeometry': 0, 'Folder': 0},
                                      ('Utah', 'Nebraska'): {'Polygon': 2, 'MultiGeometry': 0, 'Folder': 0}}}
        # note: extracting a Folder will keep all descendants
        for file_name, id_list in tests.items():
            for kml_id, tags in id_list.items():
                kml_ids = [kml_id] if is_str(kml_id) else kml_id                       # make a tuple of one if needed
                extracts = ' '.join(['--extract "{0:s}"'.format(s) for s in kml_ids])  # render the IDs as command line options
                cmd = 'kmlutil test-data/%s %s --stats --stats-format json' % (file_name, extracts)
                result = env.run(cmd)  # build the command line
                counts = stats_counts_to_dict(result.stdout)  # parse the stats as a dict keyed by element tag
                for tag, count in tags.items():
                    msg = 'Tag count for %s: %d should be %d after extract of "%s" from %s running: %s' % \
                          (tag, counts[tag].post_count, count, flatten(kml_id), file_name, cmd)
                    self.assertEqual(counts[tag].post_count, count, msg=msg, )


if __name__ == '__main__':
    unittest.main()
