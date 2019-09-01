#!/usr/bin/env python2
# Copyright 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
This module provides basic encode and decode functionality to the flashrom
memory map (FMAP) structure.

WARNING: This module has been copied from third_party/flashmap/fmap.py (see
crbug/726356 for background). Please make modifications to this file there
first and then copy changes to this file.

Usage:
  (decode)
  obj = fmap_decode(blob)
  print obj

  (encode)
  blob = fmap_encode(obj)
  open('output.bin', 'w').write(blob)

  The object returned by fmap_decode is a dictionary with names defined in
  fmap.h. A special property 'FLAGS' is provided as a readable and read-only
  tuple of decoded area flags.
"""


import logging
import struct
import sys


# constants imported from lib/fmap.h
FMAP_SIGNATURE = '__FMAP__'
FMAP_VER_MAJOR = 1
FMAP_VER_MINOR_MIN = 0
FMAP_VER_MINOR_MAX = 1
FMAP_STRLEN = 32
FMAP_SEARCH_STRIDE = 4

FMAP_FLAGS = {
    'FMAP_AREA_STATIC': 1 << 0,
    'FMAP_AREA_COMPRESSED': 1 << 1,
}

FMAP_HEADER_NAMES = (
    'signature',
    'ver_major',
    'ver_minor',
    'base',
    'size',
    'name',
    'nareas',
)

FMAP_AREA_NAMES = (
    'offset',
    'size',
    'name',
    'flags',
)


# format string
FMAP_HEADER_FORMAT = '<8sBBQI%dsH' % (FMAP_STRLEN)
FMAP_AREA_FORMAT = '<II%dsH' % (FMAP_STRLEN)


def _fmap_decode_header(blob, offset):
  """ (internal) Decodes a FMAP header from blob by offset"""
  header = {}
  for (name, value) in zip(FMAP_HEADER_NAMES,
                           struct.unpack_from(FMAP_HEADER_FORMAT,
                                              blob,
                                              offset)):
    header[name] = value

  if header['signature'] != FMAP_SIGNATURE:
    raise struct.error('Invalid signature')
  if (header['ver_major'] != FMAP_VER_MAJOR or
      header['ver_minor'] < FMAP_VER_MINOR_MIN or
      header['ver_minor'] > FMAP_VER_MINOR_MAX):
    raise struct.error('Incompatible version')

  # convert null-terminated names
  header['name'] = header['name'].strip(chr(0))
  return (header, struct.calcsize(FMAP_HEADER_FORMAT))


def _fmap_decode_area(blob, offset):
  """ (internal) Decodes a FMAP area record from blob by offset """
  area = {}
  for (name, value) in zip(FMAP_AREA_NAMES,
                           struct.unpack_from(FMAP_AREA_FORMAT, blob, offset)):
    area[name] = value
  # convert null-terminated names
  area['name'] = area['name'].strip(chr(0))
  # add a (readonly) readable FLAGS
  area['FLAGS'] = _fmap_decode_area_flags(area['flags'])
  return (area, struct.calcsize(FMAP_AREA_FORMAT))


def _fmap_decode_area_flags(area_flags):
  """ (internal) Decodes a FMAP flags property """
  return tuple([name for name in FMAP_FLAGS if area_flags & FMAP_FLAGS[name]])


def _fmap_check_name(fmap, name):
  """Checks if the FMAP structure has correct name.

  Args:
    fmap: A decoded FMAP structure.
    name: A string to specify expected FMAP name.

  Raises:
    struct.error if the name does not match.
  """
  if fmap['name'] != name:
    raise struct.error('Incorrect FMAP (found: "%s", expected: "%s")' %
                       (fmap['name'], name))


def _fmap_search_header(blob, fmap_name=None):
  """Searches FMAP headers in given blob.

  Uses same logic from vboot_reference/host/lib/fmap.c.

  Args:
    blob: A string containing FMAP data.
    fmap_name: A string to specify target FMAP name.

  Returns:
    A tuple of (fmap, size, offset).
  """
  lim = len(blob) - struct.calcsize(FMAP_HEADER_FORMAT)
  align = FMAP_SEARCH_STRIDE

  # Search large alignments before small ones to find "right" FMAP.
  while align <= lim:
    align *= 2

  while align >= FMAP_SEARCH_STRIDE:
    for offset in xrange(align, lim + 1, align * 2):
      if not blob.startswith(FMAP_SIGNATURE, offset):
        continue
      try:
        (fmap, size) = _fmap_decode_header(blob, offset)
        if fmap_name is not None:
          _fmap_check_name(fmap, fmap_name)
        return (fmap, size, offset)
      except struct.error as e:
        # Search for next FMAP candidate.
        logging.debug('Continue searching FMAP due to exception %r', e)
    align /= 2
  raise struct.error('No valid FMAP signatures.')


def fmap_decode(blob, offset=None, fmap_name=None):
  """ Decodes a blob to FMAP dictionary object.

  Arguments:
    blob: a binary data containing FMAP structure.
    offset: starting offset of FMAP. When omitted, fmap_decode will search in
            the blob.
  """
  fmap = {}

  if offset is None:
    (fmap, size, offset) = _fmap_search_header(blob, fmap_name)
  else:
    (fmap, size) = _fmap_decode_header(blob, offset)
    if fmap_name is not None:
      _fmap_check_name(fmap, fmap_name)
  fmap['areas'] = []
  offset = offset + size
  for _ in range(fmap['nareas']):
    (area, size) = _fmap_decode_area(blob, offset)
    offset = offset + size
    fmap['areas'].append(area)
  return fmap


def _fmap_encode_header(obj):
  """ (internal) Encodes a FMAP header """
  values = [obj[name] for name in FMAP_HEADER_NAMES]
  return struct.pack(FMAP_HEADER_FORMAT, *values)


def _fmap_encode_area(obj):
  """ (internal) Encodes a FMAP area entry """
  values = [obj[name] for name in FMAP_AREA_NAMES]
  return struct.pack(FMAP_AREA_FORMAT, *values)


def fmap_encode(obj):
  """ Encodes a FMAP dictionary object to blob.

  Arguments
    obj: a FMAP dictionary object.
  """
  # fix up values
  obj['nareas'] = len(obj['areas'])
  # TODO(hungte) re-assign signature / version?
  blob = _fmap_encode_header(obj)
  for area in obj['areas']:
    blob = blob + _fmap_encode_area(area)
  return blob


class FirmwareImage(object):
  """Provides access to firmware image via FMAP sections."""

  def __init__(self, image_source):
    self._image = image_source
    self._fmap = fmap_decode(self._image)
    self._areas = dict(
        (entry['name'], [entry['offset'], entry['size']])
        for entry in self._fmap['areas'])

  def get_size(self):
    """Returns the size of associate firmware image."""
    return len(self._image)

  def has_section(self, name):
    """Returns if specified section is available in image."""
    return name in self._areas

  def get_section_area(self, name):
    """Returns the area (offset, size) information of given section."""
    if not self.has_section(name):
      raise ValueError('get_section_area: invalid section: %s' % name)
    return self._areas[name]

  def get_section(self, name):
    """Returns the content of specified section."""
    area = self.get_section_area(name)
    return self._image[area[0]:(area[0] + area[1])]

  def get_section_offset(self, name):
    area = self.get_section_area(name)
    return self._image[area[0]:(area[0] + area[1])]

  def put_section(self, name, value):
    """Updates content of specified section in image."""
    area = self.get_section_area(name)
    if len(value) != area[1]:
      raise ValueError('Value size (%d) does not fit into section (%s, %d)' %
                       (len(value), name, area[1]))
    self._image = (self._image[0:area[0]] +
                   value +
                   self._image[(area[0] + area[1]):])
    return True

  def get_fmap_blob(self):
    """Returns the re-encoded fmap blob from firmware image."""
    return fmap_encode(self._fmap)


def main():
  """Decode FMAP from supplied file and print."""
  if len(sys.argv) < 2:
    print 'Usage: fmap.py <file>'
    sys.exit(1)

  filename = sys.argv[1]
  print 'Decoding FMAP from: %s' % filename
  blob = open(filename).read()
  obj = fmap_decode(blob)
  print obj


if __name__ == '__main__':
  main()
