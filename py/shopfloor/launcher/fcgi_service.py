# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Shopfloor FastCGI service."""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher.service import ServiceBase


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
               '-f'],
      'auto_restart': True,
      'logpipe': True
    }
    self.SetConfig(svc_conf)

