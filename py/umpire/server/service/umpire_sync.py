# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Synchronize all secondary umpires to the same version of bundles

1. Get the urls of secondary umpires from services' list
2. Implement the service in umpire_sync / index.py
3. Update secondary umpires' status in `umprie_sync_status.json`
"""

import os

from cros.factory.umpire.server.service import umpire_service


LOG_FILENAME = 'umpire_sync_log'
SERVICE_NAME = 'umpire_sync'
STATUS_FILENAME = 'umpire_sync_status.json'
RPC_PORT_OFFSET = 2


class UmpireSync(umpire_service.UmpireService):
  """UmpireSync service.

  Example:
    svc = GetServiceInstance('umpire_sync')
    procs = svc.CreateProcesses(umpire_config_dict, umpire_env)
    svc.Start(procs)
  """

  def CreateProcesses(self, umpire_config, env):
    """Creates list of processes via config.

    Args:
      umpire_config: Umpire config dict.
      env: UmpireEnv object.

    Returns:
      A list of ServiceProcess.
    """

    umpire_sync_config = umpire_config['services']['umpire_sync']
    log_path = os.path.join(env.log_dir, LOG_FILENAME)
    status_path = os.path.join(env.umpire_data_dir, STATUS_FILENAME)
    primary_url = 'http://%s:%s' % (
        umpire_sync_config['primary_information']['ip'],
        umpire_sync_config['primary_information']['port'])
    secondary_urls = []
    sync_time = umpire_sync_config.get('synchronize_time', '60')

    if 'secondary_information' in umpire_sync_config:
      for info in umpire_sync_config['secondary_information']:
        secondary_url = 'http://%s:%s' % (info['ip'], info['port'])
        secondary_urls.append(secondary_url)

    script_path = os.path.join(env.server_toolkit_dir, 'py', 'umpire_sync',
                               'main.py')
    proc_config = {
        'executable': script_path,
        'name': SERVICE_NAME,
        'args': [
            '-l',
            log_path,
            '-s',
            status_path,
            '-p',
            primary_url,
            '-t',
            sync_time,
            '--secondary_urls',
            *secondary_urls,
        ],
        'path': '/tmp',
        'env': os.environ
    }
    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig(proc_config)
    return [proc]
