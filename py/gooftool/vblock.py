#!/usr/bin/env python2
# Copyright 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# THIS FILE IS COPIED FROM AUTOTEST LIBRARY AND FOLLOWING PEP8 CODING STYLE RULE
# FOR BACKWARD COMPATIBLE, WE'RE NOT CHANGING ITS INDENTATION AND FUNCTION NAMES

"""
    Chrome OS firmware verification block parser.

    This module helps parsing firmware verification blocks so that we can
    retrieve the version and other information from a blob.

    See help(unpack_verification_block) for more information.

    ref: src/platform/vboot_reference/firmware/lib/include/vboot_struct.h
"""

import struct
import sys

# Constant Definition
KEY_BLOCK_MAGIC = 'CHROMEOS'
KEY_BLOCK_MAGIC_SIZE = 8
KEY_BLOCK_HEADER_VERSION_MAJOR = 2
KEY_BLOCK_HEADER_VERSION_MINOR = 1
FIRMWARE_PREAMBLE_HEADER_VERSION_MAJOR = 2
FIRMWARE_PREAMBLE_HEADER_VERSION_MINOR = 0


def unpack_VbKeyBlockHeader(blob, offset=0):
  """Unpacks a VbKeyBlockHeader from a blob, starting from offset.

  The blob is supposed to be a VBLOCK_A or VBLOCK_A in firmware image.
  Blob structure:
  typedef struct VbKeyBlockHeader {
      uint8_t magic[KEY_BLOCK_MAGIC_SIZE];
      uint32_t header_version_major;
      uint32_t header_version_minor;
      uint64_t key_block_size;
      ...
  };
  """
  fields = struct.unpack_from('<8sIIQ', blob, offset)
  names = ('magic', 'header_version_major', 'header_version_minor',
           'key_block_size')
  header = dict(zip(names, fields))
  # check values
  if header['magic'] != KEY_BLOCK_MAGIC:
    raise ValueError('unknown key block magic: %s' % header['magic'])
  major = header['header_version_major']
  minor = header['header_version_minor']
  if major != KEY_BLOCK_HEADER_VERSION_MAJOR:
    raise ValueError('unknown key block version (%d.%d)' % (major, minor))
  return header


def unpack_VbFirmwarePreambleHeader(blob, offset=0):
  """Unpacks a VbFirmwarePreambleHeader from a blob, starting from offset.

  The blob is supposed to be located immediately after a VbKeyBlockHeader.
  (i.e., offset = VbKeyBlockHeader[key_block_size])
  Blob structure:
  typedef struct VbFirmwarePreambleHeader {
      uint64_t preamble_size;
      struct VbSignature preamble_signature {
          uint64_t sig_offset;
          uint64_t sig_size;
          uint64_t data_size;
      };
      uint32_t header_version_major;
      uint32_t header_version_minor;
      uint64_t firmware_version;
      ...
  };
  """
  fields = struct.unpack_from('<QQQQIIQ', blob, offset)
  names = ('preamble_size',
           'sig_offset', 'sig_size', 'data_size',
           'header_version_major', 'header_version_minor',
           'firmware_version')
  header = dict(zip(names, fields))
  # check values
  major = header['header_version_major']
  minor = header['header_version_minor']
  if major != FIRMWARE_PREAMBLE_HEADER_VERSION_MAJOR:
    raise ValueError('unknown preamble version: (%d.%d)' % (major, minor))
  return header


def unpack_verification_block(blob, offset=0):
  """Unpacks a Chrome OS verification block.

  Returns a dictionary of VbKeyBlockHeader and VbFirmwarePreambleHeader.

  Use help(unpack_VbKeyBlockHeader) and help(unpack_VbFirmwarePreambleHeader)
  for more detail information.
  """
  result = {}
  result['VbKeyBlockHeader'] = unpack_VbKeyBlockHeader(blob, offset)
  result['VbFirmwarePreambleHeader'] = unpack_VbFirmwarePreambleHeader(
      blob, result['VbKeyBlockHeader']['key_block_size'])
  return result


# -----------------------------------------------------------------------------


def test_report_vblock_info(blob, offset=0):
  """ Reports the information of a vblock blob. """
  kb_header = unpack_VbKeyBlockHeader(blob, offset)
  print '-- VbKeyBlockHeader --'
  for name, value in kb_header.items():
    print name, ':', value
  preamble = unpack_VbFirmwarePreambleHeader(blob,
                                             kb_header['key_block_size'])
  print '-- VbFirmwarePreambleHeader --'
  for name, value in preamble.items():
    print name, ':', value
  print '-- END --'


# main stub
if __name__ == '__main__':
  # when running in command line, try to report blob in the parameters
  for filename in sys.argv[1:]:
    test_report_vblock_info(open(filename, 'rb').read())
