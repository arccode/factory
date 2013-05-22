# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Minijack service.

This configuration runs minijack to parse event logs.
"""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher.service import ServiceBase


class MinijackService(ServiceBase):
  """Minijack configuration.

  Aargs:
    dummy_config: Launcher YAML config dictionary.
  """
  def __init__(self, dummy_config):
    # ServiceBase inherits from twisted ProcessProtocol, which is an old-
    # style python class.
    ServiceBase.__init__(self)

    svc_conf = {
        'executable': os.path.join(env.runtime_dir, 'minijack'),
        'name': 'minijacksvc',
        'args': ['--event_log_dir',
                 os.path.join(env.runtime_dir, 'shopfloor_data', 'events'),
                 '--log',
                 os.path.join(env.runtime_dir, 'log', 'minijack.log')],
        'path': env.runtime_dir,
        'logpipe': False,
        'auto_restart': True}
    self.SetConfig(svc_conf)


Service = MinijackService
