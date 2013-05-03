# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Update Server State.

When update server launched by shopfloor launcher, this class provides
interfaces to query updater state.
"""

# TODO(rong): Update server state interfaces will be moved back to shopfloor
# after we deprecate v1. The data shared between processes should store in
# a local db.

import glob
import os

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import constants


FACTORY_DIR = 'factory'
LATEST_MD5SUM = 'latest.md5sum'


class FactoryUpdater(object):
  """The class reports update bundle state.

  Properties:
    factory_dir: Updater bundle directory to hold previous and current contents
        or factory bundles.
    hwid_path: The path of hwid bundle.
    rsyncd_port: Rsync daemon bind port.
    state_dir: Update state directory (generally shopfloor_data/update)
  """

  def __init__(self, state_dir):
    """Constructor.

    Args:
      state_dir: Update state directory (generally shopfloor_data/update).
    """
    self.rsyncd_port = constants.DEFAULT_RSYNC_PORT
    self.state_dir = state_dir
    self.factory_dir = os.path.join(state_dir, FACTORY_DIR)
    if not os.path.exists(self.factory_dir):
      os.mkdir(self.factory_dir)

  @property
  def hwid_path(self):
    """Gets hardware ID bundle pathname.

    Returns:
      When there's exactly 1 file that matches 'hwid_*.sh', this function
      returns the pathname. Otherwise it returns None.
    """
    hwid_files = glob.glob(os.path.join(self.state_dir, 'hwid_*.sh'))
    if len(hwid_files) == 1 and os.path.isfile(hwid_files[0]):
      return hwid_files[0]
    return None

  # TODO(rong): Remove Start() and Stop() after we drop shopfloor v1
  def Start(self):
    pass

  def Stop(self):
    pass

  def GetTestMd5sum(self):
    """Returns the MD5SUM of the current update tarball."""
    md5file = os.path.join(self.state_dir, FACTORY_DIR, LATEST_MD5SUM)
    if not os.path.isfile(md5file):
      return None
    with open(md5file, 'r') as f:
      return f.readline().strip()

  def NeedsUpdate(self, device_md5sum):
    """Checks if device_md5sum needs the update.

    Args:
      device_md5sum: The md5sum of factory environment on device.

    Returns:
      True: When there's an update available and its MD5SUM is not equal to
            device's MD5SUM.
      False: Where there's no ubdate bundle or both hashsums are equal.
    """
    current_md5sum = self.GetTestMd5sum()
    return current_md5sum and (current_md5sum != device_md5sum)

