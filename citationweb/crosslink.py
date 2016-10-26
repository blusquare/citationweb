# -*- coding: utf-8 -*-
'''This file containts the crosslink method and the interface to the reference-extracting pdf-extract tool.'''

# TODO
# 	- implement test if pdf-extract is installed or not
#	- skip books


import re
import os
from base64 import b64decode
import subprocess
import xml.etree.ElementTree as ET

from pybtex.database import BibliographyData

from .functions import _str_to_list, _append_citekey

def crosslink(bdata):
	'''The crosslink method extracts citations from each pdf in the bibliography and checks if the target entries are in the bibliography -- if that is the case, the target citekey is added to the 'Cites' field of the bibliography entry.

	For extracting citations, the ruby pdf-extract tool by CrossRef is used: https://github.com/CrossRef/pdfextract

	To turn the Bdsk-File-N fields of each bibliography entry into a readable path, ___ is used.'''

	# Checks
	if not isinstance(bdata, BibliographyData):
		raise TypeError("Expected {}, got {}.".format(type(BibliographyData), type(bdata)))

	# Initialisations
	cnt 	= (0, len(bdata.entries))
	cmd 	= ["pdf-extract", "extract", "--resolved_references"]
	max_num_pages = 25

	# Looping over all entries
	for citekey in bdata.entries.keys():
		entry 	= bdata.entries[citekey]

		cnt 	= (cnt[0]+1, cnt[1])

		# # for testing only Hordijk2013a
		# if cnt[0] != 22:
		# 		continue
		print("\n{}/{}:".format(*cnt), end='')

		for path in _resolve_filepaths(entry):
			num_pages = _count_pages(path)

			print("\tExtracting citations from {} ({} pages)".format(os.path.basename(path), num_pages))

			if num_pages > max_num_pages:
				print("too many (>{}) pages --> skipping file".format(max_num_pages))
				continue

			# Get citations. Output is terminal prints + xml with results
			try:
				output 	= subprocess.check_output(cmd + [path],
			    	                              shell=False,
			        	                          stderr=subprocess.STDOUT)
			except subprocess.CalledProcessError:
				# does not work with this file
				print("\t(not readable)")
				continue

			except KeyboardInterrupt:
				print("\n-- Cancelled --")
				exit()


			# parse XML
			try:
				root 	= ET.fromstring(_prepare_xml(output))
			except ET.ParseError as xml_err:
				print("Error in parsing XML: {}".format(xml_err))
				continue

			# Extract DOIs
			for res_ref in root.findall("resolved_reference"):
				print("\t{}".format(res_ref.get('doi')))


	print("\nDone crosslinking.\n")

	return bdata



# -----------------------------------------------------------------------------
# Private methods -------------------------------------------------------------
# -----------------------------------------------------------------------------

def _resolve_filepaths(entry):
	'''Turns the base64-encoded values from the Bdsk-File-N fields of an entry into actual filepaths.'''

	paths 	= []
	n 		= 1
	regex 	= r"(Users\/.*\/.*?.pdf)\\" # only first match considered

	while entry.fields.get('Bdsk-File-'+str(n)) is not None and n <= 5:
		b64 	= entry.fields.get('Bdsk-File-'+str(n))

		decoded	= str(b64decode(b64))

		match 	= re.findall(regex, decoded)

		paths.append("/" + match[0])

		n += 1

	return paths


def _prepare_xml(s):
	'''Preprocesses the xml string to be readable by the XML parser'''

	xml_start	= '<?xml version="1.0"?>'
	xml_end		= '</pdf>'

	s 	= str(s)
	s 	= s[s.find(xml_start):s.find(xml_end)+len(xml_end)]
	s 	= s.replace(r"\n"," ")

	return s

rxcountpages = re.compile(r"$\s*/Type\s*/Page[/\s]", re.MULTILINE|re.DOTALL)
def _count_pages(filename):
    data = open(filename,"rb").read()
    return len(rxcountpages.findall(str(data)))