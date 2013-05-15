#!/usr/bin/python
# pylint: disable=W0212
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import re


import factory_common  # pylint: disable=W0611
from cros.factory import privacy
from cros.factory.utils.process_utils import Spawn


# One line in vpd -l output.
VPD_LIST_PATTERN = re.compile(r'^"([^"]+)"="([^"]+)"$')

# Allowable VPD keys: alphanumeric and _ and .
VPD_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_.]+')

# Allowable VPD values: all printable ASCII characters except for
# double-quote.
VPD_VALUE_PATTERN = re.compile(r'^[ !#-~]*$')


class Partition(object):
  """A VPD partition.

  This should not be created by the caller; rather, the caller should use
  vpd.ro or vpd.rw."""
  def __init__(self, name):
    """Constructor.

    Args:
      name: The name of the partition (e.g., 'RO_VPD').
    """
    self.name = name

  def get(self, key, default=None):
    """Returns a single item from the VPD, or default if not present.

    This invokes the 'vpd' command each time it is run; for efficiency,
    use GetAll if more than one value is desired.
    """
    return self.GetAll().get(key, default)

  def Delete(self, *keys):
    """Deletes entries from the VPD.

    Raises:
      An error if any entries cannot be deleted.  In this case some or
      all other entries may have been deleted.
    """
    for k in keys:
      Spawn(['vpd', '-i', self.name, '-d', k], check_call=True,
            log_stderr_on_error=True)

  def GetAll(self):
    """Returns the contents of the VPD as a dict."""
    ret = {}
    for line in Spawn(
        ['vpd', '-i', self.name, '-l'], check_output=True).stdout_lines(
            strip=True):
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
      command += ['-s', '%s=%s' % (k, v)]

    if not items:
      return

    Spawn(command, check_call=True)


ro = Partition('RO_VPD')
rw = Partition('RW_VPD')
