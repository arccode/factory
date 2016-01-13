#!/usr/bin/python
# pylint: disable=W0212
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import re

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component
from cros.factory.test.rules import privacy


# One line in vpd -l output.
VPD_LIST_PATTERN = re.compile(r'^"([^"]+)"="([^"]*)"$')

# Allowable VPD keys: alphanumeric and _ and .
VPD_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_.]+')

# Allowable VPD values: all printable ASCII characters except for
# double-quote.
VPD_VALUE_PATTERN = re.compile(r'^[ !#-~]*$')

# ChromeOS firmware VPD partition names.
VPD_READONLY_PARTITION_NAME = 'RO_VPD'
VPD_READWRITE_PARTITION_NAME = 'RW_VPD'


class Partition(component.DUTComponent):
  """A VPD partition.

  This should not be created by the caller; rather, the caller should use
  vpd.ro or vpd.rw."""

  def __init__(self, dut, name):
    """Constructor.

    Args:
      dut: Instance of cros.factory.test.dut.board.DUTBoard.
      name: The name of the partition (e.g., 'RO_VPD').
    """
    super(Partition, self).__init__(dut)
    self.name = name

  def get(self, key, default=None):
    """Returns a single item from the VPD, or default if not present.

    This invokes the 'vpd' command each time it is run; for efficiency,
    use GetAll if more than one value is desired.
    """
    result = self._dut.CallOutput(['vpd', '-i', self.name, '-g', key])
    return default if result is None else result

  def Delete(self, *keys):
    """Deletes entries from the VPD.

    Raises:
      An error if any entries cannot be deleted.  In this case some or
      all other entries may have been deleted.
    """
    if keys:
      args = ['vpd', '-i', self.name]
      for k in keys:
        args += ['-d', k]
      self._dut.CheckCall(args)

  def GetAll(self):
    """Returns the contents of the VPD as a dict."""
    ret = {}
    for line in self._dut.CallOutput(
        ['vpd', '-i', self.name, '-l']).splitlines():
      match = VPD_LIST_PATTERN.match(line)
      if not match:
        logging.error('Unexpected line in %s VPD: %r', self.name, line)
        continue
      ret[match.group(1)] = match.group(2)

    return ret

  def Update(self, items, log=True):
    """Updates items in the VPD.

    Args:
      items: Items to set.  A value of "None" deletes the item
        from the VPD (actually, it currently just sets the field to empty:
        http://crosbug.com/p/18159).
      log: Whether to log the action.  Keys in VPD_BLACKLIST_KEYS are replaced
        with a redacted value.
    """
    if log:
      logging.info('Updating %s: %s', self.name, privacy.FilterDict(items))

    data = self.GetAll()
    command = ['vpd', '-i', self.name]

    for k, v in sorted(items.items()):
      if not VPD_KEY_PATTERN.match(k):
        raise ValueError('Invalid VPD key %r (does not match pattern %s)' % (
            k, VPD_KEY_PATTERN.pattern))
      if v is None:
        v = ''  # TODO(jsalz): http://crosbug.com/p/18159
      if not VPD_VALUE_PATTERN.match(v):
        raise ValueError('Invalid VPD value %r (does not match pattern %s)' % (
            k, VPD_VALUE_PATTERN.pattern))
      # Only update if needed since reading is fast but writing is slow.
      if data.get(k) != v:
        command += ['-s', '%s=%s' % (k, v)]

    if not items:
      return

    self._dut.CheckCall(command)


class VitalProductData(component.DUTComponent):
  """System module for Vital Product Data (VPD).

  Properties:
    ro: Access to Read-Only partition.
    rw: Access to Read-Write partition.
  """

  @component.DUTProperty
  def ro(self):
    return Partition(self._dut, VPD_READONLY_PARTITION_NAME)

  @component.DUTProperty
  def rw(self):
    return Partition(self._dut, VPD_READWRITE_PARTITION_NAME)
