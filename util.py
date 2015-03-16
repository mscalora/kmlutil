import sys
from cStringIO import StringIO
import attrdict
import json


class attrDictEncoder(json.JSONEncoder):
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


