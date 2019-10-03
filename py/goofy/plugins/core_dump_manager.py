# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


from cros.factory.goofy.plugins import periodic_plugin
from cros.factory.test.utils import core_dump_manager
from cros.factory.utils import debug_utils
from cros.factory.utils import type_utils


class CoreDumpManager(periodic_plugin.PeriodicPlugin):

  def __init__(self, goofy, period_secs, core_dump_watchlist=None):
    """Constructor

    Args:
      period_secs: The period between each check of core dump files.
      core_dump_watchlist: The list of core dump pattern to watch for.
    """
    super(CoreDumpManager, self).__init__(goofy, period_secs)
    core_dump_watchlist = core_dump_watchlist or []
    self._core_dump_manager = core_dump_manager.CoreDumpManager(
        core_dump_watchlist)

  @debug_utils.CatchException('CoreDumpManager')
  @type_utils.Overrides
  def RunTask(self):
    """Checks if there is any core dumped file.

    Removes unwanted core dump files immediately.
    Syncs those files matching watch list to server with a delay between
    each sync. After the files have been synced to server, deletes the files.
    """
    core_dump_files = self._core_dump_manager.ScanFiles()
    if core_dump_files:
      # Sends event to server
      self.goofy.event_log.Log('core_dumped', files=core_dump_files)
      self.goofy.log_watcher.KickWatchThread()

      # Syncs files to server
      system_log_manager = self.goofy.plugin_controller.GetPluginInstance(
          'system_log_manager')
      if system_log_manager:
        system_log_manager.KickToSync(
            core_dump_files, self._core_dump_manager.ClearFiles)
