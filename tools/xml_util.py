#!/usr/bin/env python
import sys, re
from lxml import etree as et


def xpath(node, xpath_exp, namespace_map=None):
    nsmap = {k: v for k, v in node.nsmap.items() if k is not None} if namespace_map is None else namespace_map
    return node.xpath(xpath_exp, namespaces=nsmap)


def tag(node):
    return node.tag.split('}')[-1]


def nstag(node):
    nsmap = {v: k for k, v in node.nsmap.items() if k is not None} if hasattr(node, 'nsmap') and node.nsmap is not None else {}
    return re.sub(ur'[{]([^}]+)[}]', lambda r: nsmap[r.group(1)] + ':' if r.group(1) in nsmap else r.group(0), node.tag)

if len(sys.argv) < 2:
    print "Usage:"
    print "    xml_util.py [ <filename> ] <xpath-expression> "
    sys.exit(0)

xpath_expression = sys.argv.pop()
tree = et.parse(open(sys.argv.pop(), 'r') if len(sys.argv) > 1 else sys.stdin)
doc = tree.getroot()

node_list = xpath(doc, xpath_expression)
for node in node_list if isinstance(node_list, list) else [node_list]:
    if hasattr(node, 'attrname'):
        parent = node.getparent()
        print "ATTRIBUTE: %s=%s on %s at %s" % (node.attrname, repr(node), nstag(parent), parent.getroottree().getpath(parent))
    elif hasattr(node, 'zfill'):
        print "STRING: %s" % repr(node)
    elif hasattr(node, 'tag'):
        print "ELEMENT: %s at %s" % (nstag(node), node.getroottree().getpath(node))
    elif isinstance(node, bool):
        print "BOOLEAN: %s" % repr(node)
    elif isinstance(node, float):
        print "NUMBER: %s" % str(node)
    else:
        print "UNKNOWN: %s" % repr(node)
else:
    print "Nothing selected by xpath expression '%s'" % xpath_expression
