#!/usr/bin/python -u
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for factory.py."""


import factory_common  # pylint: disable=W0611

import os
import unittest

from cros.factory.test import factory


SRCROOT = os.environ.get('CROS_WORKON_SRCROOT')


class FactoryModuleTest(unittest.TestCase):
  """Unittest for Factory module."""

  # TODO(stimim): test FactoryTestList

  def test_py_test_name_to_id(self):
    for name, test_id in (('a', 'A'),
                          ('_', '_'),
                          ('ab', 'Ab'),
                          ('a_b', 'AB'),
                          ('foo_bar', 'FooBar')):
      self.assertEqual(test_id, factory.FactoryTest.pytest_name_to_id(name))

if __name__ == '__main__':
  factory.init_logging('factory_unittest')
  unittest.main()
