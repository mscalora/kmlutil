#!/usr/bin/env python

from __future__ import print_function
import os
import re
import sys
import operator
from math import radians, cos, sin, asin, sqrt
from copy import deepcopy

from pykml import parser as kmlparser
from lxml import objectify, etree as lxml_etree

from simplify import simplify
from ordered_set import OrderedSet as oSet

placemark_name_and_type_xpath = \
    ur'.//kml:Placemark[kml:{type} and kml:name[text()={name}]]'
placemark_2name_and_type_xpath = \
    ur'.//*[local-name()="Placemark" and *[local-name()="name" and (text()="%s" or text()="%s")] and *[local-name()="%s"]]'
placemark_type_xpath = \
    ur'.//*[local-name()="Placemark" and *[local-name()="%s"]]'
folder_by_name = \
    ur'.//*[local-name()="Folder" and *[local-name()="name" and normalize-space(text())={name}]]'
folder_or_placemark_by_name = \
    ur'.//*[(local-name()="Folder" or local-name()="Placemark") and *[local-name()="name" ' \
    ur'and normalize-space(text())={name}]]'
folder_or_placemark_by_name_starts_with = \
    ur'.//*[(local-name()="Folder" or local-name()="Placemark") and *[local-name()="name" ' \
    ur'and starts-with(normalize-space(text()),{part0})]]'
folder_or_placemark_by_name_ends_with = \
    ur'.//*[(local-name()="Folder" or local-name()="Placemark") and *[local-name()="name" and ' \
    ur'contains(text(), {part0}) and substring(normalize-space(text()), string-length(normalize-space(text())) - string-length({part0}) + 1)={part0}]]'
folder_or_placemark_by_name_match = \
    ur'.//*[(local-name()="Folder" or local-name()="Placemark") and *[local-name()="name" and ' \
    ur'starts-with(normalize-space(text()),{part0}) and contains(text(), {part1}) and ' \
    ur'substring(normalize-space(text()), string-length(normalize-space(text())) - string-length({part1}) + 1)={part1}]]'
top_level_folder_or_placemarks = \
    ur'/*/*[local-name()="Document"]/*[local-name()="Folder" or local-name()="Placemark"]'
polygon_point_or_linestring = \
    ur'*[local-name()="Polygon" or local-name()="Point" or local-name()="LineString"] | ' \
    ur'*/*[local-name()="Polygon" or local-name()="Point" or local-name()="LineString"]'
all_root_features = \
    ur'/*/*/*[local-name()="Folder" or local-name()="Placemark"]'
child_features = \
    ur'*[local-name()="Folder" or local-name()="Placemark"]'

import util
from util import encode_xpath_string_literal as encode4xpath
import json
from attrdict import AttrDict


defaults = AttrDict({
    'kmlfile': None,
    'verbose': 0,
    'region': None,
    'region_file': None,
    'optimize_paths': False,
    'optimize_styles': False,
    'optimize_coordinates': False,
    'path_error_limit': 0.00001,
    'stats': False,
    'stats_format': 'text',
    'out_kml': None,
    'output_file': None,
    'pretty_print': False,
    'list_format': 'text',
    'tree': False,
    'list': False,
    'namespaces': False,
    'filter': None,
    'no_kml_out': False,
    'list_detail': False,
    'folderize': False,
    'folderize_limit': 0.35,
    'serialize_names': False,
    'delete_styles': False,
    'paths_only': False,
    'demulti_paths': False,
    'dump': [],
    'extract': [],
    'delete': [],
    'rename': [],
    'combine': False,
    'combine_filter': [],
    'validate_styles': False,
    'reraise_errors': False,
})

args = None
verboseness = 0

out_diag = sys.stderr
out_stats = sys.stderr
out_kml = sys.stdout

# first element of array is used for output
alias_map = {
    'Point': ['Point', 'Placemark', 'Waypoint'],
    'LineString': ['Path', 'Trail'],
    'Polygon': ['Polygon', 'Area']
}

all_polygon_names = '//*[local-name()="Placemark" and *[local-name()="Polygon"]]/*[local-name()="name"]/text()'
all_elementX_names = '//*[local-name()="Placemark" and *[local-name()="%s"]]/*[local-name()="name"]/text()'
all_style_data = '//*[local-name()="Style" or local-name()="StyleMap"]|//*[local-name()="Placemark"]/*[local-name()="styleUrl"]'


class KMLError(Exception):
    def __init__(self, message):
        self.message = message


def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))

    # 6367 km is the radius of the Earth
    km = 6367 * c
    # mi = 3956.27 * c
    return km


def path_length(coords_list):
    length = 0
    if len(coords_list) > 1:
        x = coords_list[0][0]
        y = coords_list[0][1]
        for i in xrange(1, len(coords_list) - 1):
            p = x
            q = y
            x = coords_list[i][0]
            y = coords_list[i][1]
            length += haversine(x, y, p, q)
    return length


def area_of_polygon(list_of_coords):
    a = 0
    ox, oy = list_of_coords[0][0:2]
    for p in list_of_coords[1:]:
        x, y = p[0:2]
        a += (x * oy - y * ox)
        ox, oy = x, y
    return abs(a / 2)


def parse_coords(coords_text):
    return [tuple([float(n) for n in coordinates.split(',')]) for coordinates in coords_text.strip().split()]


class Placemark:
    km_doc = None

    def __init__(self, element, kml_doc=None):
        self.__dict__['placemark_element'] = element
        self.__dict__['kml_doc'] = kml_doc
        self.__dict__['name'] = element.name if hasattr(element, "name") else None

    def get_alias(self):
        return util.tag(self) + \
            ('-'.join([tag if hasattr(self, tag) else '' for tag in ['LineString', 'Point', 'Polygon', 'Folder', 'LinearRing', 'MultiGeometry']])) + \
            (self.name if 'name' in self.__dict__ else '<unnamed>')

    def parse_coords(self, raise_on_failure=True):
        coords_list = util.xp(self.placemark_element, './/kml:coordinates/text()')
        joined_coords_list = " ".join(coords_list).strip()
        if len(coords_list) == 0 or joined_coords_list == '':
            if raise_on_failure:
                print("Feature does not contain any coordinates '%s'" % self.get_name(default='<unnamed>'), file=out_diag)
                raise KMLError("Feature coordinates not found")
            self.__dict__['coordinates'] = None
        elif hasattr(self.placemark_element, "MultiGeometry") and not self.is_multi_polygon() and not self.is_multi_path():
            if raise_on_failure:
                print("Unexpected MultiGeometry element %s " % self.get_alias(), file=out_diag)
                print(lxml_etree.tostring(self.__dict__, pretty_print=True))
                raise KMLError("Feature coordinates not available for this type of MultiGeometry feature")
            self.__dict__['coordinates'] = None
        else:
            self.__dict__['coordinates'] = parse_coords(joined_coords_list)
        return self.__dict__['coordinates']

    def __getattr__(self, attr):
        if attr == 'coordinates':
            return self.get_coords()
        return getattr(self.placemark_element, attr)

    def __setattr__(self, attr, value):
        return setattr(self.placemark_element, attr, value)

    def is_path(self):
        return hasattr(self.placemark_element, "LineString")

    def is_multi_path(self):
        return hasattr(self.placemark_element, "MultiGeometry") and hasattr(self.placemark_element.MultiGeometry, "LineString")

    def is_path_or_multipath(self):
        return self.is_path() or self.is_multi_path()

    def is_point(self):
        return hasattr(self.placemark_element, "Point")

    def is_polygon(self):
        return hasattr(self.placemark_element, "Polygon") or self.is_multi_polygon()

    def is_multi_polygon(self):
        return hasattr(self.placemark_element, "MultiGeometry") and hasattr(self.placemark_element.MultiGeometry, "Polygon")

    def is_multi_geometry(self):
        return hasattr(self.placemark_element, "MultiGeometry")

    def get_coords(self):
        return self.__dict__['coordinates'] if 'coordinates' in self.__dict__ else self.parse_coords(raise_on_failure=False)

    def has_coords(self):
        return self.get_coords() is not None and len(self.__dict__['coordinates']) > 0

    def get_name(self, default=None):
        namelist_list = self.placemark_element.xpath('.//*[local-name()="name"]/text()')
        return namelist_list[0] if len(namelist_list) else default

    def is_point_inside(self, x, y):
        c = self.get_coords()
        n = len(c)
        inside = False
        xints = 0

        p1x, p1y = c[0][0:2]
        for i in range(n + 1):
            p2x, p2y = c[i % n][0:2]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xints:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside

    def in_region(self, polygon, detail=False):
        c = self.get_coords()
        if c is None or len(c) == 0:
            return False
        begins_in = polygon.is_point_inside(c[0][0], c[0][1])
        ends_in = polygon.is_point_inside(c[-1][0], c[-1][1])
        if not detail:
            return begins_in or ends_in
        all_in = True
        any_in = False
        points_in = 0
        segments_in = 0
        prev_in = False
        for point in c:
            is_in = polygon.is_point_inside(point[0], point[1])
            all_in = all_in and is_in
            any_in = any_in or is_in
            if is_in:
                points_in += 1
                if not prev_in:
                    segments_in += 1
            prev_in = is_in
        return begins_in, ends_in, any_in, all_in, points_in, len(c), segments_in

    def get_normal_linestyle(self):
        if hasattr(self, 'Style') and hasattr(self.Style, 'LineStyle') and hasattr(self.Style.LineStyle, 'color'):
            kml_color = self.Style.LineStyle.color.text

    def get_path_color_width_opacity(self, cache=None):
        result = ['000000', 3.0, 1.0]
        for chain in [
            "Style;LineStyle;color;text",
            "StyleMap;{kml:Pair[kml:key[text()='normal']]};Style;LineStyle;color;text",
            "styleUrl;text;@;{kml:Pair[kml:key[text()='normal']]};Style;LineStyle;color;text",
            "styleUrl;text;@;{kml:Pair[kml:key[text()='normal']]};styleUrl;text;@;LineStyle;color;text",
        ]:
            color = util.chain(self, chain, cache=cache)
            if color is not None:
                result[0] = color[6:8] + color[4:6] + color[2:4]
                result[2] = int(color[0:2], 16)/255.0
                break
        for chain in [
            "Style;LineStyle;width;text",
            "StyleMap;{kml:Pair[kml:key[text()='normal']]};Style;LineStyle;width;text",
            "styleUrl;text;@;{kml:Pair[kml:key[text()='normal']]};Style;LineStyle;width;text",
            "styleUrl;text;@;{kml:Pair[kml:key[text()='normal']]};styleUrl;text;@;LineStyle;width;text",
        ]:
            width = util.chain(self, chain, cache=cache)
            if width is not None:
                result[1] = float(width)
                break
        return result

    def delete(self):
        self.placemark_element.getparent().remove(self.placemark_element)

    def simplify_path(self):
        coords = util.xp(self.placemark_element, ur'.//kml:coordinates')
        for coord in coords:
            text = coord.text
            clist = [tuple([float(v) for v in node.split(',')]) for node in text.split()]
            if len(clist) > 10:
                cnew = simplify(clist, args.path_error_limit)
                if args.optimize_coordinates:
                    new = ' '.join([','.join([("%.6f" % v).rstrip('0').rstrip('.') for v in node]) for node in cnew])
                else:
                    new = ' '.join([','.join([(str(v)).rstrip('0').rstrip('.') for v in node]) for node in cnew])
                coord.getparent().coordinates = objectify.StringElement(new)

    def optimize_coordinates(self):
        coords = util.xp(self.placemark_element, ur'.//kml:coordinates')
        for coord in coords:
            text = coord.text
            new = ' '.join([','.join([("%.6f" % float(v)).rstrip('0').rstrip('.') if '.' in v else v for v in node.split(',')]) for node in text.split()])
            coord.getparent().coordinates = objectify.StringElement(new)

    @staticmethod
    def find_folder_by_name(folder_name, context):
        xpath = folder_by_name.format(name=encode4xpath(folder_name))
        if args.verbose > 2:
            print(xpath, file=out_diag)
        element_list = context.xpath(xpath)

        return None if element_list is None or len(element_list) == 0 else element_list[0]

    @staticmethod
    def find_by_type(placemark_type, context):

        if args.verbose > 2:
            print(placemark_type_xpath % placemark_type, file=out_diag)

        element_list = context.xpath(placemark_type_xpath % placemark_type)

        return None if element_list is None or len(element_list) == 0 else Placemark(element_list[0])

    @staticmethod
    def find_by_name_and_type(placemark_name, placemark_type, context):

        if args.verbose > 2:
            print(placemark_name_and_type_xpath.format(name=encode4xpath(placemark_name),
                                                       type=placemark_type), file=out_diag)

        element_list = util.xp(context, placemark_name_and_type_xpath.format(name=encode4xpath(placemark_name),
                                                                             type=placemark_type))

        return None if element_list is None or len(element_list) == 0 else Placemark(element_list[0])


def find_boundry_folders(kml_doc):
    folder_list = []

    for folder in kml_doc.xpath("//*[local-name()='Folder' and *[local-name()='Placemark' and *[local-name()='name' and text()='Boundry']]]"):
        polygon = folder.xpath("*[local-name()='Placemark' and *[local-name()='name' and text()='Boundry']]")[0]
        coords_text = folder.xpath("*[local-name()='Placemark' and *[local-name()='name' and text()='Boundry']]//*[local-name()='coordinates']/text()")[0]

        folder_list.append(AttrDict({
            'name': folder.name.text,
            'element': folder,
            # 'coords': parse_coords(coords_text),
            'polygon': Placemark(polygon),
            'area': area_of_polygon(parse_coords(coords_text))
        }))
    return folder_list


def count_points(element):
    count = 0
    tag = util.tag(element)
    if tag == "Document" or tag == "LineString" or tag == "Polygon" or tag == "Point":
        coords = util.xp(element, './/kml:coordinates/text()')
        for coord in coords:
            count += len(coord.strip().split())
    return count


def rename_placemarks(doc, renames):
    for (kml_id, new_name) in renames:
        nodes = list_nodes(doc, kml_id)
        if args.verbose > 1:
            print("renaming {0:d} item(s) to '{1:s}'".format(len(nodes), new_name), file=out_diag)
        for node in nodes:
            node.name = objectify.StringElement(new_name)


def delete_nodes(doc, kml_ids):

    nodes = list_nodes(doc, kml_ids)

    print("Deleteing %d item(s)" % len(nodes), file=out_diag)

    for node in reversed(nodes):

        if args.verbose > 1:
            print("Deleteing %d item(s) named '%s'" % (len(nodes), node.name), file=out_diag)

        node.getparent().remove(node)


def extract_nodes(doc, kml_ids):

    nodes = list_nodes(doc, kml_ids)

    if args.verbose > 1:
            print("Located %d features to extract" % len(nodes), file=out_diag)

    all_top_level = doc.xpath(top_level_folder_or_placemarks)

    for node in reversed(all_top_level):
        node.getparent().remove(node)

    document_element = doc.xpath(ur'/*/*[local-name()="Document"]')[0]

    for node in nodes:
        document_element.append(node)


def demulti_paths(doc):

    # all the multi-segment linestrings
    multis = doc.xpath(ur'//*[local-name()="Placemark"][*[local-name()="MultiGeometry"]/*[local-name()="LineString"]]')

    for multi in reversed(multis):

        # all the segments in each placemark
        segments = multi.xpath(ur'.//*[local-name()="LineString"]')

        # the MultiGeometry node
        geometry = multi.xpath(ur'./*[local-name()="MultiGeometry"]')[0]
        multi.remove(geometry)

        # if there is more than one segment (not typical), get ready to make copies
        if len(segments) > 1:
            # make a copy of the whole placemark
            copy = deepcopy(multi)
            # position in the list
            parent = multi.xpath(ur'./..')[0]
            index = parent.index(multi)
            base_name = multi.name if hasattr(multi, "name") else None

            for i in reversed(range(0, len(segments))):
                if i == 0:
                    # use the original placemark for the first segment
                    multi.append(segments[i])
                else:
                    # use copies of it for subsequent segments
                    node = copy if i == 1 else deepcopy(copy)
                    # append the linestring to the placemark node
                    node.append(segments[i])
                    # insert it so that they come out in the same order
                    parent.insert(index+1, node)
                    # serialize the names
                    node.name = objectify.StringElement("%s part %s" % (base_name, i+1))


def paths_only(doc):
    paths = doc.xpath(all_placemark_paths)

    if args.verbose > 1:
            print("Located %d paths" % len(paths), file=out_diag)

    all_top_level = doc.xpath(top_level_folder_or_placemarks)

    for node in reversed(all_top_level):
        node.getparent().remove(node)

    document_element = doc.xpath(ur'/*/*[local-name()="Document"]')[0]

    for path in paths:
        document_element.append(path)


def remove_all_styles(doc):
    nodes = doc.xpath(all_style_data)

    if args.verbose > 1:
            print("Deleteing %d style related item(s)" % len(nodes), file=out_diag)

    for node in reversed(nodes):
        node.getparent().remove(node)


def doc_stats(doc, points=False):
    """
    calculate statistics for the specified document
    {
        element-tag: count,
        ...
    }
    :param doc: pykml document (root)
    :return: map as above
    """
    stats_map = {}
    predicate = ur'translate(substring(local-name(),1,1),"abcdefghijkmlnopqrstuvwxyz","ABCDEFGHIJKMLNOPQRSTUVWXYZ")=substring(local-name(),1,1)'
    all_uppercase = ur'//*[' + predicate + ']'
    all_with_coords = ur'//*[' + predicate + ' and .//kml:coordinates]'
    for el in util.xp(doc, all_with_coords if points else all_uppercase):
        tag = util.tag(el)
        if tag not in stats_map:
            stats_map[tag] = 0
        stats_map[tag] += count_points(el) if points else 1

    return stats_map


def list_filter(tag, filter_list):
    return True if filter_list is None else tag in filter_list


def lister(element, filter_list, tree=False, indent=0, recursive=True, children_only=False):
    node_list = []

    for el in element.xpath('*[local-name()="Document" or local-name()="Folder" or local-name()="Placemark"]'):
        el_tag = el.tag.split('}')[-1]
        name_ref = el.xpath('*[local-name()="name"]/text()')
        name = 'UNNAMED' if len(name_ref) == 0 else name_ref[0]
        type_list = el.xpath(ur'*[local-name()="Polygon" or local-name()="Point" or local-name()="LineString"] | ' +
                             ur'*/*[local-name()="Polygon" or local-name()="Point" or local-name()="LineString"]')
        if el_tag in ['Folder', 'Document']:
            type_tag = el_tag
        elif len(type_list) == 0:
            type_tag = 'UNKNOWN'
        else:
            type_tag = type_list[0].tag.split('}')[-1]
        node_item = None
        if not children_only and list_filter(type_tag, filter_list):
            node_item = AttrDict({
                'name': str(name),
                'type': list_type_mapper(type_tag),
                'indent': indent,
                'el': el
            })
            if args.list_detail and node_item.type == 'Path':
                els = el.xpath('.//*[local-name()="coordinates"]/text()')
                if els is not None and len(els):
                    coords = parse_coords(els[0])
                    if len(coords) > 1:
                        node_item.count = len(coords)
                        node_item.length = path_length(coords)
            node_list.append(node_item)
        if recursive and (el_tag == 'Folder' or el_tag == 'Document'):
            nodes = lister(el, filter_list, tree=tree, indent=indent + (0 if children_only else 1), recursive=recursive)
            node_list += nodes
            if node_item and args.list_detail:
                node_item.length = sum([node.length if 'length' in node and node.type == 'Path' else 0 for node in nodes])
                node_item.count = sum([node.count if 'count' in node else 0 for node in nodes])
    return node_list


def list_type_mapper(unmapped_type):
    return alias_map[unmapped_type][0] if unmapped_type in alias_map else unmapped_type


def kml_id_to_xpath(kml_id):

    if kml_id.startswith(('.', '/')):
        return kml_id
    elif kml_id.startswith('&'):
        return folder_or_placemark_by_name.format(name=encode4xpath(kml_id[1:]))
    elif kml_id.startswith('%'):
        pat = kml_id[1:].split('*')
        if len(pat) > 2:
            print("ERROR: only one * (wildcard) is permitted in a name pattern", file=out_diag)
            sys.exit(5)
        if len(pat) == 1 or len(pat[1]) == 0:
            return folder_or_placemark_by_name_starts_with.format(part0=encode4xpath(pat[0]))
        if len(pat[0]) == 0 and len(pat[1]):
            return folder_or_placemark_by_name_ends_with.format(part0=encode4xpath(pat[1]))
        else:
            return folder_or_placemark_by_name_match.format(part0=encode4xpath(pat[0]), part1=encode4xpath(pat[1]))

    return folder_or_placemark_by_name.format(name=encode4xpath(kml_id))


def list_nodes(doc, kml_ids):
    if isinstance(kml_ids, list) or isinstance(kml_ids, tuple):
        xpaths = map(kml_id_to_xpath, kml_ids)
    else:
        xpaths = [kml_id_to_xpath(kml_ids)]

    nodes = doc.xpath('|'.join(xpaths))
    return nodes


def dump(kml_doc, line_name, out_list=sys.stdout):

    node_list = list_nodes(kml_doc, line_name)

    for node in node_list:
        placemark = Placemark(node, kml_doc)
        if args.verbose:
            name = placemark.get_name()
            print("# %s" % "<unnamed>" if name is None else name, file=out_diag)
        for point in placemark.coordinates:
            print(u','.join(map(unicode, point)), file=out_list)


class FilteringAttrDictEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, AttrDict):
            d = dict(obj)
            d.pop('el', None)
            return d
        if isinstance(obj, objectify.ObjectifiedElement):
            return None
        return json.JSONEncoder.default(self, obj)


preprint_buf = None
preprint_file = sys.stdout
preprint_count = 0


def preprint(message=None, out_file=sys.stdout):
    global preprint_buf, preprint_file, preprint_count
    str_match = preprint_buf is not None and message is not None and preprint_buf == message and preprint_file == out_file
    if preprint_count > 0 and not str_match:
        print(preprint_buf + ('' if preprint_count == 1 else ' [%d occurances]' % preprint_count), file=preprint_file)
        preprint_count = 0
    if str_match:
        preprint_count += 1
    else:
        preprint_count = 0 if message is None else 1
        preprint_file = out_file
        preprint_buf = message


def print_list(doc, filter_list, tree=False, xpaths=False, list_format='text', out_list=sys.stdout):

    # map filter alias to real kml terms
    mapped_filter = filter_list
    if filter_list is not None:
        for term in filter_list.split(','):
            term_to_add = term
            for aliased_term, terms in alias_map.iteritems():
                if term in terms:
                    term_to_add = aliased_term
                    break
            mapped_filter = term_to_add

    if hasattr(doc, 'Document'):
        root = doc.Document
    elif hasattr(doc, 'Folder'):
        root = doc.Folder
    else:
        raise KMLError("Unsupported document root")

    node_list = lister(root, mapped_filter, tree=True, children_only=False)
    etree = lxml_etree.ElementTree(doc) if xpaths else None

    if list_format == 'json':

        serializable_list = []
        for node in node_list:
            serializable_node = dict(node)
            serializable_node.pop('el', None)
            if xpaths:
                serializable_node['xpath'] = etree.getpath(node.el)
            serializable_list.append(serializable_node)
        json.dump(serializable_list, out_list, indent=2 if args.pretty_print else None, cls=FilteringAttrDictEncoder)

    else:

        name_len = 0
        type_len = 0
        for node in node_list:
            if len(node.name) > name_len:
                name_len = len(node.name) + (node.indent * 2 if tree else 0)
            type_len = len(node.type) if len(node.type) > type_len else type_len

        line = "{name:<{name_width:d}s} {type:<{type_width:d}s}"

        for node in node_list:
            name = ("  " * node.indent if tree else '') + node.name
            if args.list_detail and 'length' in node:
                detail = line + " {count:6d} {length:7.2f}km {rate:7.2f}m/pt" + (" {xpath:s}" if xpaths else "")
                rate = node.length / node.count * 1000 if node.count > 0 else 0.0
                model = {
                    "name_width": name_len,
                    "name": name,
                    "type": node.type,
                    "type_width": type_len,
                    "count": node.count,
                    "length": node.length,
                    "rate": rate,
                    "xpath": etree.getpath(node.el) if xpaths else ""
                }
                preprint(detail.format(**model), out_file=out_list)
            else:
                simple = line + (" {xpath:s}" if xpaths else "")
                preprint(simple.format(name_width=name_len, name=name, type=node.type, type_width=type_len), out_file=out_list)

        preprint(None)


style_dir = AttrDict({
    'styles': {},   # (old) id: signature
    'uniques': {},  # signature: array of [ (old) ids ... ] sharing the same signature
    'ids': {},      # all ids in the document NOT belonging to Style and StyleMap elements
    'old2new': {},  # map of (old) id: (new) id
})

sigmap = {
    'Style': {
        'LineStyle': {
            'color': 'text',
            'width': 'text',
        },
        'IconStyle': {
            'scale': 'text',
            'Icon': {'href': 'text'},
        },
    }
}


def _sig(el, loc):
    sig = ''
    if isinstance(loc, dict):
        for name in loc.keys():
            if hasattr(el, name):
                sig += '-' + name + _sig(el[name], loc[name])
    else:
        if loc == 'text':
            sig += '=' + el.text.strip()
        else:
            if loc in el.attrib:
                sig += '@' + el.attrib[loc]
    return sig


def get_sig(el, style_info=None):
    tag = el.tag.split('}')[-1]
    sig = tag + '|'
    if tag == 'StyleMap':
        sig += '['
        for child in el.getchildren():
            ctag = child.tag.split('}')[-1]
            if ctag == 'Pair' and hasattr(child, 'key') and hasattr(child, 'styleUrl'):
                style_id = child.styleUrl.text[1:]
                if style_id not in style_dir.styles:
                    print('Error: style not found with id of "%s"' % style_id, file=out_diag)
                sig += '#' + child.key + '=' + style_dir.styles[style_id][0]
        sig += ']'
    else:
        sig += _sig(el, sigmap[tag])
    if style_info is not None:
        if 'id' in el.attrib:
            style_id = el.attrib['id']
            style_info.styles[style_id] = (sig, el)
            if sig not in style_info.uniques:
                style_info.uniques[sig] = oSet()
            style_info.uniques[sig].add(style_id)
    return sig


def optimize_styles(doc):
    styles = doc.xpath("//*[local-name()='Style' and @id]")
    style_detail = args.verbose > 4
    for el in styles:
        get_sig(el, style_dir)
        if style_detail:
            print('%30s - %s' % (el.attrib['id'], get_sig(el, style_dir)), file=out_diag)
    styles = doc.xpath("//*[local-name()='StyleMap' and @id]")
    for el in styles:
        get_sig(el, style_dir)
        if style_detail:
            print('%30s - %s' % (el.attrib['id'], get_sig(el, style_dir)), file=out_diag)
    if style_detail:
        print('Styles:%d uniques:%d' % (len(style_dir['styles']), len(style_dir['uniques'])))

    style_dir.ids = {str(idattr): True for idattr in doc.xpath(ur"//*[local-name()!='StyleMap' and local-name()!='Style']/@id")}

    c = 0
    for sig in style_dir.uniques.keys():
        c += 1
        sid = 'S'+str(c)
        # change id on the delegate Style and StyleMap elements we are keeping
        while sid in style_dir.ids:
            c += 1
            sid = 'S'+str(c)
        did = style_dir.uniques[sig][0]
        delegate = style_dir.styles[did][1]
        delegate.attrib['id'] = sid
        # build old2new mapping
        for oldid in style_dir.uniques[sig]:
            style_dir.old2new[oldid] = sid
        # remove orphaned Style and StyleMap elements
        for xid in style_dir.uniques[sig][1:]:
            xel = style_dir.styles[xid][1]
            xparent = xel.getparent()
            if xparent is not None:
                xparent.remove(xel)
    for el in doc.xpath("//*[*[local-name()='styleUrl']]"):
        oldid = el.styleUrl.text[1:]
        el.styleUrl = objectify.StringElement('#' + style_dir.old2new[oldid])

    # targets = {str(el.attrib['id']): el for el in doc.xpath(ur"//*[@id]")}
    # find orphans (mostly just Style that were only used by removes StyleMaps)
    references = {str(el.text)[1:]: True for el in doc.xpath("//*[local-name()='styleUrl']")}
    for el in doc.xpath(ur"//*[@id and (local-name()='StyleMap' or local-name()='Style')]"):
        style_id = str(el.attrib['id'])
        if style_id not in references:
            oparent = el.getparent()
            if oparent is not None:
                oparent.remove(el)


def read_namespaces(filepath_or_url, root_element='kml', peek_length=10240):
    """
    read namespaces and prefixes used in the document
    :rtype : dict
    """
    with open(filepath_or_url) as kml_file:
        beginning = kml_file.read(peek_length)

    match = re.search(r'<%s([^>]*)>' % re.escape(root_element), beginning)

    if match is None:
        raise TypeError("Expected element with the tag %s but didn't find one in the first %d bytes of the file." % (root_element, peek_length))

    return dict([(m.group(1), m.group(2)) for m in re.finditer(r'\w+(?::(\w+))?="([^"]*)"', match.group(0))])


def dump_namespace_table(namespaces_dict, outfile=sys.stdout, prefix_title='Prefix', url_title='Namespace URL', none_text='-none-', table_format='text'):
    """
    output table of namespaces
    :param namespaces_dict: dictionary where the keys are the prefixed and values are the namespace URLs
    :param outfile: destination of output
    :param prefix_title: label of prefix column
    :param url_title: label of url column
    :param none_text: value used for key of None
    :param table_format: 'text' or 'json'
    """
    prefixes = sorted([k for k in namespaces_dict.iterkeys()])
    max_prefix_len = max(max([len(str(k)) for k in prefixes]), len(prefix_title), len(none_text))
    max_url_len = max([len(v) for v in namespaces_dict.itervalues()])
    ns_list = []
    if table_format == "text":
        print("{key:<{width}s} {url}".format(key=prefix_title, width=max_prefix_len, url=url_title), file=outfile)
        print('-' * max_prefix_len, '-' * max_url_len, file=outfile)
    for prefix in prefixes:
        if table_format == "json":
            ns_list.append({'prefix': 'null' if prefix is None else prefix, 'url': namespaces_dict[prefix]})
        elif table_format == "text":
            print("{key:<{width}} {url}".format(key=none_text if prefix is None else prefix, width=max_prefix_len, url=namespaces_dict[prefix]), file=outfile)
        else:
            raise NotImplemented("namespace table format of '%s' not implemented" % table_format)


all_placemark_paths_old = '//*[local-name()="Placemark" and *[local-name()="LineString"]]'
all_placemark_paths = '//*[local-name()="Placemark" and (*[local-name()="LineString"] or *[local-name()="MultiGeometry" and *[local-name()="LineString"]])]'
all_placemarks = '//*[local-name()="Placemark"]'


def export_geojson(doc, out_file=None, pretty=False):

    # def add(node, ):
    #     return node.coords;
    #
    # top = doc.xpath('//*[local-name()="Document"]')

    paths = doc.xpath(all_placemark_paths)
    cache = {}

    geo = {
        'type': "FeatureCollection",
        'features': []
    }

    for el in paths:

        place = Placemark(el, doc)
        style = place.get_path_color_width_opacity(cache=cache)
        color = '#'+style[0]
        opacity = round(style[2], 3)
        width = style[1]
        feature = {
            'type': "Feature",
            'properties': {
                "stroke": color,
                "stroke-width": float(width),
                "stroke-opacity": opacity
            }
        }
        name = place.get_name()
        if name and name != '':
            feature['properties']['name'] = name
        o = {
            'type': 'LineString',
            'coordinates': place.coordinates
        }
        feature['geometry'] = o

        geo['features'].append(feature)

    print(json.dumps(geo, indent=4 if pretty else None, cls=FilteringAttrDictEncoder), file=out_file)


def validate_styles(doc):
    refs = {}
    targets = {}

    style_refs = doc.xpath(".//*[local-name()='styleUrl']")
    for style_ref in style_refs:
        style_id = style_ref.text[1:]
        if style_id not in refs:
            refs[style_id] = 0
        refs[style_id] += 1

    styles = doc.xpath("//*[local-name()='Style' or local-name()='StyleMap']")
    for style in styles:
        if 'id' in style.attrib:
            style_id = style.attrib['id']
            if style_id not in targets:
                targets[style_id] = 1
            else:
                print("Error: two or more styles exists with the same id '%s" % style_id, file=out_diag)

    id_len = 0
    for style_id in targets.keys():
        id_len = max(id_len, len(style_id))
    for style_id in refs:
        id_len = max(id_len, len(style_id))

    for style_id in sorted(targets.keys()):
        print(('%'+str(id_len)+'s : %s') % (style_id, str(refs[style_id]) if style_id in refs else '0 [orphan]'))
    for style_id in sorted(refs.keys()):
        if style_id not in targets:
            print(('%'+str(id_len)+'s : %d %s') % (style_id, refs[style_id], 'Style or StyleMap missing'))


def combine_kml(doc, combine_file, filters):
    combine_et = parse_kml(combine_file, out_diag)

    combine_doc = combine_et.getroot()

    nodes = list_nodes(combine_doc, filters if len(filters) else [all_root_features])

    if len(nodes) == 0:
        print("Error")

    if args.verbose:
        print("%d features were found in combine kml file" % len(nodes), file=out_diag)

    doc_el = doc.Document

    content = doc_el.xpath(child_features)
    style_pos_index = doc_el.index(content[0]) if len(content) else max(0, doc_el.countchildren()-1)

    for node in nodes:
        doc_el.append(node)

        style_refs = node.xpath(".//*[local-name()='styleUrl']")

        for style_ref in style_refs:
            style_id = style_ref.text[1:]
            els = combine_doc.xpath(ur'//*[@id="%s"]' % style_id if "'" in style_id else ur"//*[@id='%s']" % style_id)
            if len(els) == 0:
                print("Warning: Style/StyleMap not found with id '%s'" % style_id, file=out_diag)
                continue
            el = els[0]

            i = 0
            new_id = style_id
            while len(doc.xpath(ur'//*[@id="%s"]' % new_id if "'" in style_id else ur"//*[@id='%s']" % new_id)):
                i += 1
                new_id = "%s-%03d" % (style_id, i)
            if i > 0:
                style_ref.getparent().styleUrl = objectify.StringElement('#' + new_id)
                el.attrib['id'] = new_id

            doc_el.insert(style_pos_index, els[0])

            # StyleMaps can have styleUrl children so copy those over also
            style_refs = el.xpath(".//*[local-name()='styleUrl']")

            for style_url_ref in style_refs:
                style_id = style_url_ref.text[1:]
                els = combine_doc.xpath(ur'//*[@id="%s"]' % style_id if "'" in style_id else ur"//*[@id='%s']" % style_id)
                if len(els) == 0:
                    print("Warning: Style/StyleMap not found with id '%s'" % style_id, file=out_diag)
                    continue
                el = els[0]

                i = 0
                new_id = style_id
                while len(doc.xpath(ur'//*[@id="%s"]' % style_id if "'" in style_id else ur"//*[@id='%s']" % style_id)):
                    i += 1
                    new_id = "id-%3d" % i
                if i > 0:
                    style_url_ref.getparent().styleUrl = objectify.StringElement('#' + new_id)
                    el.attrib['id'] = new_id

                doc_el.insert(style_pos_index, els[0])


def parse_kml(kml_file, diag_file=sys.stderr, exit_on_parse_error=False, exit_on_error=True):

    kml_etree = None

    try:
        kml_etree = kmlparser.parse(kml_file)

    except lxml_etree.XMLSyntaxError, e:
        print("KMLUTIL ERROR: an xml parsing error was encountered while interpreting input kml data, unable to continue", file=diag_file)
        print("MESSAGE: %s" % e.message, file=diag_file)
        if args.reraise_errors:
            raise
        raise KMLError("Error parsing kml document")

    except IOError, e:
        print("KMLUTIL ERROR: an I/O error was encountered while reading input, unable to continue", file=diag_file)
        print("MESSAGE: %s" % e.message, file=diag_file)
        if args.reraise_errors:
            raise
        raise KMLError("Error reading kml document")

    return kml_etree


def nicify(it):
    return re.sub(ur'^(\d+\.\d$|\d+|\d+\.\d\d)(?:\.\d|\d*)$', ur'\1', str(it)) if isinstance(it, float) else str(it)


def get_path_style_stats(doc):
    path_style_map = {}
    cache = {}

    for idx, el in enumerate(doc.xpath(all_placemark_paths)):
        place = Placemark(el, doc)
        if not place.has_coords():
            continue
        parts = place.get_path_color_width_opacity(cache=cache)
        sig = '-'.join([nicify(it) if isinstance(it, float) else str(it) for it in parts]) if len(parts) else 'UNSTYLED'

        if sig not in path_style_map:
            path_style_map[sig] = {'sig': sig, 'count': 1, 'color': parts[0], 'width': parts[1], 'opacity': parts[2]}
        else:
            path_style_map[sig]['count'] += 1

    return path_style_map


def process(options):
    """

    :rtype : None
    """
    global args, verboseness, out_diag, out_stats, out_kml

    args = options
    if args.verbose > 0:
        util.set_verbosity(args.verbose)

    # error messages and 'verbose' output
    out_diag = (open(os.devnull, 'w') if options['out_diag'] is None else options['out_diag']) if "out_diag" in options else sys.stderr
    # statistics
    out_stats = (open(os.devnull, 'w') if options['out_stats'] is None else options['out_stats']) if "out_stats" in options else sys.stderr
    # output kml
    out_kml = (open(os.devnull, 'w') if options['out_kml'] is None else options['out_kml']) if "out_kml" in options else sys.stdout
    # output kml meta-data (feature names, sizes etc)
    out_list = (open(os.devnull, 'w') if options['out_list'] is None else options['out_list']) if "out_list" in options else sys.stderr
    # output of namespace map
    out_nsmap = (open(os.devnull, 'w') if options['out_nsmap'] is None else options['out_nsmap']) if "out_nsmap" in options else sys.stderr

    # 0 - no output other than ERROR:
    # >=1 - PARAM:    parameter
    # >=2 - PROGRESS: progress output ["-v -v" or "-vv"]
    # >=3 - DETAIL:   detailed output
    # >=4 - DEBUG:    debugging output
    # >=5 - TRACE:    detailed debugging output
    verboseness = args.verbose
    v1 = args.verbose >= 1
    v2 = args.verbose >= 2
    v3 = args.verbose >= 3
    # v4 = args.verbose >= 4
    v5 = args.verbose >= 5

    kml_et = parse_kml(args.kmlfile, diag_file=out_diag, exit_on_parse_error=True)
    kml_doc = kml_et.getroot()
    pre_stats = None
    pre_stats_points = {}

    if args.stats:
        if v1:
            print("PROGRESS: recording 'before' statistics", file=out_diag)
        pre_stats = doc_stats(kml_doc)
        pre_stats_points = doc_stats(kml_doc, points=True)

    if args.combine:
        combine_kml(kml_doc, args.combine, args.combine_filter)

    if args.demulti_paths:
        demulti_paths(kml_doc)

    if args.extract:
        extract_nodes(kml_doc, args.extract)

    if args.paths_only:
        paths_only(kml_doc)

    if args.delete:
        delete_nodes(kml_doc, args.delete)

    if args.delete_styles:
        remove_all_styles(kml_doc)

    if len(args.rename):
        rename_placemarks(kml_doc, args.rename)

    if args.serialize_names:
        i = 0
        if v1:
            print("PROGRESS: rename paths that are named 'Path' or 'Untitled Path' to add a serial number at least", file=out_diag)
        for element in kml_doc.xpath(placemark_2name_and_type_xpath % ("Path", "Untitled Path", "LineString")):
            element.name = objectify.StringElement("Path %d" % i)
            i += 1

    if args.region:
        if args.region_file and args.verbose > 1:
            print("PROGRESS: parsing region document ", file=out_diag)
        try:
            regions_et = kmlparser.parse(args.region_file if args.region_file else args.kmlfile)
        except IOError, e:
            print("KMLUTIL ERROR: Unable to read external region kml document", file=out_diag)
            if args.reraise_errors:
                raise
            raise KMLError("External region document not readable")
        except lxml_etree.XMLSyntaxError, e:
            info = {
                'file': e.filename if e.filename is not None else 'n/a',
                'line': str(e.lineno) if e.lineno is not None else 'n/a',
                'offset': str(e.offset) if e.offset is not None else 'n/a',
                'message': str(e.message) if e.message is not None else 'n/a',
            }
            print("KMLUTIL ERROR: Error parsing external region kml document: file: '{file}' line {line} offset {offset} message '{message}' ".format(**info), file=out_diag)
            if args.reraise_errors:
                raise
            raise KMLError("External region document not parsable")

        regions_doc = regions_et.getroot()

        if v1:
            print("PROGRESS: searching for cropping region named: '%s'" % args.region, file=out_diag)

        region = Placemark.find_by_name_and_type(args.region, "Polygon", regions_doc)
        if region is not None and len(region):
            if v1:
                print("PROGRESS: Found region Polygon with %d coords" % len(region.coordinates), file=out_diag)
        else:
            folder = Placemark.find_folder_by_name(args.region, regions_doc)
            if folder is not None:
                region = Placemark.find_by_type("Polygon", folder)
                if region and args.verbose > 1:
                    print("PROGRESS: Found region Folder with Polygon with %d coords" % len(region.coordinates), file=out_diag)

        if region is None or len(region) == 0:
            print("KMLUTIL ERROR: Unable to find suitable region with name '%s'" % args.region, file=out_diag)
            raise KMLError("Region not found")

        if v2:
            print("PROGRESS: comparing all Placemark elements against region", file=out_diag)

        for el in kml_doc.xpath(all_placemarks):
            placemark = Placemark(el, kml_doc)
            if v3 and not v5:
                print("TRACE: Element '%s' with %d coordinates" % (placemark.name, len(placemark.coordinates)), file=out_diag)

            if placemark.is_path_or_multipath():
                if args.optimize_paths:
                    placemark.simplify_path()
                elif args.optimize_coordinates:
                    placemark.optimize_coordinates()

            detail = placemark.in_region(region, detail=True)
            any_in = detail[2] if isinstance(detail, tuple) else False

            if verboseness > 3:
                print("DEBUG: Checking Placemark '%32s' against region: in: %5s %5s %5s %5s %5d %5d %5d" %
                      (placemark.get_name(), detail[0], detail[1], detail[2], detail[3], detail[4], detail[5], detail[6]), file=out_diag)

            if not any_in:
                placemark.delete()

    else:
        if args.optimize_paths:
            for el in kml_doc.xpath(all_placemark_paths):
                placemark = Placemark(el, kml_doc)
                if placemark.is_path_or_multipath():
                    if args.optimize_paths:
                        placemark.simplify_path()
                    elif args.optimize_coordinates:
                        placemark.optimize_coordinates()

    if args.optimize_styles:
        optimize_styles(kml_doc)

    if args.stats:
        element_counts = []
        point_counts = []
        path_types = []
        after = doc_stats(kml_doc)
        max_len = 0
        for key in pre_stats.iterkeys():
            max_len = len(key) if len(key) > max_len else max_len
        if args.stats_format == 'text':
            print("=== Counts by Element Type ===")
            print((" {0:>%ds} {1:>7} {2:>7}  {3}" % max_len).format("Element", "Input", "Output", "Delta"), file=out_stats)
        line_format = " {0:>%ds} {1:>7} {2:>7}{3:8.2%%}" % max_len
        for e in sorted(pre_stats.iteritems(), key=operator.itemgetter(1), reverse=True):
            f = after[e[0]] if e[0] in after else 0
            p = float(e[1] - f) / float(e[1])
            if args.stats_format == 'json':
                element_counts.append({
                    'tag': e[0],
                    'pre_count': e[1],
                    'post_count': f,
                    'percentage': "{0:8.2%}".format(p)
                })
            else:
                print(line_format.format(e[0], e[1], f, p), file=out_stats)

        if args.optimize_paths or args.stats_detail:
            after_points = doc_stats(kml_doc, points=True)
            if args.stats_format == 'text':
                print("")
                print("=== Coordinate Point Count by Element Type ===", file=out_stats)
                print((" {0:>%ds} {1:>7} {2:>7}  {3}" % max_len).format("Element", "Input", "Output", "Delta"), file=out_stats)
            for e in sorted(pre_stats_points.iteritems(), key=operator.itemgetter(1), reverse=True):
                if e[0] and int(e[1]):
                    f = after_points[e[0]] if e[0] in after_points else 0
                    p = float(e[1] - f) / float(e[1])
                    if args.stats_format == 'json':
                        pass
                        point_counts.append({
                            'tag': e[0],
                            'pre_count': e[1],
                            'post_count': f,
                            'percentage': "".format(p)
                        })
                    else:
                        print(line_format.format(e[0], e[1], f, p), file=out_stats)

        if args.stats_format == 'text':
            print("")
            print("=== Path Style Counts === <color>-<width>-<opacity>", file=out_stats)

        path_style_map = get_path_style_stats(kml_doc)
        for sig in sorted(path_style_map.keys(), key=lambda x: -path_style_map[x]['count']):
            data = path_style_map[sig]
            if args.stats_format == 'json':
                path_types.append(data)
            else:
                print("{0:>24s} {1:>6d}".format(sig, data['count']), file=out_stats)

        if args.stats_format == 'json':
            print(json.dumps({
                'element_counts': element_counts,
                'point_counts': point_counts,
                'path_style_counts': path_types
            }, indent=4), file=out_stats)

    if args.folderize:

        if args.verbose > 3:
            print("{name:20s} {place:20s} {inout:6s} {per:7s}   {dump:s}".format(
                name="Boundry",
                place="Placemark",
                inout="in/out",
                per="Contain",
                dump="Deatil (begins, ends, any, all,count,total,seg)"),
                file=out_diag)

            print("{name:20s} {place:20s} {inout:6s} {per:7s}   {dump:s}".format(
                name="-" * 20,
                place="-" * 20,
                inout="-" * 6,
                per="-" * 7,
                dump="-" * 47),
                file=out_diag)

        folders = find_boundry_folders(kml_doc)

        for el in kml_doc.xpath(all_placemarks):

            placemark = Placemark(el, kml_doc)

            if placemark.is_path() or placemark.is_point() or (placemark.is_polygon() and placemark.get_name() != 'Boundry'):

                max_folder = None
                max_ratio = 0
                max_area = 0

                for folder in folders:

                    inness = placemark.in_region(folder.polygon, detail=True)
                    if inness is False:
                        continue
                    ratio = 0.0 if inness[5] == 0 else inness[4] / float(inness[5])

                    if ratio > args.folderize_limit and (ratio > max_ratio or (ratio == max_ratio and folder.area < max_area)):
                        max_folder = folder
                        max_ratio = ratio
                        max_area = folder.area

                    if args.verbose > 3:
                        print("{name:20.20s} {place:20.20s} {inout:6s} {per:6.2f}%   {dump:s}".format(
                            name=folder.name,
                            place=placemark.get_name(),
                            inout="IN" if inness[3] else "out",
                            per=ratio * 100.0,
                            dump=str(inness)),
                            file=out_diag)

                if max_folder:
                    if args.verbose > 3:
                        print("Moving into: " + max_folder.name, file=out_diag)

                    max_folder.element.append(placemark.placemark_element)

    if args.optimize_styles:
        objectify.deannotate(kml_doc, xsi_nil=True)

    if args.validate_styles:
        validate_styles(kml_doc)

    multies = kml_doc.xpath('//*[local-name()="MultiGeometry" and *[local-name()="LineString"]]')
    if len(multies):
        print(('Note: your input file appears to contain %d MultiGeometry path%s which are poorly supported in many ' +
               'applications which accept KML files. You can use the use the --demulti-paths option to convert ' +
               'MultiGeometry paths to simple paths. This usually has little to no visual affect on typical file but it is ' +
               'possible that some data or meta-data will be lost or changed unexpectantly. Making a backup is' +
               'strongly reccomended.') % (len(multies), '' if len(multies) == 1 else 's'))

    if args.dump_path:
        dump(kml_doc, args.dump_path, out_list=out_list)
    elif args.tree or args.list:
        print_list(kml_doc, args.filter, tree=args.tree, out_list=out_list, xpaths=args.list_with_xpaths, list_format=args.list_format if 'list_format' in args else 'text')

    if args.namespaces:
        nsmap = read_namespaces(args.kmlfile)
        if nsmap:
            dump_namespace_table(nsmap, outfile=out_nsmap, table_format=args.list_format if 'list_format' in args else 'text')

    if out_kml is not None:
        if args.geojson:
            export_geojson(kml_doc, pretty=args.pretty_print, out_file=out_kml)
        else:
            kml_et.write(out_kml, pretty_print=args.pretty_print)
