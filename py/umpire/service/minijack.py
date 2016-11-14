# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Event log database Minijack service."""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.service import umpire_service


MINIJACK_NAME = 'minijack'
MINIJACK_LOG = 'minijack.log'
MINIJACK_EXEC = 'py/minijack/main.py'


class MinijackService(umpire_service.UmpireService):
  """Minijack event log database service."""

  def __init__(self):
    super(MinijackService, self).__init__()

  def CreateProcesses(self, config, env):
    """Creates a list of processes via config.

    Args:
      config: Umpire config AttrDict.
      env: UmpireEnv object.

    Returns:
      List of ServiceProcesses.
    """
    del config  # Unused.
    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig({
        'executable': os.path.join(env.server_toolkit_dir, MINIJACK_EXEC),
        'name': MINIJACK_NAME,
        'args': ['--event_log_dir',
                 os.path.join(env.umpire_data_dir, 'eventlog'),
                 '--log',
                 os.path.join(env.log_dir, MINIJACK_LOG)],
        'path': '/tmp'})
    return [proc]
