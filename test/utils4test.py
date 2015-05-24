import json
from attrdict import AttrDict


def xpath(el, xpathexp):
    return el.xpath(xpathexp, namespaces={'k': 'http://www.opengis.net/kml/2.2'})


def xpath_count(el, xpathexp):
    return len(el.xpath(xpathexp, namespaces={'k': 'http://www.opengis.net/kml/2.2'}))


def stats_counts_to_dict(stats, fill_features=["Point", "LineString", "Polygon", "Folder", "Style", "StyleMap", "Placemark", "MultiGeometry"]):
    data = stats if isinstance(stats, list) else json.loads(stats)
    counts = AttrDict({item['tag']: AttrDict(item) for item in data['element_counts']})
    if fill_features is not None and fill_features is not False:
        for tag in fill_features:
            if tag not in counts:
                counts[tag] = AttrDict({
                    "post_count": 0,
                    "pre_count": 0,
                    "tag": tag,
                    "percentage": "   0.00%"
                })

    return counts


# return if string, return comma delimited if list of strings
def flatten(s, quote_with='', after_comma=' '):
    return quote_with + s + quote_with if is_str(s) else (',' + after_comma).join([quote_with + s + quote_with for s in s])


def is_str(s):
    return hasattr(s, 'zfill')  # solves basestring/str issue with python 2.x vs 3.x
