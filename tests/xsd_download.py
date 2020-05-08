"""Taken from https://github.com/n-a-t-e/xsd_download"""
import os
import re
import urllib.request
from urllib.parse import urljoin, urlparse
from lxml import etree

XSD_DIR = "tests/files/xsd"


def url_to_path(url: str) -> str:
    """turns a URL to an XSD into a filesystem path
       eg "http://www.example.come/a/b/c.xsd" -> "./www.example.come/a/b/c.xsd"
    """
    parsed = urlparse(url)

    path = parsed.netloc + parsed.path
    return path


def localize_links(text: str, filename_complete: str) -> str:
    """ Similar to wget's --convert-links, this converts the schemaLocation
        links to be useable on local filesystem
    """
    # only converting the url-based schemaLocations here
    # eg, some will schemaLocation="../abc.xsd"
    schema_locations = re.findall('schemaLocation="(http[^"]*)"', text)

    for schema_location in schema_locations:
        path_url = url_to_path(schema_location)
        rel_path = os.path.relpath(
            os.path.dirname(path_url), os.path.dirname(filename_complete)
        )
        base_name = os.path.basename(path_url)
        text = text.replace(schema_location, rel_path + "/" + base_name)
    return text


def save_file(url: str, text: str) -> None:
    """save the XSD `text` data to file path decided by `url`
       also creates the directory structure if it doesn't exist
    """
    filename_complete = url_to_path(url)
    dir_name = os.path.dirname(XSD_DIR + "/" + filename_complete)

    # create directory structure
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

    with open(XSD_DIR + "/" + filename_complete, "w") as f:
        text_localized = localize_links(text, filename_complete)
        f.write(text_localized)
        f.close()


def download_xml_url(url: str) -> str:
    "Fetches URL, returns text of the document"
    response = urllib.request.urlopen(url).read()
    tree = etree.fromstring(response, parser=etree.XMLParser(remove_comments=True))
    xml = etree.tostring(tree).decode("utf-8")
    return xml


def download_schema(url):
    """ Calls the recursive function recursive_get_schema_locations()
    """
    # list of the URLs that have been downloaded already
    downloaded_urls = []

    def recursive_get_schema_locations(url: str, referring_url: str) -> None:
        """ Recursive function that is the heart of the script,
            stops when... TODO
        """

        # dont download same link twice
        if url not in downloaded_urls:
            downloaded_urls.append(url)
            try:
                print(f"Downloading {url}")
                xsd_data = download_xml_url(url)

            except urllib.error.URLError as e:
                print(
                    "ERROR loading {} , referenced in {} REASON: {} ".format(
                        url, referring_url, e.reason
                    )
                )
                return

            # all the XSDs linked from this file via schemaLocation
            schema_locations = re.findall('schemaLocation="([^"]*)"', xsd_data)

            # write this file in the directory structure
            save_file(url, xsd_data)

            # iterate through all schemaLocation URLs
            for schema_location in schema_locations:
                # urljoin translates relative URLs in schemaLocation to
                # absolute

                # eg:
                # >>> urljoin('http://example.com/1/2/3','../../index.html')
                # turns into: http://example.com/index.html

                line = urljoin(url, schema_location)
                recursive_get_schema_locations(line, url)

    recursive_get_schema_locations(url, url)
