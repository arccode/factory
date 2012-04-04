#!/usr/bin/python -u
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common

import glob
import logging
import os
import traceback
import unittest

from autotest_lib.client.cros import factory


FACTORY_DIR = os.path.dirname(os.path.realpath(__file__))


class FactoryTest(unittest.TestCase):
    def test_parse_test_lists(self):
        '''Checks that all known test lists are parseable.'''
        # This test is located in a full source checkout (e.g.,
        # src/third_party/autotest/files/client/cros/factory/
        # factory_unittest.py).  Construct the paths to the reference test list
        # and any test lists in private overlays.
        test_lists = [
            os.path.join(FACTORY_DIR,
                         '../../site_tests/suite_Factory/test_list.all')
            ]

        # Go up six directories to find the top-level source directory.
        src_dir = os.path.join(FACTORY_DIR, *(['..'] * 6))
        test_lists.extend(os.path.realpath(x) for x in glob.glob(
                os.path.join(src_dir, 'private-overlays/*/'
                             'chromeos-base/autotest-private-board/'
                             'files/test_list*')))

        failures = []
        for test_list in test_lists:
            logging.info('Parsing test list %s', test_list)
            try:
                factory.read_test_list(test_list)
            except:
                failures.append(test_list)
                traceback.print_exc()

        if failures:
            self.fail('Errors in test lists: %r' % failures)

        self.assertEqual([], failures)


if __name__ == "__main__":
    factory.init_logging('factory_unittest')
    unittest.main()
