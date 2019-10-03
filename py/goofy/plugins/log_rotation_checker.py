# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

from cros.factory.goofy.plugins import periodic_plugin
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


CLEANUP_LOGS_PAUSED = '/var/lib/cleanup_logs_paused'


class LogRotationChecker(periodic_plugin.PeriodicPlugin):
  """Checks log rotation file presence/absence.

  This plugin disables (or enables) log rotation by writing (or deleting)
  ``/var/lib/cleanup_logs_paused`` (see ``/usr/sbin/chromeos-cleanup-logs``).
  """

  def __init__(self, goofy, disable_rotation, period_secs=15):
    super(LogRotationChecker, self).__init__(goofy, period_secs)
    self.disable_rotation = disable_rotation

  @type_utils.Overrides
  def RunTask(self):
    try:
      if self.disable_rotation:
        open(CLEANUP_LOGS_PAUSED, 'w').close()
      else:
        file_utils.TryUnlink(CLEANUP_LOGS_PAUSED)
    except Exception:
      logging.exception(
          'Unable to %s %s',
          'touch' if self.disable_rotation else 'delete',
          CLEANUP_LOGS_PAUSED)
