# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import factory_common  # pylint: disable=unused-import
from cros.factory.utils import debug_utils
from cros.factory.utils import type_utils


# Type of resources that can be used by plugins.
RESOURCE = type_utils.Enum(['CPU', 'POWER'])


class Plugin(object):
  """Based class for Goofy plugin.

  Plugins are separated components that can be loaded by goofy for different
  scenarios. The subclass can implement the following lifetime functions for
  different purposes.

  `OnStart`: Called when Goofy starts to run the plugin.
  `OnStop`: Called when Goofy is requested to stop or pause the plugin.
  `OnDestroy`: Called when Goofy is going to shutdown.
  """

  STATE = type_utils.Enum(['RUNNING', 'STOPPED', 'DESTROYED'])
  """State of the plugin.

  Goofy plugins are started by Goofy during initialization, and are stopped when
  Goofy is about to shutdown. During the tests, some plugins may also be paused
  temporarily.

  Therefore, a plugin can be in one of the three states:
  - RUNNING: `OnStart` is called and the plugin is running.
  - STOPPED: `OnStop` is called and the plugin is stopped / paused.
  - DESTORYED: `OnDestory` is called and Goofy is going to shutdown.
  """

  def __init__(self, goofy, used_resources=None):
    """Constructor

    Args:
      goofy: the goofy instance.
      used_resources: A list of resources accessed by this plugin. Should be
          applied by subclass.
    """
    self.goofy = goofy
    self.used_resources = used_resources or []
    self._state = self.STATE.STOPPED

  def OnStart(self):
    """Called when Goofy starts or resumes the plugin."""
    pass

  def OnStop(self):
    """Called when Goofy stops or pauses the plugin."""
    pass

  def OnDestroy(self):
    """Called when Goofy is going to be shutdown."""
    pass

  @debug_utils.CatchException('Plugin')
  def Start(self):
    """Starts running the plugin."""
    if self._state == self.STATE.STOPPED:
      self._state = self.STATE.RUNNING
      self.OnStart()

  @debug_utils.CatchException('Plugin')
  def Stop(self):
    """Stops running the plugin."""
    if self._state == self.STATE.RUNNING:
      self._state = self.STATE.STOPPED
      self.OnStop()

  @debug_utils.CatchException('Plugin')
  def Destroy(self):
    """Destroy the plugin."""
    if self._state == self.STATE.DESTROYED:
      return
    self.Stop()
    self._state = self.STATE.DESTROYED
    self.OnDestroy()
