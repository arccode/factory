# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Shopfloor Factory Update Service.

This service configures launcher to start v1 factory update server as an
external process.
"""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import constants
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher.service import ServiceBase


class FactoryUpdateService(ServiceBase):
  """Configurates external factory_update_server.

  Args:
    yaml_config: Launcher YAML config dictionary.
  """
  def __init__(self, yaml_config):  # pylint: disable=W0613
    # ServiceBase is an old-style python class. Initialize it the old-way.
    ServiceBase.__init__(self)

    update_server = os.path.abspath(
        os.path.join(env.runtime_dir, 'factory_update_server'))
    svc_conf = {
        'executable': update_server,
        'name': 'updatersvc',
        'args': [
            '-d', env.GetUpdatesDir(),
            '-p', str(constants.DEFAULT_RSYNC_PORT)],
        'path': env.GetUpdatesDir(),
        'logpipe': True,
        'auto_restart': True}
    self.SetConfig(svc_conf)
