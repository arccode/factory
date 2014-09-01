# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Python twisted's module creates definition dynamically, pylint: disable=E1101

"""Umpire daemon.

Umpire: the unified factory server. Umpired is a daemon that launches factory
server applications, like shop floor proxy, log analyzer and testing program
updater.
"""

import logging
from signal import signal, SIGINT, SIGTERM
from twisted.internet import defer, reactor
from twisted.python.failure import Failure
from twisted.web import server, wsgi, xmlrpc

import factory_common  # pylint: disable=W0611
from cros.factory.common import AttrDict, Singleton
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire.service.umpire_service import (
    GetAllServiceNames, GetServiceInstance)
from cros.factory.umpire.utils import ConcentrateDeferreds
from cros.factory.umpire.web.wsgi import WebAppDispatcher
from cros.factory.umpire.web.xmlrpc import XMLRPCContainer


LOCALHOST = '127.0.0.1'


class UmpireDaemon(object):

  """Umpire daemon class.

  Umpire daemon is a singleton. It builds XMLRPC sites that serves command line
  utility and DUT requests related to umpire configuration. It also builds web
  application sites that provides interfaces for simple HTTP GET and POST.

  The daemon also has functional interfaces to restart service processes on
  configuration change.

  Examples:
    Restart service process after deployed new configuration:
        UmpireDaemon().Deploy()

    Stop Umpire daemon:
        UmpireDaemon().Stop()

  Properties:
    env: UmpireEnv object.
    deployed_config: latest Umpire configuration AttrDict.
    methods_for_cli: list of command objects for Umpire CLI (Command Line
                     Interface) to access.
    methods_for_dut: list of RPC objects for DUT (Device Under Test) to access.
    web_applications: web application dispatcher that maps request path info
                      to application object.
    twisted_ports: binded twisted ports.
    deploying: daemon is deploying a config and not finished yet.
  """
  __metaclass__ = Singleton

  def __init__(self, env):
    self.env = env
    self.deployed_config = None
    self.methods_for_cli = []
    self.methods_for_dut = []
    self.web_applications = WebAppDispatcher()
    # Twisted port object is TCP server port, listening for connections.
    # port.stopListening() will be called on reactor.stop()
    # The ports are stored here for unittests to stopListening() them
    # between tests.
    self.twisted_ports = []
    self.deploying = False

  def _HandleStopSignal(self, sig, unused_frame):
    """Handles signals that stops event loop.

    Umpire daemon prevents twisted event loop to handle SIGINT and
    SIGTERM. This signal handler stops the daemon and Twisted event
    loop nicely.
    """
    logging.info('Received signal %d', sig)
    logging.info('Stopping umpired...')
    self.Stop()

  def Stop(self):
    """Stops subprocesses and quits daemon loop."""
    service_names = GetAllServiceNames()
    if service_names:
      deferred = self.StopServices(service_names)
      deferred.addBoth(lambda _: reactor.stop())
    else:
      reactor.stop()
    return defer.succeed(True)

  def OnStart(self):
    """Daemon start handler."""
    def HandleStartError(failure):
      logging.debug('Failed to start Umpire daemon: %s', str(failure))
      self.Stop()
      # Reactor is stopping, no need to propagate this failure.
      return True

    # Deploy the loaded configuration.
    d = self.Deploy()
    d.addErrback(HandleStartError)

  def BuildWebAppSite(self, interface=LOCALHOST):
    """Buulds web application resource and site."""
    if not self.web_applications:
      raise UmpireError('Can not build web site without web application')
    # Build wsgi site.
    web_resource = wsgi.WSGIResource(reactor, reactor.getThreadPool(),
                                     self.web_applications)
    web_site = server.Site(web_resource)
    # Listen to webapp server port.
    self.twisted_ports.append(reactor.listenTCP(self.env.umpire_webapp_port,
                                                web_site, interface=interface))

  def BuildRPCSite(self, port, rpc_objects, interface=LOCALHOST):
    """Builds RPC resource and site.

    Args:
      port: the server port number to listen.
      rpc_objects: list of UmpireRPC objects.
      interface: network interface to bind, can be '0.0.0.0'.
    """
    if not rpc_objects:
      raise UmpireError('Can not build RPC site without rpc object')
    # Build command rpc site.
    rpc_resource = XMLRPCContainer()
    map(rpc_resource.AddHandler, rpc_objects)
    xmlrpc.addIntrospection(rpc_resource)
    rpc_site = server.Site(rpc_resource)
    # Listen to rpc server port.
    self.twisted_ports.append(reactor.listenTCP(port, rpc_site,
                                                interface=interface))

  def Run(self):
    """Starts the daemon and event loop."""
    self.BuildWebAppSite()
    # Umpire CLI and DUT RPCs are called by web server, which is running on the
    # same host. Hence keep interface=LOCALHOST default value.
    self.BuildRPCSite(self.env.umpire_cli_port, self.methods_for_cli)
    self.BuildRPCSite(self.env.umpire_rpc_port, self.methods_for_dut)
    # Install signal handler.
    signal(SIGTERM, self._HandleStopSignal)
    signal(SIGINT, self._HandleStopSignal)
    # Start services.
    reactor.callWhenRunning(self.OnStart)
    # And start reactor loop.
    reactor.run(installSignalHandlers=0)

  def Deploy(self, restart_all=False):
    """Starts the loaded configuration.

    UmpireDaemon().Deploy() starts processes using latest deployed
    configuration. It returns deferred object to caller to add callback
    and errback.

    On deploy failed, the caller needs to deploy last known good config
    in errback handler.

    Args:
      restart_all: restarts all services, even if previous one was started
                   with same parameters.

    Returns:
      Deferred object that relays success or failure. Caller should take
      care of the fallback options in deferred object's error callback.
    """
    def _GetActiveServiceNames(config):
      """Gets list of active service names in config.

      Args:
        config: UmpireConfig object.

      Yields:
        Active service names.
      """
      for name, service_config in config.services.iteritems():
        if not (hasattr(service_config, 'active') and
                service_config.active == False):
          yield name

    def _Deployed(result, deploying_config):
      """Switches config and flag on deploying finished."""
      # Clear deploying state.
      self.deploying = False
      # Switch deployed_config to new one.
      if not isinstance(result, Failure):
        self.deployed_config = deploying_config
      return result

    def _Rollback(result, stopping_services, starting_services):
      """Stops starting_services and starts stopping_services."""
      def _HandleRollbackError(failure):
        """Ignores rollback error."""
        exc_info = (failure.type, failure.value, failure.tb)
        logging.error('Failed rolling back configuration',
                      exc_info=exc_info)
        return True

      stopping = self.StopServices(starting_services)
      starting = self.StartServices(stopping_services)
      deferred = ConcentrateDeferreds([stopping, starting])
      deferred.addErrback(_HandleRollbackError)
      return result

    if self.deploying:
      return defer.fail(UmpireError('Another deployment in progress'))

    # Switch to deploying state, this flag will be cleard in callback/errback.
    self.deploying = True
    stopping_services = None
    starting_services = None
    # Record both old and new configuration.
    current_config = self.deployed_config
    deploying_config = AttrDict(self.env.config)
    current_services = set(_GetActiveServiceNames(current_config)
                           if current_config else [])
    deploying_services = set(_GetActiveServiceNames(deploying_config))
    # Calculate services to stop and start.
    if restart_all:
      stopping_services = current_services
      starting_services = deploying_services
    else:
      stopping_services = current_services - deploying_services
      starting_services = deploying_services - current_services
    # Need to restart shop_floor service.
    starting_services.add('shop_floor')
    # Stop unused services and start new services.
    stopping_deferred = self.StopServices(stopping_services)
    starting_deferred = self.StartServices(starting_services)
    deferred = ConcentrateDeferreds([stopping_deferred, starting_deferred])
    # Let _Deployed() to check result and switching config and flag.
    deferred.addBoth(lambda result: _Deployed(result, deploying_config))
    deferred.addErrback(lambda failure: _Rollback(failure,
                                                  stopping_services,
                                                  starting_services))
    return deferred

  def StartServices(self, service_names):
    """Starts services.

    Args:
      service_names: List of service names to start.

    Returns:
      Deferred object that relays success or failure state of starting
      services.
    """
    deferreds = []
    umpire_config = AttrDict(self.env.config)
    for name in service_names:
      service = GetServiceInstance(name)
      processes = service.CreateProcesses(umpire_config, self.env)
      deferreds.append(service.Start(processes))
    return ConcentrateDeferreds(deferreds)

  def StopServices(self, service_names):
    """Stops services.

    Args:
      service_names: List of service names to stop.

    Returns:
      Deferred object that relays success or failure state of stopping
      services.
    """
    return ConcentrateDeferreds(
        [GetServiceInstance(name).Stop() for name in service_names])

  def AddMethodForDUT(self, dut_rpc_object):
    """Adds DUT RPC object to Umpire Daemon.

    Args:
      dut_rpc_object: The object that provides DUT RPC handlers.
    """
    self.methods_for_dut.append(dut_rpc_object)

  def AddMethodForCLI(self, cli_rpc_object):
    """Adds CLI RPC object to Umpire Daemon.

    Args:
      cli_rpc_object: The object that provides CLI RPC handlers.
    """
    self.methods_for_cli.append(cli_rpc_object)

  def AddWebApp(self, path_info, application):
    """Adds WSGI web application object.

    Args:
      application: Callable object that accepts WSGI environ and start_response.
    """
    self.web_applications[path_info] = application
