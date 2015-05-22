import sys
from cStringIO import StringIO
import attrdict
import json


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


def encode_xpath_string_literal(s):
    if "'" not in s: return "'%s'" % s
    if '"' not in s: return '"%s"' % s
    return "concat('%s')" % s.replace("'", "',\"'\",'")


def get_by_id(doc, el_id):
    els = doc.xpath(ur'.//*[@id=%s]' % encode_xpath_string_literal(el_id))
    return els[0] if len(els) else None


def tag(el):
    return el.tag.split('}')[-1]


def chain(el, attr_chain):
    it = el
    for attr in attr_chain.split(';'):
        if attr[0] == '{':
            els = xp(it, attr[1:-1])
            if len(els) == 0:
                it = None
                break
            it = els[0]
        elif attr == '@':
            els = get_by_id(el.getroottree(), str(it).lstrip('#'))
            if len(els) == 0:
                it = None
                break
            it = els[0]
        elif hasattr(it, attr):
            it = it.text if attr == 'text' else it[attr]
        else:
            it = None
            break
    return it


def xp(el, xpath):
    return el.xpath(xpath, namespaces={'k': 'http://www.opengis.net/kml/2.2'})
