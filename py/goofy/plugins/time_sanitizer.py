# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import threading

from cros.factory.goofy.plugins import plugin
from cros.factory.test import state
from cros.factory.tools import time_sanitizer
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


class TimeSanitizer(plugin.Plugin):
  """Plugin to guarantee the system time consistancy.

  See `cros.factory.tools.time_sanitizer` for more detail.
  """

  def __init__(self, goofy, sync_period_secs=None, base_time_files=None):
    """Constructor

    Args:
      sync_period_secs: seconds between each sync with factory server. If set
          to None, no periodic sync would be performed. Once successfully sync,
          no periodic task would be performed again.
      base_time_files: the based file for time reference.
    """
    super(TimeSanitizer, self).__init__(goofy)

    base_time_files = base_time_files or []

    self._sync_period_secs = sync_period_secs
    self._time_sanitizer = time_sanitizer.TimeSanitizer(
        base_time_files=base_time_files)
    self._time_synced = False
    self._thread = None
    self._lock = threading.Lock()
    self._stop_event = threading.Event()

  @type_utils.Overrides
  def OnStart(self):
    if self._sync_period_secs and not self._time_synced:
      self._stop_event.clear()
      self._thread = process_utils.StartDaemonThread(target=self._RunTarget)

  @type_utils.Overrides
  def OnStop(self):
    if self._thread:
      self._stop_event.set()
      self._thread.join()

  def _RunTarget(self):
    while True:
      # After the device reboots in reboot tests, time_sanitizer plugin comes up
      # before we check the reboot test result.  In such case, we'll change the
      # system time before the reboot test complete, and the reboot test might
      # think the reboot takes too long or the clock was moving backward.
      # So we make sure the post_shutdown key is not present before syncing the
      # time.
      post_shutdown = False
      for test in self.goofy.test_list.Walk():
        if not test.IsLeaf():
          continue

        test_state = test.GetState()
        if test_state.status == state.TestState.ACTIVE:
          key_post_shutdown = state.KEY_POST_SHUTDOWN % test.path
          if self.goofy.state_instance.DataShelfGetValue(
              key_post_shutdown, True) is not None:
            post_shutdown = True
            break

      if not post_shutdown:
        break

      if self._stop_event.wait(self._sync_period_secs):
        return

    with self._lock:
      # self._time_synced may be true if SyncTimeWithFactoryServer is called by
      # RPC function call.
      if not self._time_synced:
        self._time_sanitizer.RunOnce()

    while True:
      if net_utils.ExistPluggedEthernet():
        self.SyncTimeWithFactoryServer()

      if self._time_synced or self._stop_event.wait(self._sync_period_secs):
        return

  @plugin.RPCFunction
  def SyncTimeWithFactoryServer(self, force=False):
    """Syncs time with factory server.

    Raises:
      Error if sync time failed.
    """
    logging.info("Sync time from factory server")
    with self._lock:
      if not self._time_synced or force:
        self._time_sanitizer.SyncWithFactoryServerHtpdate()
        self._time_synced = True
