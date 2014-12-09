# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Mock backend launcher for launching a mocked factory backend server."""


import logging
import os

import factory_common  # pylint: disable=W0611
from cros.factory import schema
from cros.factory.umpire.service import umpire_service

CONFIG_SCHEMA = {
    'optional_items': {
        'mlbs_csv': schema.Scalar('mlbs.csv path', str)}}


class MockBackendService(umpire_service.UmpireService):
  """Mock backend service.

  Example:
    backend_service = GetServiceInstance('mock_backend')
    procs = backend_service.CreateProcesses(umpire_config, umpire_env)
    backend_service.Start(procs)
  """

  def CreateProcesses(self, config, env):
    """Creates list of mock shopfloor server backend processes.

    Args:
      config: UmpireConfig AttrDict object.
      env: UmpireEnv instance.

    Returns:
      list of ServiceProcesses.
    """
    mock_backend = os.path.join(
        env.active_server_toolkit_dir,
        'usr/local/factory/py/shopfloor/%s_mock_shopfloor_backend.py' %
        config.board)
    logging.info('Creating mock backend process: %s', mock_backend)
    mlbs_csv = config.services.mock_backend.get('mlbs_csv', 'mlbs.csv')
    if not os.path.isabs(mlbs_csv):
      mlbs_csv = os.path.join(env.umpire_data_dir, mlbs_csv)

    if not os.path.isfile(mlbs_csv):
      logging.warn('MLBS csv file does not exist: %s', mlbs_csv)
      logging.warn('Skip mock_backend service')
      return []

    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig({
        'executable': mock_backend,
        'name': 'Mock ShopFloor Backend',
        'args': ['-v', mlbs_csv],
        'path': env.umpire_data_dir})
    return [proc]


# Create service instance
_service_instance = MockBackendService()
