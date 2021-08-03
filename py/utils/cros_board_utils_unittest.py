#!/usr/bin/env python3
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for cros_board_utils module."""

import unittest

from cros.factory.utils.cros_board_utils import BuildBoard


class BuildBoardTest(unittest.TestCase):
  """Unit tests for BuildBoard class."""
  def runTest(self):
    mickey = BuildBoard('veyron_mickey')
    self.assertDictContainsSubset(
        dict(base='veyron', variant='mickey', full_name='veyron_mickey',
             short_name='mickey', gsutil_name='veyron-mickey'), mickey.__dict__)

    # "veyron_mickey" and "veyron-mickey" should be the same
    for i in ['veyron_mickey', 'veyron-mickey']:
      self.assertEqual(mickey.__dict__, BuildBoard(i).__dict__)

    self.assertDictContainsSubset(
        dict(base='hatch', variant=None, full_name='hatch',
             short_name='hatch', gsutil_name='hatch'),
        BuildBoard('hatch').__dict__)

  def testBoardArch(self):
    self.assertEqual('arm', BuildBoard('beaglebone').arch)
    self.assertEqual('arm', BuildBoard('kukui').arch)
    self.assertEqual('arm', BuildBoard('veyron_mickey').arch)
    self.assertEqual('amd64', BuildBoard('rambi').arch)
    self.assertEqual('amd64', BuildBoard('hatch').arch)


if __name__ == '__main__':
  unittest.main()
