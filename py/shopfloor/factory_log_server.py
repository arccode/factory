# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory Log Server.

The factory log server module provides functions to start/stop an rsync server
to serve clients to upload factory log files and crash files.
"""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.utils.server_utils import (RsyncModule, StartRsyncServer,
                                             StopRsyncServer)


DEFAULT_RSYNCD_FACTORY_LOG_PORT = 8084


class FactoryLogServer(object):
  """factory log server.

  Control rsyncd for dut to upload factory log files and crash files.

  Properties:
    _rsyncd = The rsyncd process.
    _state_dir: Logs state directory (generally shopfloor_data/system_logs)
    rsyncd_port: Port on which to open rsyncd.
  """
  def __init__(self, state_dir, rsyncd_port=DEFAULT_RSYNCD_FACTORY_LOG_PORT):
    self._rsyncd = None
    self._state_dir = state_dir
    self.rsyncd_port = rsyncd_port

  def Start(self):
    """Starts factory log server."""
    factory_log_dir = os.path.join(self._state_dir, 'logs')
    if not os.path.exists(factory_log_dir):
      os.mkdir(factory_log_dir)

    self._rsyncd = StartRsyncServer(self.rsyncd_port, self._state_dir,
        [RsyncModule(module='system_logs', path=factory_log_dir,
                     read_only=False)])

  def Stop(self):
    if self._rsyncd:
      StopRsyncServer(self._rsyncd)
      self._rsyncd = None
