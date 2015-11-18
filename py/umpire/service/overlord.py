# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Overlord service for factory monitoring."""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.umpire.service import umpire_service
from cros.factory.utils.schema import Scalar


CONFIG_SCHEMA = {
    'optional_items': {
        'lan_disc_iface': Scalar('LAN discovery iterface', str),
        'noauth': Scalar('Disable authentication', bool),
        'tls': Scalar('TLS settings', str)}}

OVERLORDD_BIN = '/usr/bin/overlordd'
OVERLORD_SERVICE_NAME = 'overlord'


class OverlordService(umpire_service.UmpireService):
  """Overlord service.

  Example:
    svc = OverlordService()
    procs = svc.CreateProcesses(umpire_config_dict)
    svc.Start(procs)
  """
  def __init__(self):
    super(OverlordService, self).__init__()

  def GenerateArgs(self, umpire_config):
    args = []
    overlord_config = umpire_config['services']['overlord']

    if 'lan_disc_iface' in overlord_config:
      args.extend(['-lan-disc-iface', overlord_config['lan_disc_iface']])

    if 'noauth' in overlord_config and overlord_config['noauth']:
      args.extend(['-noauth'])

    if 'tls' in overlord_config:
      args.extend(['-tls', overlord_config['tls']])

    return args

  def FindOverlorddPath(self):
    # We are installed on server: 'usr/local/factory'
    if '/local/' in factory.FACTORY_PATH:
      return os.path.normpath(os.path.join(factory.FACTORY_PATH, '..', '..',
                                           'bin', 'overlordd'))
    else:
      return OVERLORDD_BIN

  def CreateProcesses(self, umpire_config, env):  # pylint: disable=W0613
    """Creates list of processes via config.

    Args:
      umpire_config: Umpire config dict.
      env: UmpireEnv object.

    Returns:
      A list of ServiceProcess.
    """
    proc_config = {
        'executable': self.FindOverlorddPath(),
        'name': OVERLORD_SERVICE_NAME,
        'args': self.GenerateArgs(umpire_config),
        'path': '/tmp'}
    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig(proc_config)
    return [proc]
