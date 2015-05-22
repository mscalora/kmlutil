#! /usr/bin/env python
from lxml import objectify, etree as et
from pykml import parser as kmlparser
import sys, os
sys.path.insert(1, os.path.join(sys.path[0], '..'))
import util
from util import get_by_id


def dump(obj):
    et.dump(obj)


def kmllist(objs):
    for i in range(0, len(objs)):
        it = objs[i]
        tag = util.tag(it) if hasattr(it, 'tag') else '<not-an-element>'
        name = it.name if hasattr(it, 'name') else \
            (it.attrib['id'] if 'id' in it.attrib else '<unnamed>')
        other = 'tbd'
        print('%2d: %s "%s" %s' % (i, tag, name, other))


tree = kmlparser.parse(open(os.path.join(sys.path[0], 'Test-Data.kml')))
doc = tree.getroot()

styles = doc.xpath(ur'//*[local-name()="Style"]')
style = styles[0]

stylemaps = doc.xpath(ur'//*[local-name()="StyleMap"]')
stylemap = styles[0]

folders = doc.xpath(ur'//*[local-name()="Folder"]')
folder = folders[0]

paths = doc.xpath(ur'//*[local-name()="Placemark" and *[local-name()="LineString"]]')
path = paths[0]

print("Variables setup: et, tree, doc, style, stylemap, folder or path ")
print("Utilities/Remiders: ")
print("    Dump: dump(path)")
print("    Get by id: get_by_id(id)")
