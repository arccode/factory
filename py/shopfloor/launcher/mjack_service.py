# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Minijack service.

This configuration runs minijack to parse event logs.
"""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor import EVENTS_DIR
from cros.factory.shopfloor.launcher import constants
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher.service import ServiceBase
from cros.factory.test.utils import TryMakeDirs


MINIJACK_LOG = 'minijack.log'


class MinijackService(ServiceBase):
  """Minijack configuration.

  Aargs:
    dummy_config: Launcher YAML config dictionary.
  """
  def __init__(self, dummy_config):
    # ServiceBase inherits from twisted ProcessProtocol, which is an old-
    # style python class.
    ServiceBase.__init__(self)

    minijack_executable = os.path.join(env.runtime_dir, 'minijack')
    shopfloor_data = os.path.join(env.runtime_dir, constants.SHOPFLOOR_DATA)
    events_dir = os.path.join(shopfloor_data, EVENTS_DIR)
    svc_conf = {
        'executable': minijack_executable,
        'name': 'minijacksvc',
        'args': ['--event_log_dir', events_dir,
                 '--log', os.path.join(env.runtime_dir, constants.LOGS_DIR,
                                       MINIJACK_LOG)],
        'path': env.runtime_dir,
        'logpipe': False,
        'auto_restart': True}
    self.SetConfig(svc_conf)

    # Prepares minijack symlink and folder.
    if not os.path.isfile(minijack_executable):
      os.symlink(os.path.join(env.runtime_dir, constants.FACTORY_SOFTWARE),
                 minijack_executable)
    # Minijack reads from [install dir]/shopfloor_data/events
    shopfloor_data = os.path.join(env.runtime_dir, constants.SHOPFLOOR_DATA)
    TryMakeDirs(shopfloor_data)
    TryMakeDirs(events_dir)


Service = MinijackService
