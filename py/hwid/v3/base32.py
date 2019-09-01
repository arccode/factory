#!/usr/bin/env python2
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of base32 utilities."""

import argparse

from zlib import crc32

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common


class Base32(object):
  """A utility class for encoding binary string to base32 string, decoding
  base32 string to binary string, and calculating 10-bit base32 checksum.

  The base32 encoding used here is not identical to the standard as described
  in: http://tools.ietf.org/html/rfc4648. We encode arbitrary length of bit
  strings and pad 0 when the bit string length is not multiples of 5.
  """
  BASE32_ALPHABET = common.HEADER_ALPHABET
  BASE32_REVERSED = dict([v, k] for k, v in enumerate(BASE32_ALPHABET))
  BASE32_BIT_WIDTH = 5
  DASH_INSERTION_WIDTH = 4
  CHECKSUM_SIZE = 10
  ENCODED_CHECKSUM_SIZE = 2

  @classmethod
  def GetPaddingLength(cls, orig_length):
    """Returns the minimum padding length for a given length.

    Args:
      orig_length: The length to be calculated.

    Returns:
      A number.
    """
    return (cls.BASE32_BIT_WIDTH - orig_length) % cls.BASE32_BIT_WIDTH

  @classmethod
  def Encode(cls, binary_string):
    """Converts the given binary string to a base32-encoded string. Add paddings
    if necessary.

    Args:
      binary_string: A binary string.

    Returns:
      A base32-encoded string.
    """
    assert cls.GetPaddingLength(len(binary_string)) == 0
    result = []
    for i in xrange(0, len(binary_string), cls.BASE32_BIT_WIDTH):
      result.append(cls.BASE32_ALPHABET[
          int(binary_string[i:i + cls.BASE32_BIT_WIDTH], 2)])
    return ''.join(result)

  @classmethod
  def Decode(cls, base32_string):
    """Converts the given base32-encoded string to a binary string.

    Args:
      base32_string: A base32-encoded string.

    Returns:
      A binary string.
    """
    result = []
    for c in base32_string:
      result.append('{0:05b}'.format(cls.BASE32_REVERSED[c.upper()]))
    return ''.join(result)

  @classmethod
  def Checksum(cls, string):
    """Calculate a 10-bit checksum for the given string.

    Args:
      string: A string to generate checksum for.

    Returns:
      A string with two base32-encoded alphabets representing the
      10-bit checksum.
    """
    # Get the last 10 bits
    c = crc32(string) & (2 ** 10 - 1)
    return (cls.BASE32_ALPHABET[c >> cls.BASE32_BIT_WIDTH] +
            cls.BASE32_ALPHABET[c & (2 ** cls.BASE32_BIT_WIDTH - 1)])


if __name__ == '__main__':
  option_parser = argparse.ArgumentParser(
      description='Command-line interface for base32 encoding.')
  option_parser.add_argument('hwid', metavar='HWID', help='HWID to operate on.')
  option_parser.add_argument('--checksum', '-c', action='store_true',
                             help='Calculate checksum of the given HWID.')
  option_parser.add_argument('--verify-checksum', '-v', action='store_true',
                             help='Verify checksum of the given HWID.')
  options = option_parser.parse_args()
  stripped_hwid = options.hwid.upper().replace('-', '')
  if options.checksum:
    print Base32.Checksum(stripped_hwid)
  elif options.verify_checksum:
    expected_checksum = Base32.Checksum(stripped_hwid[:-2])
    given_checksum = stripped_hwid[-2:]
    if expected_checksum == given_checksum:
      print 'Success.'
    else:
      print 'Checksum should be: %r' % expected_checksum
  else:
    option_parser.print_help()
