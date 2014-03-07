#!/usr/bin/env python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101


import unittest

import factory_common  # pylint: disable=W0611
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
