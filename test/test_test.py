__author__ = 'mscalora'

import unittest
import json
from utils4test import *
from scripttest import TestFileEnvironment
from lxml import objectify, etree as lxml_et

env = TestFileEnvironment('scratch', cwd='.')

class TestFromCommandLine(unittest.TestCase):

    def test_delete_folder_by_name(self):
        env.clear()
        result = env.run('kmlutil --tree test-data/1-test-hand-edit.kml', expect_stderr=True)

        print(result.stdout)