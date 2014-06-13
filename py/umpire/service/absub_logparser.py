# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""AB subline logparser service for fixture log processing."""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.service import umpire_service


LOGPARSER_BIN = 'usr/local/factory/py/tools/logparser.py'
TAR_FILE_DIR = 'tarfiles'
RAW_DATA_DIR = 'rawdata'
VPD_FILE = os.path.join(TAR_FILE_DIR, 'vpd')
CAMERA_FILE = os.path.join(TAR_FILE_DIR, 'camera')
LOGPARSER_PORT_OFFSET = 5

class LogParserService(umpire_service.UmpireService):
  """Log parser service.

  Example:
    logparser_service = GetServiceInstance('absub_logparser')
    procs = logparser_service.CreateProcess(umpire_config_attrdict, umpire_env)
    logparser_service.Start(procs)
  """
  def __init__(self):
    super(LogParserService, self).__init__()
    self.properties['fastcgi_handlers'] = [
        {'path': '/logparser', 'port_offset': LOGPARSER_PORT_OFFSET},
        {'path': '/getvpd', 'port_offset': LOGPARSER_PORT_OFFSET},
        {'path': '/getcamera', 'port_offset': LOGPARSER_PORT_OFFSET}]

  def CreateProcesses(self, config, env):
    """Creates list of logparser process.

    Args:
      config: Umpire config AttrDict object.
      env: UmpireEnv object.

    Returns:
      A list of ServiceProcess objects.
    """
    proc_config = {
        'executable': os.path.join(env.active_server_toolkit_dir,
                                   LOGPARSER_BIN),
        'name': 'absubline_logparser',
        'args': [
            '--tar-file-dir', os.path.join(env.umpire_data_dir, TAR_FILE_DIR),
            '--raw-data-dir', os.path.join(env.umpire_data_dir, RAW_DATA_DIR),
            '--event-log-dir', os.path.join(env.umpire_data_dir, 'eventlog'),
            '--vpd-file', os.path.join(env.umpire_data_dir, VPD_FILE),
            '--camera-file', os.path.join(env.umpire_data_dir, CAMERA_FILE),
            '--fastcgi-tcp-port', config.port + LOGPARSER_PORT_OFFSET],
          'path': '/tmp'}
    return [proc_config]

_logparser_service = LogParserService()
