#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import sys
import unittest


class DummyCliUnittest(unittest.TestCase):
  def testImportCrosFactory(self):
    from cros.factory.cli import factory_env  # pylint: disable=unused-import

  def testSysPath(self):
    self.assertIn('factory/py_pkg', ' '.join(sys.path))


if __name__ == '__main__':
  unittest.main()
