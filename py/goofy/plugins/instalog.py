# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import urlparse
import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy.plugins import plugin
from cros.factory.test.env import paths
from cros.factory.test import shopfloor
from cros.factory.test import testlog_goofy
from cros.factory.utils import process_utils


class Instalog(plugin.Plugin):
  """Run Instalog as a Goofy plugin."""

  def __init__(self, goofy, uplink_hostname, uplink_port, uplink_use_shopfloor):
    """Constructor.

    Args:
      goofy: The goofy instance.
      uplink_hostname: Hostname of the target for uploading logs.
      uplink_port: Port of the target for uploading logs.
      uplink_use_shopfloor: Use the configured Shopfloor's IP instead.  If
                            unable to properly retrieve the IP, fall back to
                            uplink_hostname.
    """
    super(Instalog, self).__init__(goofy)
    self._instalog_process = None
    self._config_path = os.path.join(paths.GetRuntimeVariableDataPath(),
                                     'instalog.yaml')

    node_id = testlog_goofy.GetDeviceID()
    data_dir = os.path.join(paths.GetLogRoot(), 'instalog')
    pid_file = os.path.join(paths.GetRuntimeVariableDataPath(), 'instalog.pid')
    log_file = os.path.join(paths.GetLogRoot(), 'instalog.log')
    cli_hostname = '0.0.0.0'
    cli_port = 7000
    testlog_json_path = goofy.testlog.primary_json.path
    uplink_enabled = (
        uplink_use_shopfloor or uplink_hostname) and uplink_port
    uplink_hostname = uplink_hostname
    uplink_port = uplink_port
    if uplink_use_shopfloor:
      url = shopfloor.get_server_url()
      if not url:
        if uplink_hostname:
          logging.error('Instalog: Could not retrieve Shopfloor IP; falling '
                        'back to provided uplink hostname "%s"',
                        uplink_hostname)
        else:
          logging.error('Instalog: Could not retrieve Shopfloor IP; no '
                        'fallback provided; disabling uplink functionality')
          uplink_enabled = False
      else:
        uplink_hostname = urlparse.urlparse(url).hostname

    config = {
        'instalog': {
            'node_id': node_id,
            'data_dir': data_dir,
            'pid_file': pid_file,
            'log_file': log_file,
            'cli_hostname': cli_hostname,
            'cli_port': cli_port
        },
        'buffer': {
            'plugin': 'buffer_simple_file',
        },
        'input': {
            'testlog_json': {
                'plugin': 'input_testlog_file',
                'path': testlog_json_path,
            },
        },
        'output': {
            'output_uplink': {
                'plugin': 'output_socket',
                'hostname': uplink_hostname,
                'port': uplink_port,
            }
        },
    }
    if not uplink_enabled:
      del config['output']['output_uplink']

    logging.info('Instalog: Saving config YAML to: %s', self._config_path)
    with open(self._config_path, 'w') as f:
      yaml.dump(config, f, default_flow_style=False)

  def RunCommand(self, args, blocking=False):
    if isinstance(args, basestring):
      args = [args]
    base_args = ['py/instalog/cli.py', '--config', self._config_path]
    logging.info('Instalog: Running command: %s' % ' '.join(base_args + args))
    p = process_utils.Spawn(base_args + args, cwd=paths.FACTORY_PATH)
    if blocking:
      p.communicate()
    return p

  def OnStart(self):
    self._instalog_process = self.RunCommand('start')

  def OnStop(self):
    self.RunCommand('stop', blocking=True)
    self._instalog_process.terminate()
