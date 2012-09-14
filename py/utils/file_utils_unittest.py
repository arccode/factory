#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import os
import re
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import file_utils


class UnopenedTemporaryFileTest(unittest.TestCase):
  def testUnopenedTemporaryFile(self):
    with file_utils.UnopenedTemporaryFile(
        prefix='prefix', suffix='suffix') as x:
      self.assertTrue(os.path.exists(x))
      self.assertEquals(0, os.path.getsize(x))
      assert re.match('prefix.+suffix', os.path.basename(x))
      self.assertEquals(tempfile.gettempdir(), os.path.dirname(x))
    self.assertFalse(os.path.exists(x))

if __name__ == '__main__':
  unittest.main()
