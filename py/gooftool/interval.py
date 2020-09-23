# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Helper functions for manupulating intervals."""

import copy


# Interval class representing [start, end) intervals.
class Interval:
  def __init__(self, start, end):
    self.start = start
    self.end = end

  def __repr__(self):
    return 'Interval(%s, %s)' % (self.start, self.end)

  def __eq__(self, other):
    return self.start == other.start and self.end == other.end

  def __ne__(self, other):
    return self.start != other.start or self.end != other.end

  @property
  def size(self):
    return max(self.end - self.start, 0)


def MergeIntervals(intervals):
  """Merges a list of intervals.

  Args:
    intervals: An Interval list of [start, end).

  Returns:
    A minimal sorted Interval list which is the union of all intervals.
  """
  # Filter out empty intervals and sort.
  intervals = sorted(list(filter(lambda x: x.size, intervals)),
                     key=lambda x: x.start)
  if not intervals:
    return []
  # Merge intervals.
  ret = [copy.copy(intervals[0])]
  for interval in intervals[1:]:
    if interval.start <= ret[-1].end:
      ret[-1].end = max(ret[-1].end, interval.end)
    else:
      ret.append(copy.copy(interval))

  return ret


def MergeAndExcludeIntervals(include_intervals, exclude_intervals):
  """Merges a list of intervals with some excluded intervals.

  Args:
    include_intervals: An Interval list of [start, end) that we want to include
        in the union of intervals.
    exclude_intervals: An Interval list of [start, end) that we want to exclude
        from the union of intervals.

  Returns:
    A minimal sorted Interval list which is the union of all included intervals,
        with the excluded intervals removed.
  """
  include_intervals = MergeIntervals(include_intervals)
  exclude_intervals = MergeIntervals(exclude_intervals)
  exclude_size = len(exclude_intervals)
  exclude_i = 0
  ret = []
  for include in include_intervals:
    # [include.start, include.end) might be shortened in the following loop.
    while exclude_i < exclude_size and include.size:
      exclude = exclude_intervals[exclude_i]
      # When [include.start, include.end) is completely ahead of
      # [exclude.start, exclude.end), try the next excluded interval.
      if exclude.end <= include.start:
        exclude_i += 1
        continue
      # When [include.start, include.end) is completely behind
      # [exclude.start, exclude.end), it will not be cut into multiple
      # intervals again.
      if include.end <= exclude.start:
        break
      # When [include.start, include.end) intersects with
      # [exclude.start, exclude.end), cut off the interval before exclude.end
      # from [include.start, include.end), which might be the whole interval.
      if include.start < exclude.start:
        ret.append(Interval(include.start, exclude.start))
      include.start = exclude.end

    if include.size:
      ret.append(include)

  return ret


def SplitInterval(interval, max_size):
  """Split an interval into multiple intervals with a size limit.

  Args:
    interval: An Interval.
    max_size: Maximum interval size.

  Returns:
    A list of Interval where the size of each internal is not larger than
    `max_size`.
  """
  ret = []
  while interval.size:
    ret.append(
        Interval(interval.start, min(interval.start + max_size, interval.end)))
    interval = Interval(interval.start + max_size, interval.end)

  return ret
