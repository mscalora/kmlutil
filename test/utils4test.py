
def xpath(el, xpathexp):
    return el.xpath(xpathexp, namespaces={'k': 'http://www.opengis.net/kml/2.2'})


def xpath_count(el, xpathexp):
    return len(el.xpath(xpathexp, namespaces={'k': 'http://www.opengis.net/kml/2.2'}))
