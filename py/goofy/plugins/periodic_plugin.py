# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import threading

from cros.factory.goofy.plugins import plugin
from cros.factory.utils import debug_utils
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


class PeriodicPlugin(plugin.Plugin):
  """Plugins that runs specific task periodically.

  A common implementation of `cros.factory.goofy.plugins` that run a specific
  task periodically.

  Subclass needs to implement `RunTask()`, which will be executed periodically
  in a daemon thread.
  """

  def __init__(self, goofy, period_secs,
               used_resources=None, catch_exception=True):
    """Contructor of PeriodicPlugin.

    Args:
      period_secs: seconds between each run.
      catch_exception: catch exceptions from `RunTask()` function or not. If
          set to False, exception in `RunTask()` would cause the running thread
          to crash, and the following periodic task would be stopped.
    """
    super(PeriodicPlugin, self).__init__(goofy, used_resources)
    self._thread = None
    self._stop_event = threading.Event()
    self._period_secs = period_secs
    self._run_times = 0
    self._run_task = self._RunTaskWithCatch if catch_exception else self.RunTask

  @type_utils.Overrides
  def OnStart(self):
    self._stop_event.clear()
    self._run_times = 0
    self._thread = process_utils.StartDaemonThread(target=self._RunTarget)

  def _RunTarget(self):
    """Periodically runs `RunTask()`."""
    while not self._stop_event.wait(
        self._period_secs if self._run_times else 0):
      self._run_task()
      self._run_times += 1

  def RunTask(self):
    """Called periodically

    Subclass need to implement this function.
    """
    raise NotImplementedError

  @debug_utils.CatchException('PeriodicPlugin')
  def _RunTaskWithCatch(self):
    """Wrapper of `RunTask()` that catches any exception."""
    self.RunTask()

  @type_utils.Overrides
  def OnStop(self):
    self._stop_event.set()
