#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import utils


class RegistryTest(unittest.TestCase):

  def testRegistry(self):
    reg = utils.Registry()
    reg['foo'] = 'value_foo'
    reg['bar'] = 'value_foo'

    test_reg = utils.Registry()
    self.assertEqual(test_reg.foo, 'value_foo')
    self.assertNotEqual(test_reg.bar, 'value_bar')


if __name__ == '__main__':
  unittest.main()
