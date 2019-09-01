#!/usr/bin/env python2
# Copyright 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
    Chrome OS bitmap block parser.

    This module helps parsing firmware bitmap blocks so that we can
    retrieve the version and other information from a blob.

    See help(unpack_bmpblock) for more information.

    ref: src/platform/vboot_reference/firmware/include/bmpblk_header.h
"""

import struct
import sys

# Constant Definition
BMPBLOCK_SIGNATURE = '$BMP'
BMPBLOCK_SIGNATURE_SIZE = 4
MAX_IMAGE_IN_LAYOUT = 8

# Blob Structure

# typedef struct BmpBlockHeader {
#   uint8_t signature[BMPBLOCK_SIGNATURE_SIZE];
#   uint16_t major_version;
#   uint16_t minor_version;
#   uint32_t number_of_localizations;
#   uint32_t number_of_screenlayouts;
#   uint32_t number_of_imageinfos;
#   uint32_t locale_string_offset;
#   uint32_t reserved[2];
# };
FORMAT_BMPBLOCK_HEADER = '<4shhIIII2I'
NAMES_BMPBLOCK_HEADER = ('signature',
                         'major_version',
                         'minor_version',
                         'number_of_localizations',
                         'number_of_screenlayouts',
                         'number_of_imageinfos',
                         'locale_string_offset',
                         'reserved')

# typedef struct ScreenLayout {
#   struct {
#     uint32_t x;
#     uint32_t y;
#     uint32_t image_info_offset;
#   } images[MAX_IMAGE_IN_LAYOUT];
# };
FORMAT_SCREEN_LAYOUT_IMAGE = '<III'
NAMES_SCREEN_LAYOUT_IMAGE = ('x', 'y', 'image_info_offset')

# typedef struct ImageInfo {
#   uint32_t tag;
#   uint32_t width;
#   uint32_t height;
#   uint32_t format;
#   uint32_t compression;
#   uint32_t original_size;
#   uint32_t compressed_size;
#   uint32_t reserved;
# };
FORMAT_IMAGE_INFO = '<IIIIIIII'
NAMES_IMAGE_INFO = (
    'tag',
    'width',
    'height',
    'format',
    'compression',
    'original_size',
    'compressed_size',
    'reserved')


def unpack_BmpBlockHeader(blob, offset=0):
  """ Unpacks a BmpBlockHeader from a blob, starting from offset. """
  fields = struct.unpack_from(FORMAT_BMPBLOCK_HEADER, blob, offset)
  header = dict(zip(NAMES_BMPBLOCK_HEADER, fields))
  # check signature
  if header['signature'] != BMPBLOCK_SIGNATURE:
    raise ValueError('unknown bmpblock signature: %s' % header['signature'])
  return header


def unpack_ImageInfo(blob, offset=0):
  """ Unpacks a ImageInfo from a blob, starting from offset. """
  fields = struct.unpack_from(FORMAT_IMAGE_INFO, blob, offset)
  info = dict(zip(NAMES_IMAGE_INFO, fields))
  return info


def unpack_ScreenLayout(blob, base=0, offset=0):
  """ Unpacks a ScreenLayout from a blob, starting from offset. """
  layout = []
  for _ in range(MAX_IMAGE_IN_LAYOUT):
    fields = struct.unpack_from(FORMAT_SCREEN_LAYOUT_IMAGE, blob, offset)
    offset += struct.calcsize(FORMAT_SCREEN_LAYOUT_IMAGE)
    image = dict(zip(NAMES_SCREEN_LAYOUT_IMAGE, fields))
    info_offset = image['image_info_offset']
    if info_offset > 0:
      image.update(unpack_ImageInfo(blob, base + info_offset))
      layout.append(image)
  return layout


def unpack_LocaleString(blob, base=0, offset=0):
  """ Unpacks a double NUL-terminated locale string, starting from offset. """
  end = blob.find('\x00\x00', base + offset)
  if end < 0:
    return []
  locale_string = blob[base + offset:end]
  return locale_string.split('\x00')


def unpack_bmpblock(blob, offset=0):
  """Unpacks a Chrome OS Bitmap Block.

  Returns a dictionary of unpacked data
  """
  data = unpack_BmpBlockHeader(blob, offset)
  layout_offset = offset + struct.calcsize(FORMAT_BMPBLOCK_HEADER)
  localizations = []
  for _ in range(data['number_of_localizations']):
    layouts = []
    for _ in range(data['number_of_screenlayouts']):
      layouts.append(unpack_ScreenLayout(blob, offset, layout_offset))
      layout_offset += (struct.calcsize(FORMAT_SCREEN_LAYOUT_IMAGE) *
                        MAX_IMAGE_IN_LAYOUT)
    localizations.append(layouts)
  data['localizations'] = localizations
  # locale string is optional.
  locale_string_offset = data['locale_string_offset']
  data['locales'] = (unpack_LocaleString(blob, offset, locale_string_offset)
                     if locale_string_offset else [])
  return data


# -----------------------------------------------------------------------------


def main():
  # Only load pprint if we are in console (debug / test) mode
  import pprint
  for filename in sys.argv[1:]:
    bmpblk = unpack_bmpblock(open(filename, 'rb').read(), 0)
    print pprint.pformat(bmpblk)


# When running in command line, try to report blob in the parameters
if __name__ == '__main__':
  main()
