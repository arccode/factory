#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of base32 utilities."""

from zlib import crc32


class Base32(object):
  """A utility class for encoding binary string to base32 string, decoding
  base32 string to binary string, and calculating 10-bit base32 checksum.

  The base32 encoding used here is not identical to the standard as described
  in: http://tools.ietf.org/html/rfc4648. We encode arbitrary length of bit
  strings and pad 0 when the bit string length is not multiples of 5.
  """
  BASE32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  BASE32_REVERSED = dict([v, k] for k, v in enumerate(BASE32_ALPHABET))
  BASE32_BIT_WIDTH = 5

  @classmethod
  def Encode(cls, binary_string):
    """Converts the given binary string to a base32-encoded string. Add paddings
    if necessary.

    Args:
      binary_string: A binary string.

    Returns:
      A base32-encoded string.
    """
    # Add paddings if the string length is not multiples of 5.
    if len(binary_string) % cls.BASE32_BIT_WIDTH:
      binary_string += '0' * (cls.BASE32_BIT_WIDTH -
                              (len(binary_string) % cls.BASE32_BIT_WIDTH))
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
