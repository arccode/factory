# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Python twisted's module creates definition dynamically,
# pylint: disable=no-member

"""Umpire daemon.

Umpire: the unified factory server. Umpired is a daemon that launches factory
server applications, like shop floor proxy, log analyzer and testing program
updater.
"""

import logging
import signal

from twisted.internet import defer
from twisted.internet import reactor
from twisted.python import failure as twisted_failure
from twisted.web import server
from twisted.web import wsgi
from twisted.web import xmlrpc

from cros.factory.umpire import common
from cros.factory.umpire.server.service import umpire_service
from cros.factory.umpire.server import utils
from cros.factory.umpire.server.web import wsgi as umpire_wsgi
from cros.factory.umpire.server.web import xmlrpc as umpire_xmlrpc
from cros.factory.utils import net_utils
from cros.factory.utils import type_utils


class UmpireDaemon:
  """Umpire daemon class.

  Umpire daemon builds XMLRPC sites that serves command line utility and
  DUT requests related to Umpire configuration. It also builds web application
  sites that provides interfaces for simple HTTP GET.

  The daemon also has functional interfaces to restart service processes on
  configuration change.

  Examples:
    Restart service process after deployed new configuration:
        daemon.Deploy()

    Stop Umpire daemon:
        daemon.Stop()

  Properties:
    env: UmpireEnv object.
    deployed_config: latest Umpire configuration type_utils.AttrDict.
    methods_for_cli: list of command objects for Umpire CLI (Command Line
                     Interface) to access.
    methods_for_dut: list of RPC objects for DUT (Device Under Test) to access.
    web_applications: web application dispatcher that maps request path info
                      to application object.
    twisted_ports: bound twisted ports.
    deploying: daemon is deploying a config and not finished yet.
    stopping: daemon is stopping.
  """

  def __init__(self, env):
    self.env = env
    self.deployed_config = None
    self.methods_for_cli = []
    self.methods_for_dut = []
    self.web_applications = umpire_wsgi.WebAppDispatcher()
    # Twisted port object is TCP server port, listening for connections.
    # port.stopListening() will be called on reactor.stop()
    # The ports are stored here for unittests to stopListening() them
    # between tests.
    self.twisted_ports = []
    self.deploying = False
    self.stopping = False

  def _HandleStopSignal(self, sig, frame):
    """Handles signals that stops event loop.

    Umpire daemon prevents twisted event loop to handle SIGINT and
    SIGTERM. This signal handler stops the daemon and Twisted event
    loop nicely.
    """
    del frame  # Unused.
    logging.info('Received signal %d', sig)
    if self.stopping:
      reactor.callLater(3, reactor.stop)
      return

    logging.info('Stop umpired...')
    self.Stop()

  def Stop(self):
    """Stops subprocesses and quits daemon loop."""
    self.stopping = True
    service_names = umpire_service.GetAllServiceNames()
    deferred = self.StopServices(service_names)
    deferred.addBoth(lambda _: reactor.stop())
    return deferred

  def OnStart(self):
    """Daemon start handler."""
    def HandleStartError(failure):
      logging.debug('Failed to start Umpire daemon: %s', failure)
      self.Stop()
      # Reactor is stopping, no need to propagate this failure.
      return True

    # Install signal handler.
    signal.signal(signal.SIGTERM, self._HandleStopSignal)
    signal.signal(signal.SIGINT, self._HandleStopSignal)

    # Deploy the loaded configuration.
    d = self.Deploy()
    d.addErrback(HandleStartError)

  def BuildWebAppSite(self, interface=net_utils.LOCALHOST):
    """Builds web application resource and site."""
    if not self.web_applications:
      raise common.UmpireError('Can not build web site without web application')
    # Build wsgi site.
    web_resource = wsgi.WSGIResource(reactor, reactor.getThreadPool(),
                                     self.web_applications)
    web_site = server.Site(web_resource)
    # Listen to webapp server port.
    self.twisted_ports.append(reactor.listenTCP(self.env.umpire_webapp_port,
                                                web_site, interface=interface))

  def BuildRPCSite(self, port, rpc_objects, interface=net_utils.LOCALHOST):
    """Builds RPC resource and site.

    Args:
      port: the server port number to listen.
      rpc_objects: list of UmpireRPC objects.
      interface: network interface to bind, can be '0.0.0.0'.
    """
    if not rpc_objects:
      raise common.UmpireError('Can not build RPC site without rpc object')
    # Build command rpc site.
    rpc_resource = umpire_xmlrpc.XMLRPCContainer()
    for rpc_object in rpc_objects:
      rpc_resource.AddHandler(rpc_object)
    xmlrpc.addIntrospection(rpc_resource)
    rpc_site = server.Site(rpc_resource)
    # Listen to rpc server port.
    self.twisted_ports.append(reactor.listenTCP(port, rpc_site,
                                                interface=interface))

  def Run(self):
    """Starts the daemon and event loop."""
    self.BuildWebAppSite()

    self.BuildRPCSite(self.env.umpire_cli_port, self.methods_for_cli, '0.0.0.0')
    self.BuildRPCSite(self.env.umpire_rpc_port, self.methods_for_dut)

    # Start services.
    reactor.callWhenRunning(self.OnStart)
    # And start reactor loop.
    reactor.run()

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
      for name, service_config in config.services.items():
        if getattr(service_config, 'active', True):
          yield name

    def _Deployed(result, deploying_config):
      """Switches config and flag on deploying finished."""
      # Switch deployed_config to new one.
      if not isinstance(result, twisted_failure.Failure):
        self.deployed_config = deploying_config
      # Clear deploying state.
      self.deploying = False
      return result

    def _Rollback(failure, stopping_services, starting_services):
      """Stops starting_services and starts stopping_services."""
      def _HandleRollbackError(failure):
        """Ignores rollback error."""
        exc_info = (failure.type, failure.value, failure.tb)
        logging.error('Failed rolling back configuration',
                      exc_info=exc_info)
        return True

      deferred = self.StopServices(starting_services)
      deferred.addCallback(lambda _: self.StartServices(stopping_services))
      deferred.addErrback(_HandleRollbackError)
      # Ignore result for rollback, and return the deploy failure.
      deferred.addBoth(lambda _: failure)
      return deferred

    if self.deploying:
      return defer.fail(common.UmpireError('Another deployment in progress'))

    # Switch to deploying state, this flag will be cleared in callback/errback.
    self.deploying = True
    stopping_services = None
    starting_services = None
    # Record both old and new configuration.
    current_config = self.deployed_config
    deploying_config = type_utils.AttrDict(self.env.config)
    current_services = set(_GetActiveServiceNames(current_config)
                           if current_config else [])
    deploying_services = set(_GetActiveServiceNames(deploying_config))
    # Calculate services to stop
    if restart_all:
      stopping_services = current_services
    else:
      stopping_services = current_services - deploying_services

    # umpire_service would handle the case when the service processes are not
    # changed.
    starting_services = deploying_services

    # Stop unused services and start new services.
    deferred = self.StopServices(stopping_services)
    deferred.addCallback(lambda _: self.StartServices(starting_services))

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
    umpire_config = type_utils.AttrDict(self.env.config)
    for name in service_names:
      service = umpire_service.GetServiceInstance(name)
      processes = service.CreateProcesses(umpire_config, self.env)
      deferreds.append(service.Start(processes))
    return utils.ConcentrateDeferreds(deferreds)

  def StopServices(self, service_names):
    """Stops services.

    Args:
      service_names: List of service names to stop.

    Returns:
      Deferred object that relays success or failure state of stopping
      services.
    """
    return utils.ConcentrateDeferreds(
        [umpire_service.GetServiceInstance(name).Stop()
         for name in service_names])

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
