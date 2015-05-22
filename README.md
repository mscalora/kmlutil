# kmlutil

### Dependencies:

* lxml
* pykml
* attrdict

### To install dependencies:

    pip install lxml pykml attrdict

## Example Usage:

### View contents of file:

    $ kmlutil --tree --list-detail sample.kml
    Tracks                                   Folder   7456   19.62km    2.63m/pt
      Points                                 Folder      0    0.00km    0.00m/pt
        UNNAMED                              Point  [3728 occurances]
      Paths                                  Folder   3728   19.62km    5.26m/pt
        Current Track: 02 MAY 2015 07:18 001 Path     3728   19.62km    5.26m/pt

The indentation shows the nesting structure, use --list instead of --tree to produce a flat list.

### Extract paths only

    $ kmlutil --paths-only sample.kml -O path.kml

### Optimize paths (-p) coordinates (-c) and styles (-o)

    $ kmlutil -p -c -o sample.kml -O out.kml
