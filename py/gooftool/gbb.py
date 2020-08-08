#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Chrome OS GBB parser.

This module helps parsing GBB so that we can retrieve the HWID and other
information from a blob.

ref: src/platform/vboot_reference/firmware/2lib/include/2struct.h
"""

import collections
import struct
import sys


GBBContent = collections.namedtuple(
    'GBBContent', ['hwid', 'hwid_digest', 'rootkey', 'recovery_key'])
GBBField = collections.namedtuple('GBBField', ['value', 'offset', 'size'])


# constant definition
GBB_SIGNATURE = b'$GBB'
GBB_SIGNATURE_SIZE = 4
GBB_HWID_DIGEST_OFFSET = 48  # bytes before HWID digest section in the header
GBB_HWID_DIGEST_SIZE = 32


# blob structure
# struct vb2_gbb_header {
#   uint8_t  signature[VB2_GBB_SIGNATURE_SIZE];
#   uint16_t major_version;
#   uint16_t minor_version;
#   uint32_t header_size;
#   vb2_gbb_flags_t flags;
#   uint32_t hwid_offset;
#   uint32_t hwid_size;
#   uint32_t rootkey_offset;
#   uint32_t rootkey_size;
#   uint32_t bmpfv_offset;
#   uint32_t bmpfv_size;
#   uint32_t recovery_key_offset;
#   uint32_t recovery_key_size;
#   uint8_t  hwid_digest[VB2_GBB_HWID_DIGEST_SIZE];
#   uint8_t  pad[48];
# };


GBBHeader = collections.namedtuple('GBBHeader', [
    'signature',
    'major_version',
    'minor_version',
    'header_size',
    'flags',
    'hwid_offset',
    'hwid_size',
    'rootkey_offset',
    'rootkey_size',
    'bmpfw_offset',
    'bmpfw_size',
    'recovery_key_offset',
    'recovery_key_size',
    'hwid_digest'])
FORMAT_GBB_HEADER = '<4sHHIIIIIIIIII32s48x'


def UnpackGBBHeader(blob, offset=0):
  """Unpacks a GBB header from a blob, starting from offset."""
  header = GBBHeader(*struct.unpack_from(FORMAT_GBB_HEADER, blob, offset))
  # Check signature.
  if header.signature != GBB_SIGNATURE:
    raise ValueError('unknown GBB signature: %s' % header.signature)
  return header


def UnpackHWID(blob, base, header):
  """Unpacks HWID section."""
  offset = base + header.hwid_offset
  size = header.hwid_size
  return GBBField(
      blob[offset:offset + size].strip(b'\x00').decode('UTF-8'),
      offset,
      size)


def UnpackHWIDDigest(base, header):
  """Unpacks HWID digest section."""
  offset = base + GBB_HWID_DIGEST_OFFSET
  size = GBB_HWID_DIGEST_SIZE
  return GBBField(header.hwid_digest.hex(), offset, size)


def UnpackRootKey(blob, base, header):
  """Unpacks root key section."""
  offset = base + header.rootkey_offset
  size = header.rootkey_size
  return GBBField(blob[offset:offset + size], offset, size)


def UnpackRecoveryKey(blob, base, header):
  """Unpacks recovery key section."""
  offset = base + header.recovery_key_offset
  size = header.recovery_key_size
  return GBBField(blob[offset:offset + size], offset, size)


def UnpackGBB(blob, offset=0):
  """Unpacks a Chrome OS GBB.

  Returns a GBBContent instance containing the unpacked data.
  """
  header = UnpackGBBHeader(blob, offset)
  content = GBBContent(
      hwid=UnpackHWID(blob, offset, header),
      hwid_digest=UnpackHWIDDigest(offset, header),
      rootkey=UnpackRootKey(blob, offset, header),
      recovery_key=UnpackRecoveryKey(blob, offset, header))

  return content


def main():
  # Only load pprint if we are in console (debug / test) mode.
  import pprint
  for filename in sys.argv[1:]:
    gbb = UnpackGBB(open(filename, 'rb').read(), 0)
    print(pprint.pformat(gbb))


# When running in command line, try to report blob in the parameters.
if __name__ == '__main__':
  main()
