# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import threading

from cros.factory.goofy.plugins import plugin
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
    self._time_sanitizer.RunOnce()
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
      if net_utils.ExistPluggedEthernet():
        self._time_sanitizer.SaveTime()
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
