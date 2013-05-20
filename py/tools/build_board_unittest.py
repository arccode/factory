#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.tools.build_board import BuildBoard, BuildBoardException


class BuildBoardTest(unittest.TestCase):
  def runTest(self):
    spring = BuildBoard('spring')
    self.assertDictContainsSubset(
        dict(base='daisy', variant='spring', full_name='daisy_spring',
             short_name='spring',
             overlay_relpath=('private-overlays/'
                              'overlay-variant-daisy-spring-private')),
        spring.__dict__)

    # "daisy_spring" and "daisy-spring" should be the same
    for i in ['daisy_spring', 'daisy-spring']:
      self.assertEquals(spring.__dict__, BuildBoard(i).__dict__)

    self.assertDictContainsSubset(
        dict(base='link', variant=None, full_name='link',
             short_name='link',
             overlay_relpath='private-overlays/overlay-link-private'),
        BuildBoard('link').__dict__)
    self.assertDictContainsSubset(
        dict(base='tegra2', variant='seaboard', full_name='tegra2_seaboard',
             short_name='seaboard',
             overlay_relpath='overlays/overlay-variant-tegra2-seaboard'),
        BuildBoard('seaboard').__dict__)

    self.assertRaisesRegexp(BuildBoardException, 'Unknown board',
                            BuildBoard, 'notarealboard')
    self.assertRaisesRegexp(BuildBoardException, 'Multiple board names',
                            BuildBoard, 'he')


if __name__ == '__main__':
  unittest.main()
