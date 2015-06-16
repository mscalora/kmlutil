from __future__ import print_function
import sys
from cStringIO import StringIO
import attrdict
import json

_verbose = 0


def set_verbosity(n):
    global _verbose
    _verbose = n


class AttrDictEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, attrdict.AttrDict):
            return obj._mapping
        return json.JSONEncoder.default(self, obj)


class CapturingStdout(list):

    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._stringio = StringIO()
        return self

    def __exit__(self, *args):
        self.extend(self._stringio.getvalue().splitlines())
        sys.stdout = self._stdout


class CapturingStderr(list):

    def __enter__(self):
        self._stderr = sys.stderr
        sys.stderr = self._stringio = StringIO()
        return self

    def __exit__(self, *args):
        self.extend(self._stringio.getvalue().splitlines())
        sys.stderr = self._stderr


def nice_num(number):
    s = unicode(number)
    return s.rstrip('0').rstrip('.') if '.' in s else s


def encode_xpath_string_literal(s):
    if "'" not in s: return "'%s'" % s
    if '"' not in s: return '"%s"' % s
    return "concat('%s')" % s.replace("'", "',\"'\",'")


def get_by_id(doc, el_id, cache=None):
    if cache is not None:
        result = None
        if len(cache) == 0:
            for el in doc.xpath(ur'.//*[@id]'):
                cache[str(el.attrib['id'])] = el
        return cache[el_id] if el_id in cache else None

    els = doc.xpath(ur'.//*[@id=%s]' % encode_xpath_string_literal(el_id))
    return els[0] if len(els) else None


def tag(el):
    return el.tag.split('}')[-1]


def chain(el, attr_chain, cache=None):
    it = el
    for attr in attr_chain.split(';'):
        if attr[0] == '{':
            els = xp(it, attr[1:-1])
            if len(els) == 0:
                it = None
            else:
                it = els[0]
        elif attr == '@':
            it = get_by_id(el.getroottree(), str(it).lstrip('#'), cache=cache)
        elif hasattr(it, attr):
            it = it.text if attr == 'text' else it[attr]
        else:
            it = None

        if it is None:
            break
    return it


def xp(el, xpath):
    if _verbose > 2:
        pass # print('xpath={xpath} on {tag}[{el}]'.format(xpath=xpath, tag=el.tag.split('}')[-1], el=el.getroottree().getpath(el)), file=sys.stderr)
    return el.xpath(xpath, namespaces=dict({'kml': 'http://www.opengis.net/kml/2.2'}, **{k: v for k, v in el.nsmap.items() if k is not None}))
