# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Updater for HWID configs."""

import factory_common  # pylint: disable=unused-import
from cros.chromeoshwid import update_checksum


class HwidUpdater(object):
  """Updates HWID configs."""

  def UpdateChecksum(self, hwid_config_contents):
    """Updates the checksum in the config and returns the updated config."""
    encoded = hwid_config_contents.encode('utf8')
    updated = update_checksum.ReplaceChecksum(encoded)
    return updated.decode('utf8')
