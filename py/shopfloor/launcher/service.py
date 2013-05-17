# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The base class of shopfloor launcher services."""

# Python twisted's module creates definition dynamically
# pylint: disable=E1101


import logging
import os
import time
from twisted.internet import protocol, reactor

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import ShopFloorLauncherException
from cros.factory.shopfloor.launcher import env


class ServiceBase(protocol.ProcessProtocol):
  """Base class of shopfloor launcher service.

  The launcher runs external executables and hooks their standard input and
  outputs. The derived class should call ServiceBase.__init__() to setup
  ServiceBase and then call SetConfig(param_dict) to setup attributes.

  Attributes:
    start_time: Records the time on Start().
    connection: True if the spawned process didn't close its stdin.
    subprocess: Twisted transport object that controls the spawned subprocess.
    pid: Process ID in int.
    stopping: Flag indicates this subprocess is on the halfway to stop.
    # For setting up spawn parameters:
    executable: Executable full pathname.
    name: Service name for logging.
    args: List of arguments, not including executable itself.
    path: Startup path.
    # Optional spawn parameters:
    logpipe: True to redirect stderr to launcher log.
    auto_restart: True when the service needs to be restarted.
    daemon: True when the executable daemonize itself.
  """

  def __init__(self):
    self.start_time = 0
    self.connection = False
    self.subprocess = None
    self.pid = None
    self.stopping = False
    # Spawn parameters
    self.executable = None
    self.name = 'svc'
    self.args = []
    self.path = env.runtime_dir
    self.uid = os.getuid()
    self.gid = os.getgid()
    self.logpipe = False
    self.auto_restart = False
    self.daemon = False

  # Twisted process protocol callbacks
  def connectionMade(self):
    """On process started and its stdin is in a good place to write data."""
    self.connection = True

  def outReceived(self, data):
    """On data received from the process' stdout pipe."""
    if self.logpipe:
      logging.info('%s: %s', self.name, data)

  def errReceived(self, data):
    """On data received from stderr pipe."""
    if self.logpipe:
      logging.warn('%s: %s', self.name, data.rstrip())

  def inConnectionLost(self):
    """Subprocess' stdin has closed."""
    self._ConnectionLost('stdin')
    self.connection = False

  def outConnectionLost(self):
    """Subprocess' stdout has closed."""
    self._ConnectionLost('stdout')

  def errConnectionLost(self):
    """Subprocess' stderr has closed."""
    self._ConnectionLost('stderr')

  def processEnded(self, status):
    """Subprocess has been ended properly."""
    if self.daemon:
      return
    self.subprocess = None
    if status.value.exitCode != 0:
      logging.warn('%s process ended with status %s', self.name, status)
    if self.auto_restart:
      if self.stopping:
        logging.info('%s ended', self.name)
      else:
        logging.info('%s restarting', self.name)
        if time.time() - self.start_time > 5:
          self.Start()
        else:
          logging.error('%s respawn too fast, restart failed', self.name)

  def _ConnectionLost(self, pipe):
    """Genetic handler for broken pipes."""
    if not self.daemon and not self.stopping :
      logging.info('%s was closed',  pipe)

  def SetConfig(self, conf):
    """Sets service configuration."""

    attrs = ['name', 'executable', 'path', 'args', 'uid', 'pid',
             'logpipe', 'auto_restart', 'daemon']
    for key in attrs:
      if key in conf:
        setattr(self, key, conf[key])

  def Start(self):
    """Starts background service."""
    self.stopping = False
    logging.debug('Starting %s', self.name)
    self.subprocess = reactor.spawnProcess(self, self.executable,
                                           [self.executable] + self.args,
                                           {}, self.path)
    self.pid = self.subprocess.pid
    logging.debug('%s started: pid = %d', self.name, self.pid)
    self.start_time = time.time()

  def Stop(self):
    """Stops background service."""
    self.stopping = True
    self.transport.loseConnection()
    self.transport.signalProcess('TERM')

  def CheckPortPrivilage(self, port):
    """Check binding port number if not run as root."""
    if port < 1024:
      if os.getuid() != 0:
        raise ShopFloorLauncherException('%s port < 1024' % self.name)
