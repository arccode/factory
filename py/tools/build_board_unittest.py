#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for build_board module."""

import os
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.tools.build_board import BuildBoard, BuildBoardException


class BuildBoardTest(unittest.TestCase):
  """Unit tests for BuildBoard class."""
  def runTest(self):
    have_private_overlays = os.path.exists(
        os.path.join(os.environ['CROS_WORKON_SRCROOT'], 'src',
                     'private-overlays'))

    spring = BuildBoard('spring')
    self.assertDictContainsSubset(
        dict(base='daisy', variant='spring', full_name='daisy_spring',
             short_name='spring', gsutil_name='daisy-spring',
             overlay_relpath=('private-overlays/'
                              'overlay-variant-daisy-spring-private'
                              if have_private_overlays else
                              'overlays/overlay-variant-daisy-spring')),
        spring.__dict__)

    # "daisy_spring" and "daisy-spring" should be the same
    for i in ['daisy_spring', 'daisy-spring']:
      self.assertEquals(spring.__dict__, BuildBoard(i).__dict__)

    self.assertDictContainsSubset(
        dict(base='link', variant=None, full_name='link',
             short_name='link', gsutil_name='link',
             overlay_relpath=('private-overlays/overlay-link-private'
                              if have_private_overlays else
                              'overlays/overlay-link')),
        BuildBoard('link').__dict__)

    self.assertRaisesRegexp(BuildBoardException, 'Unknown board',
                            BuildBoard, 'notarealboard')
    self.assertRaisesRegexp(BuildBoardException, 'Multiple board names',
                            BuildBoard, 'he')

  def testBoardArch(self):
    self.assertEquals('arm', BuildBoard('beaglebone').arch)
    self.assertEquals('arm', BuildBoard('nyan').arch)
    self.assertEquals('arm', BuildBoard('spring').arch)
    self.assertEquals('amd64', BuildBoard('rambi').arch)
    self.assertEquals('amd64', BuildBoard('link').arch)

if __name__ == '__main__':
  unittest.main()
