#!/usr/bin/python -u
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common # pylint: disable=W0611

import glob
import logging
import os
import traceback
import unittest

from cros.factory.test import factory
from cros.factory.goofy import test_steps


SRCROOT = os.environ.get('CROS_WORKON_SRCROOT')


class FactoryTest(unittest.TestCase):
  def test_parse_test_lists(self):
    '''Checks that all known test lists are parseable.'''
    # This test is located in a full source checkout (e.g.,
    # src/third_party/autotest/files/client/cros/factory/
    # factory_unittest.py). Construct the paths to the reference test list
    # and any test lists in private overlays.
    test_lists = [os.path.join(factory.FACTORY_PATH, 'test_lists',
                               'test_list.all')]

    test_lists.extend(os.path.realpath(x) for x in glob.glob(
        os.path.join(SRCROOT, 'src/private-overlays/*/'
               'chromeos-base/autotest-private-board/'
               'files/test_list*')))

    failures = []
    for test_list in test_lists:
      logging.info('Parsing test list %s', test_list)
      try:
        factory.read_test_list(test_list, test_classes=test_steps.__dict__)
      except:  # pylint: disable=W0702
        failures.append(test_list)
        traceback.print_exc()

    if failures:
      self.fail('Errors in test lists: %r' % failures)

    self.assertEqual([], failures)

  def test_options(self):
    base_test_list = 'TEST_LIST = []\n'

    # This is a valid option.
    factory.read_test_list(
      text=base_test_list +
      'options.auto_run_on_start = True')

    try:
      factory.read_test_list(
        text=base_test_list + 'options.auto_run_on_start = 3')
      self.fail('Expected exception')
    except factory.TestListError as e:
      self.assertTrue(
        'Option auto_run_on_start has unexpected type' in e[0], e)

    try:
      factory.read_test_list(
        text=base_test_list + 'options.fly_me_to_the_moon = 3')
      self.fail('Expected exception')
    except factory.TestListError as e:
      # Sorry, swinging among the stars is currently unsupported.
      self.assertTrue(
        'Unknown option fly_me_to_the_moon' in e[0], e)

if __name__ == "__main__":
  factory.init_logging('factory_unittest')
  unittest.main()
