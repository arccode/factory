# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Shopfloor FastCGI service."""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor import AUX_LOGS_DIR
from cros.factory.shopfloor import EVENTS_DIR
from cros.factory.shopfloor import REPORTS_DIR
from cros.factory.shopfloor.launcher import constants
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher.service import ServiceBase
from cros.factory.test.utils import TryMakeDirs


class FcgiService(ServiceBase):
  def __init__(self, yaml_conf):
    """Configures shopfloor xmlrpc server to FastCGI mode."""

    # ServiceBase inherits from Protocol, which is an old-style class and
    # cannot use super() to init.
    ServiceBase.__init__(self)

    shopfloor_server = os.path.abspath(
        os.path.join(env.runtime_dir, 'shopfloor_server'))
    svc_conf = {
      'executable': shopfloor_server,
      'name': 'fcgisvc',
      'args': ['-a', '127.0.0.1',
               '-p', str(env.fcgi_port),
               '-m', yaml_conf['shopfloor']['shopfloor_module'],
               '-f',
               '-v',
               '-u', 'cros.factory.shopfloor.launcher.update_state',
               '--updater-dir', env.GetUpdatesDir()],
      'auto_restart': True,
      'logpipe': True
    }
    self.SetConfig(svc_conf)

    # Creates shopfloor xmlrpc server symlink and folders.
    if not os.path.isfile(shopfloor_server):
      os.symlink(os.path.join(env.runtime_dir, constants.FACTORY_SOFTWARE),
                 shopfloor_server)
    shopfloor_data = os.path.join(env.runtime_dir, constants.SHOPFLOOR_DATA)
    TryMakeDirs(shopfloor_data)
    TryMakeDirs(os.path.join(shopfloor_data, REPORTS_DIR))
    TryMakeDirs(os.path.join(shopfloor_data, EVENTS_DIR))
    TryMakeDirs(os.path.join(shopfloor_data, AUX_LOGS_DIR))


Service = FcgiService
