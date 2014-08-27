#!/usr/bin/python

# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for get_version."""


import gzip
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.tools import get_version
from cros.factory.utils import file_utils


class GetVersionTest(unittest.TestCase):
  """Unit tests for methods in get_version module."""

  def testHWIDVersion(self):
    # The checksum is actually for 'X\nX'.
    CHECKSUM_XX = 'da9449cebe8f96641c9e6fbdca1783cc5ff3a05a'
    CONTENT_XX = 'X\nchecksum: %s\nX' % CHECKSUM_XX

    # checksum at the last line.
    CHECKSUM_X = 'b5fec669aca110f1505934b1b08ce2351072d16b'
    CONTENT_X = 'X\nchecksum: %s' % CHECKSUM_X

    CONTENT_NO_CHECKSUM = 'X\nno_checksum: %s' % CHECKSUM_X

    with file_utils.UnopenedTemporaryFile() as hwid_path:
      file_utils.WriteFile(hwid_path, CONTENT_XX)
      self.assertEquals(CHECKSUM_XX,
                        get_version.GetHWIDVersion(hwid_path))

    with file_utils.UnopenedTemporaryFile() as hwid_path:
      file_utils.WriteFile(hwid_path, CONTENT_X)
      self.assertEquals(CHECKSUM_X,
                        get_version.GetHWIDVersion(hwid_path))

    with file_utils.UnopenedTemporaryFile() as hwid_path:
      file_utils.WriteFile(hwid_path, CONTENT_NO_CHECKSUM)
      self.assertIsNone(get_version.GetHWIDVersion(hwid_path))


  def testHWIDVersionGzipped(self):
    # The checksum is actually for 'X\nX'.
    CHECKSUM = 'da9449cebe8f96641c9e6fbdca1783cc5ff3a05a'
    CONTENT = 'X\nchecksum: %s\nX' % CHECKSUM

    # Gzipped
    with file_utils.UnopenedTemporaryFile(suffix='.gz') as gzipped_hwid_path:
      f = gzip.open(gzipped_hwid_path, 'wb')
      f.writelines(CONTENT)
      f.close()

      self.assertEquals(CHECKSUM, get_version.GetHWIDVersion(gzipped_hwid_path))


if __name__ == '__main__':
  unittest.main()
