# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog service for log processing."""

import hashlib
import os
import pprint

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.service import umpire_service
from cros.factory.utils import schema

from cros.factory.external import yaml


CONFIG_SCHEMA = {
    'optional_items': {
        'archive': schema.FixedDict('archive', optional_items={
            'enable': schema.Scalar('enable', bool),
            'args': schema.FixedDict('args', optional_items={
                'interval': schema.Scalar('interval', int)
            })
        }),
        'forward': schema.FixedDict('forward', optional_items={
            'enable': schema.Scalar('enable', bool),
            'args': schema.FixedDict('args', optional_items={
                'hostname': schema.Scalar('hostname', str),
                'port': schema.Scalar('port', int),
                'batch_size': schema.Scalar('batch_size', int)
            })
        })
    }
}

CLI_HOSTNAME = '0.0.0.0'  # Allows remote connections.
CLI_PORT = 7000
NODE_ID = 'factory_server'
SERVICE_NAME = 'instalog'


class InstalogService(umpire_service.UmpireService):
  """Instalog service.

  Example:
    svc = GetServiceInstance('instalog')
    procs = svc.CreateProcesses(umpire_config_dict, umpire_env)
    svc.Start(procs)
  """

  def __init__(self):
    super(InstalogService, self).__init__()

  def UpdateConfig(self, instalog_config, update_info, env):
    """Updates Instalog plugin config based on Umpire config.

    Args:
      instalog_config: Original Instalog configuration.
      update_info: The Umpire configuration used to update instalog_config.
      env: UmpireEnv object.
    """
    if update_info.get('forward', {}).get('enable', False):
      instalog_config['output']['forward'] = {
          'plugin': 'output_socket',
          'args': update_info.get('forward', {}).get('args', {}).copy()
      }
      # If no hostname or port is provided, we should fail.
      if ('hostname' not in instalog_config['output']['forward']['args'] or
          'port' not in instalog_config['output']['forward']['args']):
        raise ValueError('Instalog forwarding is enabled; hostname and port '
                         'must be provided')
      for input_name in instalog_config['input']:
        instalog_config['input'][input_name]['targets'].append('forward')
    if update_info.get('archive', {}).get('enable', False):
      instalog_config['output']['archive'] = {
          'plugin': 'output_archive',
          'args': update_info.get('archive', {}).get('args', {}).copy()
      }
      # Set the target_dir.
      target_dir = os.path.join(env.umpire_data_dir, 'instalog_archives')
      instalog_config['output']['archive']['args']['target_dir'] = target_dir
      for input_name in instalog_config['input']:
        instalog_config['input'][input_name]['targets'].append('archive')

  def GenerateConfigFile(self, umpire_config, env):
    """Generates Instalog configuration file and symlinks '~/.instalog.yaml'.

    Returns:
      The path of Instalog configuration file.
    """
    root_dir = os.path.join(env.umpire_data_dir, 'instalog')
    if not os.path.isdir(root_dir):
      os.makedirs(root_dir)
    instalog_config = {
        'instalog': {
            'node_id': NODE_ID,
            'data_dir': os.path.join(root_dir, 'data'),
            'pid_file': os.path.join(os.sep, 'run', 'instalog.pid'),
            'log_file': os.path.join(root_dir, 'instalog.log'),
            'cli_hostname': CLI_HOSTNAME,
            'cli_port': CLI_PORT
        },
        'buffer': {
            'plugin': 'buffer_simple_file',
            'args': {
                'truncate_interval': 0
            }
        },
        'input': {
            # TODO(chuntsen): Remove input_socket.
            'socket_in': {
                'plugin': 'input_socket',
                'targets': [],
                'args': {
                    'port': env.umpire_instalog_socket_port
                }
            },
            'http_in': {
                'plugin': 'input_http_testlog',
                'targets': [],
                'args': {
                    'port': env.umpire_instalog_http_port
                }
            },
            'health': {
                'plugin': 'input_health',
                'targets': []
            }
        },
        'output': {
        }
    }
    self.UpdateConfig(
        instalog_config, umpire_config['services']['instalog'], env)
    # pprint guarantees the dictionary is sorted.
    config_hash = hashlib.md5(pprint.pformat(instalog_config)).hexdigest()
    config_path = os.path.join(root_dir, 'instalog-%s.yaml' % config_hash)
    if os.path.exists(config_path):
      os.remove(config_path)
    with open(config_path, 'w') as f:
      yaml.dump(instalog_config, f, default_flow_style=False)
    config_link = os.path.join(os.path.expanduser('~'), '.instalog.yaml')
    if not os.path.exists(config_link):
      os.symlink(config_path, config_link)
    return config_path

  def CreateProcesses(self, umpire_config, env):
    """Creates list of processes via config.

    Args:
      umpire_config: Umpire config dict.
      env: UmpireEnv object.

    Returns:
      A list of ServiceProcess.
    """
    if ('services' not in umpire_config or
        'instalog' not in umpire_config['services']):
      return None
    cli_path = os.path.join(env.server_toolkit_dir, 'py', 'instalog', 'cli.py')
    config_path = self.GenerateConfigFile(umpire_config, env)
    proc_config = {
        'executable': cli_path,
        'name': SERVICE_NAME,
        # Have to use --no-daemon when starting instalog, because Umpire will
        # supervise the process by its pid.
        'args': ['--config', config_path, 'start', '--no-daemon'],
        'path': '/tmp'}
    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig(proc_config)
    return [proc]
