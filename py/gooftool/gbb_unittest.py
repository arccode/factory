#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

from cros.factory.gooftool import gbb

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')
_TEST_GBB_PATH = os.path.join(_TEST_DATA_PATH, 'test_gbb')


class GBBTest(unittest.TestCase):
  """Unittest for gbb."""

  def testGetData(self):
    with open(_TEST_GBB_PATH, 'rb') as f:
      gbb_content = gbb.UnpackGBB(f.read())
    # HWID string
    self.assertEqual(gbb_content.hwid.value, 'TEST HWID')
    # SHA256 of HWID
    self.assertEqual(
        gbb_content.hwid_digest.value,
        '846045dcb414d8ae984aa9c78c024b398b340d63afc85870606a3236a5459cfe')
    # rootkey
    self.assertEqual(gbb_content.rootkey.value, b'\xa5' * 4096)
    # recovery key
    self.assertEqual(gbb_content.recovery_key.value, b'\x5a' * 4096)


if __name__ == '__main__':
  unittest.main()
