#! /usr/bin/env python
from lxml import objectify, etree as et
from pykml import parser as kmlparser
tree = kmlparser.parse(open('/Users/mscalora/temp/Styles1.kml'))
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
print("Remiders: ")
print("    Dump: et.dump(path)")
