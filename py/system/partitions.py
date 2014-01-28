#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Partitions on CrOS devices."""

import factory_common  # pylint: disable=W0611


from cros.factory.utils.process_utils import Spawn


def GetRootDev():
  """Gets root block device."""
  return Spawn(['rootdev', '-d'], check_output=True).stdout_data.strip()


class Partition(object):
  """A partition on a factory-installed device."""
  name = None
  """The name of the partition."""

  index = None
  """The index of the partition."""

  def __init__(self, name, index):
    self.name = name
    self.index = index

  @property
  def path(self):
    root_dev = GetRootDev()
    if 'mmcblk' in root_dev:
      return root_dev + 'p' + str(self.index)
    else:
      return root_dev + str(self.index)


STATEFUL = Partition('STATEFUL', 1)
FACTORY_KERNEL = Partition('FACTORY_KERNEL', 2)
FACTORY_ROOTFS = Partition('FACTORY_ROOTFS', 3)
RELEASE_KERNEL = Partition('RELEASE_KERNEL', 4)
RELEASE_ROOTFS = Partition('RELEASE_ROOTFS', 5)
