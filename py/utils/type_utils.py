# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for data types."""

import Queue


class Enum(frozenset):
  """An enumeration type.

  Usage:
    To create a enum object:
      dummy_enum = type_utils.Enum(['A', 'B', 'C'])

    To access a enum object, use:
      dummy_enum.A
      dummy_enum.B
  """
  def __getattr__(self, name):
    if name in self:
      return name
    raise AttributeError


def DrainQueue(queue):
  """Returns as many elements as can be obtained from a queue without blocking.

  (This may be no elements at all.)
  """
  ret = []
  while True:
    try:
      ret.append(queue.get_nowait())
    except Queue.Empty:
      break
  return ret


def FlattenList(lst):
  """Flattens a list, recursively including all items in contained arrays.

  For example:

    FlattenList([1,2,[3,4,[]],5,6]) == [1,2,3,4,5,6]
  """
  return sum((FlattenList(x) if isinstance(x, list) else [x] for x in lst),
             [])
