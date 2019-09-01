#!/usr/bin/env python2
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for get_version."""


import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.tools import get_version


SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))


class GetHWIDVersionTest(unittest.TestCase):
  """Unit tests for methods in get_version module."""

  checksum = 'e684ff75984ade16b513069ce4ec6933fcb21838'

  def setUp(self):
    os.chdir(os.path.join(SCRIPT_DIR, 'testdata'))

  def testRaw(self):
    self.assertEqual(self.checksum, get_version.GetHWIDVersion('OAK'))

  def testBundle(self):
    self.assertEqual(self.checksum,
                     get_version.GetHWIDVersion('hwid_v3_bundle_OAK.sh'))

  def testGzippedBundle(self):
    self.assertEqual(self.checksum, get_version.GetHWIDVersion('hwid.gz'))


if __name__ == '__main__':
  unittest.main()
