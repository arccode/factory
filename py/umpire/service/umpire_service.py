# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Umpire service base class.

Umpire service is an external application with a python class wrapper that
provides twisted process protocol. This is the base class and a global registry
for all service module.
"""


# Twisted module dynamically creates definitions at run time.
# pylint: disable=E1101


import copy
import importlib
import logging
import os
import sys
import time
import uuid
from twisted.internet import protocol, reactor

import factory_common  # pylint: disable=W0611
from cros.factory.schema import FixedDict, Scalar
from cros.factory.umpire.common import UmpireError


# Service package path
_SERVICE_PACKAGE = 'cros.factory.umpire.service'
# Service restart within _TIME_RESTART_FAST seconds is considered abnormal.
_TIME_RESTART_FAST = 5
# The maximum retries before cancel restarting external service.
_MAX_RESTART_COUNT = 5
# Optional service config schema
_OPTIONAL_SERVICE_SCHEMA = {
    'active': Scalar('Default service state on start', bool)}


# Map service name to sys.modules.
_SERVICE_MAP = {}


class UmpireService(protocol.ProcessProtocol):
  """Umpire service base class.

  Umpire daemon launches external executables and hooks their standard input,
  output and error. Since twisted protocol is an old-style Python class, hence
  the derived service class should call UmpireService.__init__() to initialize.

  On UmpireService.__init__(), the Python module contains the derived class is
  stored in a global map, with module name as key.

  UmpireService provides SetConfig(param_dict) to set up attributes.

  Attributes:
    start_time: Record external executable start up time.
    restart_count: Counts the service restarting within _TIME_RESTART_FAST.
    connection: Boolean flag, true if spawned process didn't close its stdin.
    subprocess: Twisted transport object to control spawned process.
    pid: Numeric process ID.
    stopping: Boolean flag indicates the subprocess is stopping and should not
              restart.

  SetConfig() required attributes:
    executable: Full pathname of external executable.
    name: Service name for logging.
    args: List of arguments, executable pathname excluded.
    path: Startup path.

  SetConfig() optional attributes:
    log: File handle to store stderr log output
    restart: True to restart service after exit.
    daemon: True if the executable daemonize itself.
    ext_args: Extended command line args.
    enable: False to disable the service on Umpire start.
  """
  def __init__(self):
    self.start_time = 0
    self.restart_count = 0
    self.connection = False
    self.subprocess = None
    self.pid = None
    self.stopping = False
    # Spawn parameters
    self.executable = None
    self.name = str(uuid.uuid1())
    self.args = []
    self.path = os.getcwd()
    self.uid = os.getuid()
    self.gid = os.getgid()
    self.log = None
    self.restart = False
    self.daemon = False
    self.ext_args = []
    self.enable = True
    # Update module map
    self.classname = self.__class__.__name__
    self.modulename = self.__class__.__module__
    self.module = sys.modules[self.modulename]
    _SERVICE_MAP[self.modulename] = self.module

  # Twisted process protocol callbacks
  def connectionMade(self):
    """On process start."""
    self.connection = True

  def outReceived(self, data):
    """On stdout receive."""
    logging.info('%s: %s', self.name, data)

  def errReceived(self, data):
    """On stderr receive."""
    if self.log:
      self.log.write(data)

  def inConnectionLost(self):
    """On stdin close."""
    self._ConnectionLost('stdin')
    self.connection = False

  def outConnectionLost(self):
    """On stdout close."""
    self._ConnectionLost('stdout')

  def errConnectionLost(self):
    """On stderr close."""
    self._ConnectionLost('stderr')

  def processEnded(self, status):
    """Subprocess has been ended."""
    # Daemon detach itself from parent process.
    if self.daemon:
      logging.info('%s (%d) daemonized itself.', self.name, self.pid)
      return
    logging.info('%s (%d) ended: %s', self.name, self.pid, status)
    self.subprocess = None
    if self.stopping:
      logging.info('%s stopped successfully.', self.name)
      return
    if self.restart:
      logging.info('%s restarting.', self.name)
      if time.time() - self.start_time < _TIME_RESTART_FAST:
        self.restart_count += 1
      else:
        self.restart_count = 0

      if self.restart_count >= _MAX_RESTART_COUNT:
        logging.error('%s respawn too fast, restart failed.', self.name)
      else:
        self.Start()

  # Local helper functions.
  def _ConnectionLost(self, msg):
    """Handles broken pipe."""
    logging.info('%s : pipe was closed - %s.', self.name, msg)

  # Interfaces.
  def SetConfig(self, conf_dict):
    """Sets service startup configuration.

    Params:
      conf_dict: Service attributes map. Please see class comments for required
                 and optional attributes SetConfig sets.

    Riases:
      UmpireError: When required attributes are missing.
    """
    req_attrs = ['executable', 'name', 'args', 'path']
    opt_attrs = ['uid', 'pid', 'log', 'restart', 'daemon', 'ext_args',
                 'enable']

    set_req = set(req_attrs)
    set_conf = set(conf_dict.keys())

    if not set_req.issubset(set_conf):
      set_diff = set_req.difference(set_conf)
      raise UmpireError('Missing service attribute(s): ' + str(set_diff))

    attrs = req_attrs + opt_attrs
    for key, value in conf_dict.iteritems():
      if key in attrs:
        setattr(self, key, value)

  def Start(self):
    """Starts background service."""
    self.stopping = False
    logging.debug('%s starting.', self.name)
    args = [self.exectable] + self.args + self.ext_args
    self.subprocess = reactor.spawnProcess(
        self,             # processProtocol
        self.exectuable,  # Full program pathname
        args,             # Args list, including executable
        {},               # Env vars
        self.path)        # Process CWD
    self.pid = self.subprocess.pid

  def Stop(self):
    """Stops background service."""
    self.stopping = True
    self.transport.signalProcess('TERM')


def GetServiceSchemata():
  """Gets a dictionary of service configuration schemata.

  Returns:
    A schema.FixedDict items parameter for validating service schemata.
  """
  schemata = {}
  for name, module in _SERVICE_MAP.iteritems():
    if hasattr(module, 'CONFIG_SCHEMA'):
      items = module.CONFIG_SCHEMA
      optional_items = copy.deepcopy(_OPTIONAL_SERVICE_SCHEMA)
      for key in items:
        if key in optional_items:
          del optional_items[key]
      schemata[name] = FixedDict(
          'Service schema:' + name,
          items=items,
          optional_items=optional_items)
    else:
      schemata[name] = FixedDict(
          'Service schema:' + name,
          optional_items=copy.deepcopy(_OPTIONAL_SERVICE_SCHEMA))
  return FixedDict('Service schemata', items=schemata)


def LoadServiceModule(module_name):
  """Imports service python module.

  Returns:
    Module object.

  Raises:
    ImportError: when fails to find a name.
  """
  return importlib.import_module(module_name, _SERVICE_PACKAGE)
