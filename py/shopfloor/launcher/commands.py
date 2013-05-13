# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Launcher Commands.

Shopfloor command line utility passes its sys.argv in a json serialized string
to command port. This module provides a server factory class for twisted
LineReceiver protocol. When a json object arrives, connection dispatcher
calls callable command object to handle one command.
"""


import glob
import json
import logging
import os
from twisted.internet.protocol import ServerFactory, connectionDone
from twisted.protocols.basic import LineReceiver

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher import ShopFloorLauncherException
from cros.factory.shopfloor.launcher import utils
from cros.factory.shopfloor.launcher.yamlconf import LauncherYAMLConfig


class LauncherCommandError(Exception):
  pass


def ValidateCommand(command):
  """Validateis deserialized JSON command dictionary.

  JSON command should be a dictionary and contains at least:
    'cwd': the current working directory of command line utility
    'args': 'sys.argv' from the command line utility

  Args:
    command: Deserialized JSON command dictionary.

  Raises:
    LauncherCommandError: When the command is not a dict, or at least one of
                          the required fields is missing.
  """
  if not isinstance(command, dict):
    raise LauncherCommandError('Command is not a dictionary')
  if 'cwd' not in command:
    raise LauncherCommandError('Missing field: cwd')
  if 'args' not in command or not isinstance(command['args'], list):
    raise LauncherCommandError('Missing field: args')


class ConnectionDispatcher(LineReceiver):
  """Command line parser and dispatcher."""

  # Override LineReceiver's line delimiter ('\r\n')
  delimiter = '\n'

  def __init__(self):
    # LineReceiver is a twisted protocol. The factory member will be
    # initialized by ServerFactory class, which uses this protocol on
    # accept new connections.
    self.factory = None
    # session variable stores stringified remote peer.
    self.session = None

  def rawDataReceived(self, data):
    pass

  def connectionMade(self):
    self.session = str(self.transport.getPeer())
    logging.info('Client connection from %s', self.session)
    if len(self.factory.clients) < self.factory.clients_max:
      self.factory.clients.append(self.session)
    else:
      logging.info('Too many connections: disconnecting %s', self.session)
      self.transport.write('Too many client connections')
      self.transport.loseConnection()

  def connectionLost(self, reason=connectionDone):
    logging.info('Connection lost: %s : %s', self.session, reason)
    self.factory.clients.remove(self.session)

  def lineReceived(self, json_line):
    """Callback when json command line received."""
    response = ''
    try:
      request = json.loads(json_line)
      ValidateCommand(request)
      request['connection'] = self
      command = request['args'][1]
      response = self.factory.Dispatch(command, request)
    except Exception as e:
      self._ReturnError('ERROR: exception %r' % e)
      return
    self.transport.write(response)
    self.transport.loseConnection()

  def _ReturnError(self, msg):
    logging.error(msg)
    self.transport.write(msg)
    self.transport.loseConnection()


class CommandHandler(object):
  """Command handler base class."""
  def Handle(self, args, request):
    raise NotImplementedError('Handle')

  def __call__(self, request):
    args = request['args'][2:]
    return self.Handle(args, request)


class CommandDeploy(CommandHandler):
  """Handler for deploy command."""
  def Handle(self, args, request):
    """Deploys new configuration file."""
    new_config_file = os.path.join(env.GetResourcesDir(), args[0])
    try:
      # Update new configuration and restart services
      utils.UpdateConfig(new_config_file)
    except Exception as e:
      return 'ERROR: failed to deploy new configuration %s' % e
    if os.getuid() == 0:
      utils.CreateConfigSymlink(new_config_file)
      #TODO(rong): utils.CreateBinSymlink()
    return "OK: %r deployed successfully." % new_config_file


class CommandImport(CommandHandler):
  """Handler for import command."""
  def Handle(self, args, request):
    """Imports resource files to system folder."""
    cwd = request['cwd']
    if len(args) == 2 and args[0] == '--all':
      # Process "shopfloor import --all shopfloor.yaml"
      yaml_file = utils.SearchFile(
          args[1],
          [cwd, os.path.join(cwd, 'resources')])
      if yaml_file is None:
        return 'ERROR: YAML config file not found %s' % args[1]
      resources = [os.path.join(cwd, 'resources', res) for res in
                   utils.ListResources(yaml_file)]
    else:
      # Process "shopfloor import res1 [res2 [res3 ...]]"
      resources = list()
      for res in args:
        pathname = utils.SearchFile(
            res, [cwd, os.path.join(cwd, 'resources')])
        if pathname is None:
          return 'ERROR: resource not found: %s' % res
        resources.append(pathname)
    utils.PrepareResources(resources)
    return 'OK: resources imported.'


class CommandInfo(CommandHandler):
  """Handler for info command."""
  def Handle(self, args, request):
    """Gets human readable running config file name, version and other info."""
    return utils.GetInfo()


class CommandInit(CommandHandler):
  """Handler for init command."""
  def Handle(self, args, request):
    """Creates system directory structure."""
    utils.CreateSystemFolders()
    return "OK: system folders created."


class CommandList(CommandHandler):
  """Handler for list command."""
  def Handle(self, args, request):
    """Lists available configurations."""
    response = ['OK: available YAML configurations:']
    config_files = glob.glob(os.path.join(env.GetResourcesDir(),
                             "shopfloor.yaml#*"))
    for config in config_files:
      filename = os.path.basename(config)
      yaml_config = LauncherYAMLConfig(config)
      response.append('  %s - %s' % (filename, yaml_config['info']['version']))
    return '\n'.join(response)


class CommandVerify(CommandHandler):
  """Handler for verify command."""
  def Handle(self, args, request):
    """Verifies the resource files and structure of YAML config file."""
    cwd = request['cwd']
    all_passed = True
    local_config = set([os.path.basename(res) for res in
                        glob.glob(os.path.join(cwd, 'resources',
                                  'shopfloor.yaml#*'))])
    system_config = set([os.path.basename(res) for res in
                         glob.glob(os.path.join(env.GetResourcesDir(),
                                  'shopfloor.yaml#*'))])
    all_config = set().union(local_config, system_config)
    config_name = os.path.basename(args[0])
    if config_name not in all_config:
      raise ShopFloorLauncherException('Config file not found %r' % config_name)
    response = ['YAML config file: %s' % config_name]
    if config_name in system_config:
      response.append('  installed')
    resources = utils.ListResources(args[0])
    for res in resources:
      try:
        utils.VerifyResource(res)
        response.append('  OK: %s' % res)
      except Exception:
        response.append('  FAIL: %s' % res)
        all_passed = False
    if all_passed:
      response.append('OK: all resources in YAML config are good.')
    else:
      response.append('ERROR: YAML config verify failed.')
    return '\n'.join(response)


class LauncherCommandFactory(ServerFactory):
  """Twisted protocol factory for shopfloor command session."""
  protocol = ConnectionDispatcher

  def __init__(self, clients_max=10):
    """Initializes command map and the client list."""
    self.commands = {}
    self.clients = []
    self.clients_max = clients_max

    self.Add('deploy', CommandDeploy())
    self.Add('import', CommandImport())
    self.Add('info', CommandInfo())
    self.Add('init', CommandInit())
    self.Add('list', CommandList())
    self.Add('verify', CommandVerify())

  def Add(self, cmd, handler):
    handler.factory = self
    self.commands[cmd] = handler

  def Dispatch(self, cmd, request):
    return self.commands[cmd](request)

