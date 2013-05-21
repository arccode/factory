# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Rsync service.

This service configures launcher to start rsync daemon that serves factory
bundle update and log upload.
"""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import constants
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher.service import ServiceBase
from cros.factory.test.utils import TryMakeDirs

RSYNCD_CONFIG_TEMPLATE = '''port = %(port)d
pid file = %(pidfile)s
log file = %(logfile)s
use chroot = no
'''
RSYNCD_CONFIG_MODULE_PATH_TEMPLATE = '''[%(module)s]
  path = %(path)s
  read only = %(read_only)s
'''


class RsyncService(ServiceBase):
  """Rsync configuration.

  Args:
    yaml_config: Launcher YAML config dictionary.
  """
  def __init__(self, dummy_config):
    # ServiceBase inherits from an old-style python class.
    ServiceBase.__init__(self)

    config_file = os.path.join(env.runtime_dir, 'rsyncd.conf')
    log_file = os.path.join(env.runtime_dir, 'log', 'rsync.log')
    pid_file = os.path.join(env.runtime_dir, 'run', 'rsync.pid')
    if os.path.exists(pid_file):
      os.unlink(pid_file)

    rsync_config = RSYNCD_CONFIG_TEMPLATE % dict(
        port=constants.DEFAULT_RSYNC_PORT,
        pidfile=pid_file,
        logfile=log_file)

    # Factory update module
    rsync_config += RSYNCD_CONFIG_MODULE_PATH_TEMPLATE % dict(
        module='factory',
        path=os.path.join(env.GetUpdatesDir(), 'factory'),
        read_only='yes')

    # Log upload module
    upload_path = os.path.join(env.runtime_dir, 'upload_logs')
    TryMakeDirs(upload_path)
    rsync_config += RSYNCD_CONFIG_MODULE_PATH_TEMPLATE % dict(
        module='system_logs',
        path=upload_path,
        read_only='no')

    with open(config_file, 'w') as f:
      f.write(rsync_config)

    svc_conf = {
      'executable': 'rsync',
      'name': 'rsyncsvc',
      'args': [
        '--daemon',
        '--no-detach',
        '--config=%s' % config_file],
      'path': env.runtime_dir,
      'logpipe': False,
      'auto_restart': True}
    self.SetConfig(svc_conf)


Service = RsyncService
