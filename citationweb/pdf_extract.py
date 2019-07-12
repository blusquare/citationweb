"""This module implements functions to extract information from PDF files"""

import os
import logging
import warnings
import shutil
import subprocess
from xml.etree import ElementTree
from typing import List, Union

import PyPDF2 as pdf

from .tools import load_cfg
from .crossref import search_for_doi


# Local constants
cfg = load_cfg(__name__)
log = logging.getLogger(__name__)

MAX_NUM_PAGES = cfg['max_num_pages']

# -----------------------------------------------------------------------------
# Custom error messages

class PdfExtractError(Exception):
    """Base class for pdf extraction errors"""

    def __init__(self, path, *args, **kwargs):
        """Store the path of the PDF"""
        self.path = path

        super().__init__(*args, **kwargs)

class TooManyPages(PdfExtractError):
    """Raised when the file exceeded the allowed number of pages"""

class PdfNotReadable(PdfExtractError):
    """Raised when the file could not be read via pdf-extract"""

# -----------------------------------------------------------------------------

def extract_refs_from_pdf(path: str, *,
                          max_num_pages=MAX_NUM_PAGES) -> List[str]:
    """Given the path to a PDF file, tries to extract the referenced DOIs.
    
    Args:
        path (str): The path to the PDF file
        max_num_pages (TYPE, optional): Description
    
    Returns:
        List[str]: The list of DOIs
    
    Raises:
        EnvironmentError: If pdf-extract was not installed
        PdfNotReadable: If the pdf was not readable
        TooManyPages: If the pdf was too long
    """

    # Check, if pdf-extract installed
    if shutil.which('pdf-extract') is None:
        raise EnvironmentError("pdf-extract was not found, but is necessary "
                               "to extract citations from the PDF files. "
                               "Please check, if it is installed.")

    # Get the basename
    pdf_name = os.path.basename(path)

    # Get the page count and check whether it exceeds the maximum allowed num
    num_pages = count_pages(path)

    if num_pages > max_num_pages:
        raise TooManyPages(path,
                           "{} had {} > {} number of pages."
                           "".format(pdf_name, num_pages, max_num_pages))

    # Go ahead ...
    log.info("Extracting references from %s (%s pages) ...",
             os.path.basename(path),
             num_pages if num_pages != 0 else '?')

    # Define the command and call it using subprocess
    cmd = ("pdf-extract", "extract", "--references")
    #, "--set", "reference_flex:4")

    try:
        output  = subprocess.check_output(cmd + [path],
                                          shell=False,
                                          stderr=subprocess.STDOUT)

    except subprocess.CalledProcessError as exc:
        # does not work with this file
        raise PdfNotReadable(path, str(exc))

    except KeyboardInterrupt:
        log.warning("--- Cancelled reading %s ---", pdf_name)
        raise 

    # extract DOIs from the XML output and return
    dois = get_dois_from_xml(output)
    log.info("  Extracted %d DOIs from %s.", len(dois), pdf_name)

    return dois

# -----------------------------------------------------------------------------
# reference resolving

def get_dois_from_xml(xml_str: str, ref_key: str='reference') -> List[str]:
    """This method parses an xml string and returns a list of found DOIs"""
    
    def prepare_xml(s: str) -> str:
        """Preprocesses the XML string to be readable by the XML parser"""

        log.debug("Pre-processing XML string:\n\n%s\n", s)

        xml_start = '<?xml version="1.0"?>'
        xml_end = '</pdf>'

        s = str(s)
        s = s.replace(r"\n"," ")
        s = s.replace("<pdf/>", "<pdf></pdf>")

        # if nothing was found, the xml consists only of '<?xml ...?>\n<pdf/>'
        # and in that case, no further stuff should be tried to be stripped
        # away.
        # Note that .find returns -1 when the search string is not found.
        if s.find(xml_start) >= 0 and s.find(xml_end) >= 0:
            s = s[s.find(xml_start):s.find(xml_end)+len(xml_end)]

        log.debug("XML string after pre-processing:\n\n%s\n", s)

        return s

    # Prepare XML string
    log.debug("Pre-processing XML string and then parsing ...")
    xml_processed = prepare_xml(xml_str)

    try:
        # Get the root of the xml tree
        root = ElementTree.fromstring(xml_processed)

    except ET.ParseError as xml_err:
        log.error("Error in parsing XML: %s\n\n%s\n", xml_err, xml_processed)
        raise

    else:
        log.debug("XML parsing succeeded.")
    
    # Get the reference nodes
    ref_nodes = root.findall(ref_key)

    if not ref_node:
        log.debug("No references were available or could be resolved.")
        return []
    log.debug("Found %d reference nodes.", len(ref_nodes))

    # Check if the order parameter starts at 1
    order_vals = [r.get('order') for r in ref_nodes]
    order_vals = [int(order) for order in order_vals if order is not None]
    if min(order_vals) > 1:
        log.warning("Extracted references do not start at 1. Probably a block "
                    "of references was not detected as such...")

    # Extract DOIs
    dois = [get_doi_from_ref(r) for r in ref_nodes]

    # Remove the Nones and return
    return [doi for doi in dois if doi is not None]

def get_doi_from_ref(ref) -> Union[str, None]:
    """Given a reference as an XML element, tries to extract the doi form it.

    First, tries to find the doi key. If that is not available, makes a call
    to crossref to find the doi by name of the publication.
    """
    doi = ref.get('doi')
    if doi:
        return doi
    # else: no DOI available

    # If there is no citation text, we can't do anything about this.
    if not ref.text:
        log.debug("No citation text available to search for DOI.")
        return None

    # Yay, let's search for it via the crossref API
    return search_for_doi({'query.bibliographic': ref.text})


# -----------------------------------------------------------------------------
# PDF tools

def count_pages(path: str, **read_kwargs) -> int:
    """Returns the number of pages of a PDF document"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pdf.PdfFileReader(path, **read_kwargs).numPages
