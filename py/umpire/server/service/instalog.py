# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog service for log processing."""

import hashlib
import logging
import os
import pprint
import socket

from cros.factory.umpire.server.service import umpire_service

from cros.factory.external import yaml


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

  def UpdateConfig(self, instalog_config, update_info, env):
    """Updates Instalog plugin config based on Umpire config.

    Args:
      instalog_config: Original Instalog configuration.
      update_info: The Umpire configuration used to update instalog_config.
      env: UmpireEnv object.
    """
    if update_info.get('data_truncate', {}).get('enable', False):
      # If enable data_truncate, Instalog truncate once a day.
      instalog_config['buffer']['args']['truncate_interval'] = 86400

    threshold = update_info.get('input_http', {}).get(
        'log_level_threshold', logging.NOTSET)
    instalog_config['input']['http_in']['args']['log_level_threshold'] = (
        threshold)

    if update_info.get('forward', {}).get('enable', False):
      args = update_info.get('forward', {}).get('args', {}).copy()
      # Umpire is running in docker, and we always use IP of umpire and port
      # published by docker.
      args['hostname'] = socket.gethostbyname(socket.gethostname())
      args['port'] = env.umpire_instalog_pull_socket_port
      instalog_config['output']['forward'] = {
          'plugin': 'output_pull_socket',
          'args': args
      }
      for input_name in instalog_config['input']:
        instalog_config['input'][input_name]['targets'].append('forward')

    if update_info.get('customized_output', {}).get('enable', False):
      args = update_info.get('customized_output', {}).get('args', {}).copy()
      # Umpire is running in docker, and we always use IP of umpire and port
      # published by docker.
      args['hostname'] = socket.gethostbyname(socket.gethostname())
      args['port'] = env.umpire_instalog_customized_output_port
      instalog_config['output']['customized_output'] = {
          'plugin': 'output_pull_socket',
          'args': args
      }
      for input_name in instalog_config['input']:
        instalog_config['input'][input_name]['targets'].append(
            'customized_output')

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
            'plugin': 'buffer_priority_testlog_file',
            'args': {
                'truncate_interval': 0
            }
        },
        'input': {
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
    config_value = pprint.pformat(instalog_config).encode('utf-8')
    config_hash = hashlib.md5(config_value).hexdigest()
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
        'path': '/tmp',
        'env': os.environ}
    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig(proc_config)
    return [proc]
