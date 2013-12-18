# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A collective of system-related functions."""

import logging
import re

import factory_common   # pylint: disable=W0611
from cros.factory.utils import file_utils


def GetInterrupts():
  """Gets the list of interrupt names and its count.

  Returns:
    A dict of interrupt names to their interrupt counts.  The interrupt names
    are all strings even if some of the names are numbers, e.g. the name for
    interrupt 88 is "88" instead of 88.
  """
  interrupt_count = {}

  lines = file_utils.ReadLines('/proc/interrupts')
  if not lines:
    raise OSError('Unable to read /proc/interrupts')

  # First line indicates CPUs in system
  num_cpus = len(lines.pop(0).split())

  for line_num, line in enumerate(lines, start=1):
    fields = line.split()
    if len(fields) < num_cpus + 1:
      logging.error('Parse error at line %d: %s', line_num, line)
      continue
    interrupt = fields[0].strip().split(':')[0]
    count = sum(map(int, fields[1:1 + num_cpus]))
    interrupt_count[interrupt] = count
    logging.debug('interrupt[%s] = %d', interrupt, count)

  return interrupt_count


class PartitionInfo(object):
  """A class that holds the info of a partition."""
  def __init__(self, major, minor, blocks, name):
    self.major = major
    self.minor = minor
    self.blocks = blocks
    self.name = name

  def __str__(self):
    return ('%5s %5s %10s %-20s' %
            (self.major, self.minor, self.blocks, self.name))


def GetPartitions():
  """Gets a list of partition info.

  Example content of /proc/partitions:

    major minor  #blocks  name

       8        0  976762584 sda
       8        1     248832 sda1
       8        2          1 sda2
       8        5  976510976 sda5
       8       16  175825944 sdb
       8       17  175825943 sdb1
     252        0   39059456 dm-0
     252        1  870367232 dm-1
     252        2   67031040 dm-2

  Returns:
    A list of PartitionInfo objects parsed from /proc/partitions.
  """
  line_format = re.compile(
      r'^\s*(\d+)'  # major
      r'\s*(\d+)'   # minor
      r'\s*(\d+)'   # number of blocks
      r'\s*(\w+)$'  # name
  )
  results = []
  lines = file_utils.ReadLines('/proc/partitions')
  for line in lines:
    match_obj = line_format.match(line)
    if match_obj:
      results.append(PartitionInfo(*match_obj.groups()))
  return results
