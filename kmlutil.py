#!/usr/bin/env python

from __future__ import print_function
import os
import re
import sys
import operator
from math import radians, cos, sin, asin, sqrt
from pykml import parser as kmlparser
from simplify import simplify
from lxml import objectify, etree as ET
from copy import deepcopy

placemark_name_and_type_xpath = \
    ur'.//*[local-name()="Placemark" and *[local-name()="name" and text()="%s"] and *[local-name()="%s"]]'
placemark_2name_and_type_xpath = \
    ur'.//*[local-name()="Placemark" and *[local-name()="name" and (text()="%s" or text()="%s")] and *[local-name()="%s"]]'
placemark_type_xpath = \
    ur'.//*[local-name()="Placemark" and *[local-name()="%s"]]'
folder_by_name = \
    ur'.//*[local-name()="Folder" and *[local-name()="name" and text()="%s"]]'
folder_or_placemark_by_name = \
    ur'.//*[(local-name()="Folder" or local-name()="Placemark") and *[local-name()="name" and text()="%s"]]'
top_level_folder_or_placemarks = \
    ur'/*/*[local-name()="Document"]/*[local-name()="Folder" or local-name()="Placemark"]'

from util import *
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
    #mi = 3956.27 * c
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
    id_map = None
    id_style_refs = None

    def __init__(self, element, kml_doc=None):
        if kml_doc is not None and Placemark.id_map is None:
            Placemark.id_map = {}
            Placemark.id_style_refs = {}
            Placemark.populate_id_map(kml_doc)

        self.placemark_element = element
        self.kml_doc = kml_doc
        self.name = element.name if hasattr(element,"name") else None

        coords_list = self.placemark_element.xpath('.//*[local-name()="coordinates"]/text()')
        if not coords_list:
            print("Unable to extract coordinates data", file=out_diag)
            raise KMLError("Region coordinates not found")

        data_name_xpath = "//*[local-name()='Data' and @name='NAME']/*[local-name()='value']/text()"

        if self.is_multi_geometry_polygon():
            # concatenate all points for multi-geometry polygons
            self.coordinates = parse_coords(" ".join([str(s) for s in coords_list]))
        elif self.is_multi_geometry_linestring():
            self.coordinates = parse_coords(" ".join([str(s) for s in coords_list]))
        elif hasattr(element, "MultiGeometry"):
            print("Unexpected MultiGeometry element %s " % self.placemark_element.tag + self.name if self.name is not None else (
                element.xpath(data_name_xpath)[0] if len(element.xpath(data_name_xpath)) else "unnamed"))
            print(ET.tostring(element, pretty_print=True))
        else:
            self.coordinates = parse_coords(coords_list[0])
        #self.coordinates = [tuple([float(n) for n in coordinates.split(',')]) for coordinates in coords_list[0].strip().split()]

    def is_path(self):
        return hasattr(self.placemark_element, "LineString")

    def is_point(self):
        return hasattr(self.placemark_element, "Point")

    def is_polygon(self):
        return hasattr(self.placemark_element, "Polygon") or self.is_multi_geometry_polygon()

    def is_multi_geometry(self):
        return hasattr(self.placemark_element, "MultiGeometry")

    def is_multi_geometry_polygon(self):
        return hasattr(self.placemark_element, "MultiGeometry") and hasattr(self.placemark_element.MultiGeometry, "Polygon")

    def is_multi_geometry_linestring(self):
        return hasattr(self.placemark_element, "MultiGeometry") and hasattr(self.placemark_element.MultiGeometry, "LineString")

    def get_coords(self):
        return self.coordinates

    def get_name(self):
        namelist_list = self.placemark_element.xpath('.//*[local-name()="name"]/text()')
        return namelist_list[0] if namelist_list else namelist_list

    def is_point_inside(self, x, y):

        n = len(self.coordinates)
        inside = False
        xints = 0

        p1x, p1y = self.coordinates[0][0:2]
        for i in range(n + 1):
            p2x, p2y = self.coordinates[i % n][0:2]
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
        if len(self.coordinates) == 0:
            return False
        begins_in = polygon.is_point_inside(self.coordinates[0][0], self.coordinates[0][1])
        ends_in = polygon.is_point_inside(self.coordinates[-1][0], self.coordinates[-1][1])
        if not detail:
            return begins_in or ends_in
        all_in = True
        any_in = False
        points_in = 0
        segments_in = 0
        prev_in = False
        for point in self.coordinates:
            is_in = polygon.is_point_inside(point[0], point[1])
            all_in = all_in and is_in
            any_in = any_in or is_in
            if is_in:
                points_in += 1
                if not prev_in:
                    segments_in += 1
            prev_in = is_in
        return begins_in, ends_in, any_in, all_in, points_in, len(self.coordinates), segments_in

    def get_stype_sig(self):
        try:
            style_map_id = self.placemark_element.xpath(".//*[local-name()='styleUrl']/text()")[0][1:]
            style_map_el = Placemark.get_style_by_id(style_map_id)
            if style_map_el is None:
                print("Style map id not found: '%s'" % style_map_id, file=out_diag)
                return None, None, None, None
            norm_id = style_map_el.xpath('*[*[local-name()="key" and text()="normal"]]' +
                                         '/*[local-name()="styleUrl"]/text()')[0][1:]
            high_id = style_map_el.xpath('*[*[local-name()="key" and text()="highlight"]]' +
                                         '/*[local-name()="styleUrl"]/text()')[0][1:]
            norm_el = Placemark.get_style_by_id(norm_id)
            if norm_el is None:
                print("Style id not found: '%s'" % norm_el, file=out_diag)
                return None, None, None, None
            high_el = Placemark.get_style_by_id(high_id)
            if high_el is None:
                print("Style id not found: '%s'" % high_id, file=out_diag)
                return None, None, None, None
            style_map_parts = norm_el.xpath('.//*[local-name()="LineStyle"]/*[local-name()="color"]/text()')
            style_map_parts += norm_el.xpath('.//*[local-name()="LineStyle"]/*[local-name()="width"]/text()')
            style_map_parts +=  high_el.xpath('.//*[local-name()="LineStyle"]/*[local-name()="color"]/text()')
            style_map_parts +=  high_el.xpath('.//*[local-name()="LineStyle"]/*[local-name()="width"]/text()')
            if len(style_map_parts)!=4:
                return None, None, None, None

            if args.verbose > 3:
                print("StyleMap:", style_map_id, '-'.join(style_map_parts),file=out_diag)

            return style_map_parts, style_map_id, norm_id, high_id

            # if (norm_el.countchildren() != 1 or
            #         high_el.countchildren() != 1 or
            #         norm_el.getchildren()[0].tag[-9:] != "LineStyle" or
            #         high_el.getchildren()[0].tag[-9:] != "LineStyle"):
            #     return None, None, None, None
            # style_map_parts = norm_el.xpath('*/*/text()') + high_el.xpath('*/*/text()')
            # if args.verbose > 3:
            #     print("StyleMap:", style_map_id, file=out_diag)
            #     print("  Normal:",
            #           norm_el.tag.split('}')[-1], norm_el.attrib['id'] if 'id' in norm_el.attrib else '',
            #           norm_el.countchildren(), norm_el.getchildren()[0].tag.split('}')[-1],
            #           style_map_parts[0:len(style_map_parts) / 2], file=out_diag)
            #     print("  Highlight:",
            #           high_el.tag.split('}')[-1], high_el.attrib['id'] if 'id' in high_el.attrib else '',
            #           high_el.countchildren(), high_el.getchildren()[0].tag.split('}')[-1],
            #           style_map_parts[-len(style_map_parts) / 2:], file=out_diag)
            # return style_map_parts, style_map_id, norm_id, high_id
        except KMLError:
            pass
        except IndexError:
            pass
        return None, None, None, None

    def delete(self):
        self.placemark_element.xpath('./..')[0].remove(self.placemark_element)

    def simplify_path(self):
        c = self.coordinates
        if len(self.coordinates) < 10:
            return
        self.coordinates = simplify(self.coordinates, args.path_error_limit)
        if args.verbose > 2 and len(c) > len(self.coordinates):
            print("Path simplified, Was", len(c), "points long and now ", len(self.coordinates), file=out_diag)
        parent_list = self.placemark_element.xpath('.//*[*[local-name()="coordinates"]]')
        if parent_list:
            if args.optimize_coordinates:
                parent_list[0].coordinates = \
                    objectify.StringElement(" ".join([",".join(["%.6f" % p[i] for i in [0, 1]]) for p in self.coordinates]))
            else:
                parent_list[0].coordinates = \
                    objectify.StringElement(" ".join([",".join([str(i) for i in p]) for p in self.coordinates]))

    def optimize_coordinates(self):
        parent_list = self.placemark_element.xpath('.//*[*[local-name()="coordinates"]]')
        if parent_list:
            parent_list[0].coordinates = \
                objectify.StringElement(" ".join([",".join(["%.6f" % p[i] for i in [0, 1]]) for p in self.coordinates]))

    @staticmethod
    def find_folder_by_name(folder_name, context):
        if args.verbose > 2:
            print(folder_by_name % folder_name, file=out_diag)

        element_list = context.xpath(folder_by_name % folder_name)

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
            print(placemark_name_and_type_xpath % (placemark_name, placemark_type), file=out_diag)

        element_list = context.xpath(placemark_name_and_type_xpath % (placemark_name, placemark_type))

        return None if element_list is None or len(element_list) == 0 else Placemark(element_list[0])

    @staticmethod
    def populate_id_map(doc):
        for element in doc.xpath('//*[@id]'):
            Placemark.id_map[element.attrib['id']] = element

        for element in doc.xpath('//*[local-name()="styleUrl"]'):
            el_id = element.text[1:]
            if not el_id in Placemark.id_style_refs:
                Placemark.id_style_refs[el_id] = []
            Placemark.id_style_refs[el_id].append(element)

    @staticmethod
    def remove_style_id(style_id):
        Placemark.id_map.pop(style_id, None)
        Placemark.id_style_refs.pop(style_id, None)

    @staticmethod
    def add_style_id(style_id, element, refs=None):
        Placemark.id_map[style_id] = element
        Placemark.id_style_refs[style_id] = refs

    @staticmethod
    def get_style_by_id(style_id):
        """
        get element by id in constant time
        :rtype : etree.Element
        """
        return Placemark.id_map.get(style_id, None)

    @staticmethod
    def get_style_refs_by_id(style_id):
        return Placemark.id_style_refs[style_id]


def find_boundry_folders(kml_doc):
    folder_list = []

    for folder in kml_doc.xpath("//*[local-name()='Folder' and *[local-name()='Placemark' and *[local-name()='name' and text()='Boundry']]]"):
        polygon = folder.xpath("*[local-name()='Placemark' and *[local-name()='name' and text()='Boundry']]")[0]
        coords_text = folder.xpath("*[local-name()='Placemark' and *[local-name()='name' and text()='Boundry']]//*[local-name()='coordinates']/text()")[0]

        folder_list.append(AttrDict({
            'name': folder.name.text,
            'element': folder,
            #'coords': parse_coords(coords_text),
            'polygon': Placemark(polygon),
            'area': area_of_polygon(parse_coords(coords_text))
        }))
    return folder_list


def delete_orphans(kml_doc):
    """
    remove all Style and StyleMap that have an id but no styleUrl refers to them
    :return:
    """
    ref_map = {}
    for ref in kml_doc.xpath('//*[local-name()="styleUrl"]/text()'):
        ref_map[ref[1:]] = True
    for smel in kml_doc.xpath('//*[local-name()="StyleMap"]'):
        if 'id' in smel.attrib:
            stylemap_id = smel.attrib['id']
            if verboseness > 3:
                print("Checking StyleMap", stylemap_id, file=out_diag)
            if stylemap_id not in ref_map:
                if verboseness > 3:
                    print("Deleteing StyleMap", stylemap_id, file=out_diag)
                smel.xpath('./..')[0].remove(smel)
    ref_map = {}
    for ref in kml_doc.xpath('//*[local-name()="styleUrl"]/text()'):
        ref_map[ref[1:]] = True
    for sel in kml_doc.xpath('//*[local-name()="Style"]'):
        if 'id' in sel.attrib:
            style_id = sel.attrib['id']
            if verboseness > 3:
                print("Checking Style", style_id, file=out_diag)
            if style_id not in ref_map:
                if verboseness > 3:
                    print("Deleteing Style", style_id, file=out_diag)
                sel.xpath('./..')[0].remove(sel)


def count_points(element):
    count = 0
    tag = element.tag.split('}')[-1]
    if tag == "Placemark" or tag == "Point":
        coords = element.xpath('.//*[local-name()="coordinates"]/text()')
        for coord in coords:
            count += len(coord.strip().split())
    return count


def delete_nodes(doc, kml_ids):

    nodes = list_nodes(doc, kml_ids)

    print("Deleteing %d item(s)" % len(nodes), file=out_diag)

    for node in reversed(nodes):

        if args.verbose > 1:
            print("Deleteing %d item(s) named '%s'" % (len(fnodes), name), file=out_diag)

        parent = node.xpath('./..')[0]
        parent.remove(node)


def extract_nodes(doc, kml_ids):

    nodes = list_nodes(doc, kml_ids)

    if args.verbose > 1:
            print("Located %d features to extract" % len(all), file=out_diag)

    all_top_level = doc.xpath(top_level_folder_or_placemarks)

    for node in reversed(all_top_level):
        node.xpath('./..')[0].remove(node)

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
        if len(segments)>1:
            # make a copy of the whole placemark
            copy = deepcopy(multi)
            # position in the list
            parent = multi.xpath(ur'./..')[0]
            index = parent.index(multi)
            base_name = multi.name if hasattr(multi,"name") else None

        for i in reversed(range(0,len(segments))):
            if i==0:
                # use the original placemark for the first segment
                multi.append(segments[i])
            else:
                # use copies of it for subsequent segments
                node = copy if i==1 else deepcopy(copy)
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
        node.xpath('./..')[0].remove(node)

    document_element = doc.xpath(ur'/*/*[local-name()="Document"]')[0]

    for path in paths:
        document_element.append(path)

def remove_all_styles(doc):
    nodes = doc.xpath(all_style_data)

    if args.verbose > 1:
            print("Deleteing %d style related item(s)" % len(nodes), file=out_diag)

    for node in reversed(nodes):
        node.xpath('./..')[0].remove(node)


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
    for el in doc.xpath('//*'):
        uri, tag = el.tag[1:].split('}')
        if tag[0].isupper():
            if not tag in stats_map:
                stats_map[tag] = 0
            stats_map[tag] += count_points(el) if points else 1

    return stats_map


def get_path_stats(doc):
    path_stats_map = {}

    for el in doc.xpath(all_placemark_paths):
        place = Placemark(el, doc)
        if len(place.coordinates) == 0:
            continue
        parts, _, _, _ = place.get_stype_sig()

        sig = "-".join(parts if parts[0] != parts[2] or parts[1] != parts[2] else parts[0:2]) if parts else 'NONE'

        if sig not in path_stats_map:
            path_stats_map[sig] = 1
        else:
            path_stats_map[sig] += 1

    return path_stats_map


def list_filter(tag, filter_list):
    return True if filter_list is None else tag in filter_list


def lister(element, filter_list, tree=False, indent=0, recursive=True, children_only=False):
    node_list = []

    for el in element.xpath('*[local-name()="Document" or local-name()="Folder" or local-name()="Placemark"]'):
        el_tag = el.tag.split('}')[-1]
        name_ref = el.xpath('*[local-name()="name"]/text()')
        name = 'UNNAMED' if len(name_ref) == 0 else name_ref[0]
        type_list = el.xpath('*[local-name()="Polygon" or local-name()="Point" or local-name()="LineString"] | ' +
            '*/*[local-name()="Polygon" or local-name()="Point" or local-name()="LineString"]')
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

    if kml_id.startswith(('.','/')):
        return kml_id
    elif kml_id.startswith('&'):
        return folder_or_placemark_by_name % kml_id[1:]

    return folder_or_placemark_by_name % kml_id


def list_nodes(doc, kml_ids):
    xpaths = []
    if isinstance(kml_ids,list):
        xpaths  = map(kml_id_to_xpath,kml_ids)
        # for kml_id in kml_ids:
        #     xpaths.append(kml_id_to_xpath(kml_ids))
    else:
        xpaths = [kml_id_to_xpath(kml_ids)]

    nodes = doc.xpath('|'.join(xpaths))
    return nodes

def dump(kml_doc, line_name, out_list=sys.stdout):

    node_list = list_nodes(kml_doc, line_name)

    for node in node_list:
        placemark = Placemark(node, kml_doc)
        if (args.verbose):
            name = placemark.get_name()
            print("# %s" % "<unnamed>" if name is None else name, file=out_diag)
        for point in placemark.coordinates:
            print(u','.join(map(unicode, point)), file=out_list)

    # print(line_name, file=out_list)
    # for el in kml_doc.xpath(all_placemarks):
    #     placemark = Placemark(el, kml_doc)
    #     print(placemark.get_name(), file=out_list)
    #     #is_line_string =
    #     if line_name=='-' or line_name==placemark.get_name():
    #         for point in placemark.coordinates:
    #             print(','.join(point.astype(unicode)), file=out_list)


class filteringAttrDictEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, attrdict.AttrDict):
            d = dict(obj)
            d.pop('el', None)
            return d
        return json.JSONEncoder.default(self, obj)


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
    elif hasattr(doc,'Folder'):
        root = doc.Folder
    else:
        raise KMLError("Unsupported document root")

    node_list = lister(root, mapped_filter, tree=True, children_only=False)
    etree = ET.ElementTree(doc) if xpaths else None

    if list_format == 'json':

        if xpaths:
            for node in node_list:
                node.xpath = etree.getpath(node.el)
        json.dump(node_list, out_list, indent=2 if args.pretty_print else None, cls=filteringAttrDictEncoder)

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
                rate = node.length / node.count * 1000 if node.count>0 else 0.0
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
                print(detail.format(**model),file=out_list)
            else:
                simple = line  + (" {xpath:s}" if xpaths else "")
                print(line.format(name_width=name_len, name=name, type=node.type, type_width=type_len), file=out_list)


def optimize_style(placemark):
    """
    normalize style ID by content (color, line thickness) and rename existing style unless one already exists
    :param placemark:
    :return:
    """
    if placemark.is_path():
        style_parts, style_id, norm_id, high_id = placemark.get_stype_sig()
        if style_parts:
            # synthesise a name from the style attributes
            symmetric = style_parts[0] == style_parts[2] and style_parts[1] == style_parts[3]
            new_id = 'SM-' + '-'.join(style_parts[0:2 if symmetric else 4]).replace('.', '_')
            new_el = Placemark.get_style_by_id(new_id)
            old_el = Placemark.get_style_by_id(style_id)
            refs = Placemark.get_style_refs_by_id(style_id)
            # if style with synthesised name does not exist, change the id on the existing style
            if new_el is None:
                old_el.attrib['id'] = new_id
                Placemark.add_style_id(new_id, old_el, refs)
            # update the references to the style
            for style_url_el in refs:
                el = style_url_el.xpath('./..')[0]
                el.styleUrl = objectify.StringElement('#' + new_id)
            Placemark.remove_style_id(style_id)


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

def export_geojson(doc, outfile=None, pretty=False):

    # def add(node, ):
    #     return node.coords;
    #
    # top = doc.xpath('//*[local-name()="Document"]')

    paths = doc.xpath(all_placemark_paths)

    geo = {
        'type': "FeatureCollection",
        'features': []
    }

    for el in paths:

        place = Placemark(el, doc)
        sig = place.get_stype_sig()
        stroke = sig[0][0]
        color = '#'+stroke[6:8]+stroke[4:6]+stroke[2:4]
        opacity = round(int(stroke[0:2],16)/255.0,3)
        width = sig[0][1]
        feature = {
            'type': "Feature",
            'properties': {
                "stroke": color,
                "stroke-width": float(width),
                "stroke-opacity": opacity
            }
        }
        name = place.get_name()
        if name and name!='':
            feature['properties']['name'] = name
        o = {
            'type': 'LineString',
            'coordinates': place.coordinates
        }
        feature['geometry'] = o

        geo['features'].append(feature)

    print(json.dumps(geo, indent=4 if pretty else None, cls=filteringAttrDictEncoder), file=outfile)


def process(options):
    """

    :rtype : None
    """
    global args, verboseness, out_diag, out_stats, out_kml

    args = options

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
    v4 = args.verbose >= 4
    v5 = args.verbose >= 5

    kml_et = None
    try:
        kml_et = kmlparser.parse(args.kmlfile)

    except ET.XMLSyntaxError, e:
        print("ERROR: an xml parsing error was encountered while interpreting input kml data, unable to continue", file=out_diag)
        print("MESSAGE: %s" % e.message, file=out_diag)
        if v3:
            raise
        sys.exit(5)

    except IOError, e:
        print("ERROR: an I/O error was encountered while reading input, unable to continue", file=out_diag)
        print("MESSAGE: %s" % e.message, file=out_diag)
        if v3:
            raise
        sys.exit(10)

    kml_doc = kml_et.getroot()
    pre_stats = None
    pre_stats_points = {}

    if args.stats:
        if v1: print("PROGRESS: recording 'before' statistics", file=out_diag)
        pre_stats = doc_stats(kml_doc)
        pre_stats_points = doc_stats(kml_doc, points=True)

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

    if args.serialize_names:
        i = 0
        if v1: print("PROGRESS: rename paths that are named 'Path' or 'Untitled Path' to add a serial number at least", file=out_diag)
        for element in kml_doc.xpath(placemark_2name_and_type_xpath % ("Path", "Untitled Path", "LineString")):
            element.name = objectify.StringElement("Path %d" % i)
            i += 1

    if args.region:
        if args.region_file and args.verbose > 1: print("PROGRESS: parsing region document ", file=out_diag)
        regions_et = kmlparser.parse(args.region_file if args.region_file else args.kmlfile)
        regions_doc = regions_et.getroot()

        if v1: print("PROGRESS: searching for cropping region named: '%s'" % args.region, file=out_diag)

        region = Placemark.find_by_name_and_type(args.region, "Polygon", regions_doc)
        if not region:
            folder = Placemark.find_folder_by_name(args.region, regions_doc)
            if folder is not None:
                region = Placemark.find_by_type("Polygon", folder)
                if region and args.verbose > 1: print("PROGRESS: Found region Folder with Polygon with %d coords" % len(region.coordinates), file=out_diag)
        else:
            if v1: print("PROGRESS: Found region Polygon with %d coords" % len(region.coordinates), file=out_diag)

        if region is None:
            print("ERROR: Unable to find suitable region with name %s" % args.region, file=out_diag)
            raise KMLError("Region not found")

        if v2: print("PROGRESS: comparing all Placemark elements against region", file=out_diag)
        if v5:
            print("DEBUG: Checking Placemark '%32s' against region: in: %5s %5s %5s %5s %5d %5d %5d" %
                      ("Name", "Start", "EndIn", "AnyIn", "AllIn", "PtsIn", "Pts", "% In", "Segments In"), file=out_diag)
        for el in kml_doc.xpath(all_placemarks):
            placemark = Placemark(el, kml_doc)
            if v3 and not v5: print("TRACE: Element '%s' with %d coordinates" % (placemark.name, len(placemark.coordinates)), file=out_diag)

            if args.optimize_styles:
                optimize_style(placemark)

            if placemark.is_path():
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
                if placemark.is_path():
                    if args.optimize_paths:
                        placemark.simplify_path()
                    elif args.optimize_coordinates:
                        placemark.optimize_coordinates()

    if args.optimize_styles:
        for el in kml_doc.xpath(all_placemark_paths):
            placemark = Placemark(el, kml_doc)

            optimize_style(placemark)

        delete_orphans(kml_doc)

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
            print((" {0:>%ds} {1:>7} {2:>7}  {3}" % max_len).format("Element","Input","Output","Delta"), file=out_stats)
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
                print((" {0:>%ds} {1:>7} {2:>7}  {3}" % max_len).format("Element","Input","Output","Delta"), file=out_stats)
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
            print("=== Path Style Counts === <normal-color>-<size>-<highlight-color>-<size>", file=out_stats)

        path_type_map = get_path_stats(kml_doc)
        for sig, count in path_type_map.iteritems():
            if args.stats_format == 'json':
                parts = sig.split('-')
                path_types.append({
                    'color': parts[0] if len(parts) > 0 else 'n/a',
                    'width': parts[1] if len(parts) > 1 else 'n/a',
                    'count': count
                })
            else:
                print("{0:>24s} {1:>6d}".format(sig, count), file=out_stats)

        if args.stats_format == 'json':
            print(json.dumps({
                'element_counts': element_counts,
                'point_counts': point_counts,
                'path_type_counts': path_types
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
                    if inness == False:
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

    if args.dump_path:
        dump(kml_doc, args.dump_path, out_list=out_list)
    elif args.tree or args.list:
        print_list(kml_doc, args.filter, tree=args.tree, out_list=out_list, xpaths=args.list_with_xpaths, list_format=args.list_format if 'list_format' in args else 'text')

    if args.namespaces:
        nsmap = read_namespaces(args.kmlfile)
        if nsmap:
            dump_namespace_table(nsmap, outfile=out_nsmap, table_format=args.list_format if 'list_format' in args else 'text')

    if out_kml is not None:
        if (args.geojson):
            export_geojson(kml_doc, pretty=args.pretty_print, outfile=out_kml)
        else:
            kml_et.write(out_kml, pretty_print=args.pretty_print)

    doc_stats(kml_doc)
