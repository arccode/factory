#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from cros.factory.gooftool import interval


class IntervalTest(unittest.TestCase):
  """Unittest for interval utility."""

  def MakeIntervals(self, intervals):
    return list(map(lambda x: interval.Interval(x[0], x[1]), intervals))

  def testMergeIntervals_EmptyIntervals(self):
    intervals = self.MakeIntervals([(1, 1), (3, 2)])
    result = self.MakeIntervals([])
    self.assertEqual(interval.MergeIntervals(intervals), result)

  def testMergeIntervals_NoIntersections(self):
    intervals = self.MakeIntervals([(4, 6), (1, 3), (7, 8), (8, 9)])
    result = self.MakeIntervals([(1, 3), (4, 6), (7, 9)])
    self.assertEqual(interval.MergeIntervals(intervals), result)

  def testMergeIntervals_Intersections(self):
    intervals = self.MakeIntervals([(1, 3), (2, 5), (4, 6), (7, 10), (8, 9)])
    result = self.MakeIntervals([(1, 6), (7, 10)])
    self.assertEqual(interval.MergeIntervals(intervals), result)

  def testMergeAndExcludeIntervals_NoExcluded(self):
    include_intervals = self.MakeIntervals([(4, 5), (5, 6)])
    exclude_intervals = self.MakeIntervals([(1, 4), (7, 8)])
    result = self.MakeIntervals([(4, 6)])
    self.assertEqual(
        interval.MergeAndExcludeIntervals(include_intervals, exclude_intervals),
        result)

  def testMergeAndExcludeIntervals_AllExcluded(self):
    include_intervals = self.MakeIntervals([(1, 3), (4, 6), (5, 7)])
    exclude_intervals = self.MakeIntervals([(1, 5), (5, 7)])
    result = []
    self.assertEqual(
        interval.MergeAndExcludeIntervals(include_intervals, exclude_intervals),
        result)

  def testMergeAndExcludeIntervals_PartialExcluded(self):
    include_intervals = self.MakeIntervals([(1, 9), (10, 12)])
    exclude_intervals = self.MakeIntervals([(2, 3), (4, 5), (6, 7), (8, 11)])
    result = self.MakeIntervals([(1, 2), (3, 4), (5, 6), (7, 8), (11, 12)])
    self.assertEqual(
        interval.MergeAndExcludeIntervals(include_intervals, exclude_intervals),
        result)

  def testSplitInterval(self):
    i = interval.Interval(1, 6)
    max_size = 2
    result = self.MakeIntervals([(1, 3), (3, 5), (5, 6)])
    self.assertEqual(interval.SplitInterval(i, max_size), result)


if __name__ == '__main__':
  unittest.main()
