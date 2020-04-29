#!/usr/bin/env python3
#
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from cros.factory.hwid.v3 import filesystem_adapter


class FileSystemAdapterTest(unittest.TestCase):
  """Tests the FileSystemAdapter interface."""

  def testAbstractClass(self):
    """Tests if FileSystemAdapter cannot be instantiated since it's an abstract
    class."""
    self.assertRaises(TypeError, filesystem_adapter.FileSystemAdapter)


if __name__ == '__main__':
  unittest.main()
