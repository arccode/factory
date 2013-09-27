#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for touch_utils module."""


import os
import sys
import unittest

import factory_common                             # pylint: disable=W0611
import touch_utils


PY_UTILS_DIR = os.path.dirname(sys.modules[__name__].__file__)
TOUCH_DATA_DIR = os.path.join(PY_UTILS_DIR, 'testdata/touch_data')


def GetPath(filename):
  return os.path.join(TOUCH_DATA_DIR, filename)


class MtbStateMachineTest(unittest.TestCase):
  """Unit tests for MtbStateMachine class."""

  def testMtbOneFinger(self):
    filename = 'one_finger_swipe.dat'

    # Test the number of packets in the file
    mtb_packets = touch_utils.GetMtbPacketsFromFile(GetPath(filename))
    self.assertEquals(len(mtb_packets.packets), 5)

    # Get the finger_paths dict and test the number of finger contacts
    finger_paths = mtb_packets.GetOrderedFingerPaths()
    self.assertEquals(len(finger_paths), 1)

    # Test the TRACKING ID (33), and the slot number (0)
    self.assertEquals(finger_paths.keys()[0], 33)
    self.assertEquals(finger_paths.values()[0].slot, 0)

    # Test the number of points in the 0th finger contact (finger = 0)
    points = mtb_packets.GetOrderedFingerPath(0, 'point')
    self.assertEquals(len(points), 5)

    # Test the points in the 0th finger contact
    expected_xy_pairs = [(861, 259),
                         (827, 260),
                         (782, 290),
                         (713, 347),
                         (713, 347)]
    for i, point in enumerate(points):
      self.assertEquals((point.x, point.y), expected_xy_pairs[i])

    # Test the number of syn_report time events in the 0th finger contact.
    syn_times = mtb_packets.GetOrderedFingerPath(0, 'syn_time')
    self.assertEquals(len(syn_times), 5)

    # Test the syn_report time events in the 0th finger contact.
    expected_syn_times = [160278.881053, 160278.889880, 160278.898388,
                          160278.907438, 160278.915150]
    for i, syn_time in enumerate(syn_times):
      self.assertEquals(syn_time, expected_syn_times[i])

    # Test the pressures in the 0th finger contact
    pressures = mtb_packets.GetOrderedFingerPath(0, 'pressure')
    expected_pressures = [41, 36, 35, 23, 23]
    for i, pressure in enumerate(pressures):
      self.assertEquals(pressure, expected_pressures[i])

  def testMtbTwoFinger(self):
    filename = 'two_finger_tracking.bottom_left_to_top_right.slow.dat'

    # Test the number of packets in the file
    mtb_packets = touch_utils.GetMtbPacketsFromFile(GetPath(filename))
    self.assertEquals(len(mtb_packets.packets), 58)

    # Test the number of finger contacts
    finger_paths = mtb_packets.GetOrderedFingerPaths()
    self.assertEquals(len(finger_paths), 2)

    # Test the number of packets in the 0th finger contact (finger = 0)
    finger_path = mtb_packets.GetOrderedFingerPath(0, 'point')
    self.assertEquals(len(finger_path), 58)

    # Test the number of packets in the 1st finger contact (finger = 1)
    finger_path = mtb_packets.GetOrderedFingerPath(1, 'point')
    self.assertEquals(len(finger_path), 56)


if __name__ == '__main__':
  unittest.main()
