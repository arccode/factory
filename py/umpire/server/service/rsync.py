# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""RSYNC service for factory toolkit update."""

import os

from cros.factory.umpire.server.service import umpire_service
from cros.factory.utils import file_utils


RSYNC_BIN = '/usr/bin/rsync'
# rsync daemon mode configuration file doesn't need hash in name.
RSYNCD_CONFIG_FILENAME = 'rsyncd.conf'
RSYNCD_LOG_FILENAME = 'rsyncd.log'
RSYNCD_PID_FILENAME = 'rsyncd.pid'
RSYNCD_CONFIG_TEMPLATE = """port = %(port)d
pid file = %(pidfile)s
log file = %(logfile)s
use chroot = no
uid = 0
gid = 0
"""
RSYNCD_CONFIG_MODULE_PATH_TEMPLATE = """[%(module)s]
  path = %(path)s
  read only = %(readonly)s
"""


class RsyncService(umpire_service.UmpireService):
  """RSYNC service.

  Example:
    rsync_service = RsyncService()
    procs = rsync_service.CreateProcesses(umpire_config_dict, env)
    rsync_service.Start(procs)
  """

  def CreateProcesses(self, umpire_config, env):
    """Creates list of processes via config.

    Args:
      umpire_config: Umpire config AttrDict.
      env: UmpireEnv object.

    Returns:
      A list of ServiceProcesses.
    """
    del umpire_config  # Unused.
    config_path = os.path.join(env.config_dir, RSYNCD_CONFIG_FILENAME)
    log_path = os.path.join(env.log_dir, RSYNCD_LOG_FILENAME)
    pid_path = os.path.join(env.pid_dir, RSYNCD_PID_FILENAME)
    rsyncd_config = RSYNCD_CONFIG_TEMPLATE % {
        'port': env.umpire_rsync_port, 'pidfile': pid_path, 'logfile': log_path}
    # Add deprecated auxiliary log support.
    system_logs_dir = os.path.join(env.log_dir, 'dut_upload')
    file_utils.TryMakeDirs(system_logs_dir)
    rsyncd_config += RSYNCD_CONFIG_MODULE_PATH_TEMPLATE % {
        'module': 'system_logs', 'path': system_logs_dir, 'readonly': 'no'}
    file_utils.WriteFile(config_path, rsyncd_config)

    proc_config = {
        'executable': RSYNC_BIN,
        'name': 'rsync',
        'args': ['--daemon', '--no-detach', '--config=%s' % config_path],
        'path': '/tmp'}
    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig(proc_config)
    return [proc]
