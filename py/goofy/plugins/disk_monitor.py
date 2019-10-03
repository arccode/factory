# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging

from cros.factory.goofy.plugins import periodic_plugin
from cros.factory.test import event_log
from cros.factory.tools import disk_space
from cros.factory.utils import debug_utils
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


class DiskMonitor(periodic_plugin.PeriodicPlugin):
  """Plugin to log disk space usage during tests."""

  def __init__(self, goofy, period_secs, stateful_usage_threshold=None,
               stateful_usage_above_threshold_action=None):
    super(DiskMonitor, self).__init__(goofy, period_secs)
    self._stateful_usage_threshold = stateful_usage_threshold
    self._stateful_usage_above_threshold_action = (
        stateful_usage_above_threshold_action)
    self._last_log_disk_space_message = None

  @debug_utils.CatchException('DiskMonitor')
  @type_utils.Overrides
  def RunTask(self):
    # Upload event if stateful partition usage is above threshold.
    # Stateful partition is mounted on /usr/local, while
    # encrypted stateful partition is mounted on /var.
    # If there are too much logs in the factory process,
    # these two partitions might get full.
    vfs_infos = disk_space.GetAllVFSInfo()
    stateful_info, encrypted_info = None, None
    for vfs_info in vfs_infos.values():
      if '/usr/local' in vfs_info.mount_points:
        stateful_info = vfs_info
      if '/var' in vfs_info.mount_points:
        encrypted_info = vfs_info

    stateful = disk_space.GetPartitionUsage(stateful_info)
    encrypted = disk_space.GetPartitionUsage(encrypted_info)

    above_threshold = (
        self._stateful_usage_threshold and
        max(stateful.bytes_used_pct,
            stateful.inodes_used_pct,
            encrypted.bytes_used_pct,
            encrypted.inodes_used_pct) > self._stateful_usage_threshold)

    if above_threshold:
      self.goofy.event_log.Log(
          'stateful_partition_usage',
          partitions={
              'stateful': {
                  'bytes_used_pct': event_log.FloatDigit(
                      stateful.bytes_used_pct, 2),
                  'inodes_used_pct': event_log.FloatDigit(
                      stateful.inodes_used_pct, 2)
              },
              'encrypted_stateful': {
                  'bytes_used_pct': event_log.FloatDigit(
                      encrypted.bytes_used_pct, 2),
                  'inodes_used_pct': event_log.FloatDigit(
                      encrypted.inodes_used_pct, 2)
              }
          })
      self.goofy.log_watcher.KickWatchThread()
      if self._stateful_usage_above_threshold_action:
        process_utils.Spawn(self._stateful_usage_above_threshold_action,
                            call=True)

    message = disk_space.FormatSpaceUsedAll(vfs_infos)
    if message != self._last_log_disk_space_message:
      if above_threshold:
        logging.warning(message)
      else:
        logging.info(message)
      self._last_log_disk_space_message = message
