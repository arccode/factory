#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import argparse
import jsonrpclib
import logging
import os
import signal
import socket
import threading
import time

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import dhcp_manager
from cros.factory.system import service_manager
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.utils.jsonrpc_utils import JSONRPCServer
from cros.factory.utils.jsonrpc_utils import TimeoutJSONRPCTransport
from cros.factory.utils import net_utils
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils import sync_utils


# Standard RPC ports.  These may be replaced by unit tests.
PRESENTER_LINK_RPC_PORT = 4020
DUT_LINK_RPC_PORT = 4021
PRESENTER_PING_PORT = 4022
DUT_PING_PORT = 4023


def MakeTimeoutServerProxy(ip, port, timeout):
  return jsonrpclib.Server('http://%s:%d/' %
                           (ip, port),
                           transport=TimeoutJSONRPCTransport(timeout))


class PingServer(object):
  """Runs a ping server in a separate process."""

  def __init__(self, port):
    self._process = Spawn(['python', __file__, '--port', str(port)])

  def Stop(self):
    self._process.terminate()


class LinkDownError(Exception):
  """The exception raised on RPC calls when the link is down."""
  pass


class PresenterLinkManager(object):
  """The manager that runs on the DUT to maintain a link to the presenter."""

  def __init__(self,
               check_interval=5,
               methods=None,
               handshake_timeout=0.3,
               rpc_timeout=1,
               connect_hook=None,
               disconnect_hook=None,
               standalone=False):
    self._check_interval = check_interval
    self._handshake_timeout = handshake_timeout
    self._rpc_timeout = rpc_timeout
    self._connect_hook = connect_hook
    self._disconnect_hook = disconnect_hook
    self._standalone = standalone
    self._suspend_deadline = None
    self._methods = methods or {}
    self._methods.update({'Announce': self._PresenterAnnounce,
                          'IsConnected': lambda: self._presenter_connected})
    self._reported_failure = set()
    self._presenter_connected = False
    self._presenter_ip = None
    self._presenter_proxy = None
    self._presenter_ping_proxy = None
    self._presenter_announcement = None
    self._kick_event = threading.Event()
    self._abort_event = threading.Event()
    self._server = JSONRPCServer(port=DUT_LINK_RPC_PORT, methods=self._methods)
    self._server.Start()
    self._ping_server = None
    self.StartPingServer()
    self._thread = threading.Thread(target=self.MonitorLink)
    self._thread.start()

  def __getattr__(self, name):
    """A wrapper that proxies the RPC calls to the real server proxy."""
    if not self._presenter_connected:
      raise LinkDownError()
    try:
      return self._presenter_proxy.__getattr__(name)
    except AttributeError:
      # _presenter_proxy is None. Link is probably down.
      raise LinkDownError()

  def StartPingServer(self):
    """Starts ping server."""
    if not self._ping_server:
      self._ping_server = PingServer(DUT_PING_PORT)

  def StopPingServer(self):
    """Stops and discard ping server."""
    if self._ping_server:
      self._ping_server.Stop()
      self._ping_server = None

  def Stop(self):
    """Stops and destroys the link manager."""
    self._server.Destroy()
    self._abort_event.set()
    self._kick_event.set()  # Kick the thread
    self._thread.join()
    self.StopPingServer()

  def SuspendMonitoring(self, interval_sec):
    """Suspend monitoring of connection for a given period.

    Args:
      interval_sec: Number of seconds to suspend.
    """
    self._suspend_deadline = time.time() + interval_sec
    self._presenter_proxy.SuspendMonitoring(interval_sec)

  def ResumeMonitoring(self):
    """Immediately resume suspended monitoring of connection."""
    self._suspend_deadline = None
    self.Kick()
    self._presenter_proxy.ResumeMonitoring()

  def PresenterIsAlive(self):
    """Pings the presenter."""
    if not self._presenter_connected:
      return False
    try:
      return self._presenter_ping_proxy.IsAlive()
    except (socket.error, socket.timeout, AttributeError):
      return False

  def _PresenterAnnounce(self, my_ip, presenter_ip):
    self._presenter_announcement = (my_ip, presenter_ip)
    self._kick_event.set()

  def _HandlePresenterAnnouncement(self):
    my_ip, presenter_ip = self._presenter_announcement # pylint: disable=W0633
    self._presenter_announcement = None
    self._MakePresenterConnection(my_ip, presenter_ip)
    if self._presenter_connected:
      return

  def _MakePresenterConnection(self, my_ip, presenter_ip):
    """Attempts to connect the the presenter.

    Args:
      my_ip: The IP address of this DUT received from the presenter.
      presenter_ip: The IP address of the presenter.
    """
    log = (logging.info if presenter_ip not in self._reported_failure else
           lambda *args: None)

    try:
      log('Attempting to connect to presenter %s', presenter_ip)
      self._presenter_proxy = MakeTimeoutServerProxy(presenter_ip,
                                                     PRESENTER_LINK_RPC_PORT,
                                                     self._handshake_timeout)
      self._presenter_ping_proxy = MakeTimeoutServerProxy(
          presenter_ip,
          PRESENTER_PING_PORT,
          self._handshake_timeout)
      self._presenter_ip = presenter_ip
      self._presenter_proxy.IsAlive()
      self._presenter_ping_proxy.IsAlive()

      # Presenter is alive. Let's register!
      log('Registering to presenter %s', presenter_ip)
      try:
        log('Trying IP address %s', my_ip)
        self._presenter_proxy.Register(my_ip)

        # Make sure the presenter sees us
        log('Registered. Checking connection.')
        if self._presenter_proxy.ConnectionGood():
          self._presenter_connected = True
          logging.info('Connected to presenter %s', presenter_ip)
          # Now that we are connected, use a longer timeout for the proxy
          self._presenter_proxy = MakeTimeoutServerProxy(
              presenter_ip, PRESENTER_LINK_RPC_PORT, self._rpc_timeout)
          self._presenter_ping_proxy = MakeTimeoutServerProxy(
              presenter_ip, PRESENTER_PING_PORT, self._rpc_timeout)
          if presenter_ip in self._reported_failure:
            self._reported_failure.remove(presenter_ip)
          if self._connect_hook:
            self._connect_hook(presenter_ip)
          return
      except:  # pylint: disable=W0702
        logging.exception('Failed to register DUT as %s', my_ip)

    except (socket.error, socket.timeout):
      pass

    # If we are here, we failed to make connection. Clean up.
    self._presenter_connected = False
    self._presenter_ip = None
    self._presenter_proxy = None
    self._presenter_ping_proxy = None
    self._reported_failure.add(presenter_ip)
    log('Connection failed.')

  def CheckPresenterConnection(self):
    """Check the connection to the presenter.

    If the connection is down, put ourselves into disconnected state and attempt
    to establish the connection again.
    """
    if self._presenter_connected:
      if self.PresenterIsAlive():
        return  # everything's fine
      else:
        logging.info('Lost connection to presenter %s', self._presenter_ip)
        self._presenter_connected = False
        self._presenter_ip = None
        self._presenter_proxy = None
        if self._disconnect_hook:
          self._disconnect_hook()

  def MonitorLink(self):
    while True:
      self._kick_event.wait(self._check_interval)
      self._kick_event.clear()
      if self._abort_event.isSet():
        return
      if self._suspend_deadline:
        if time.time() > self._suspend_deadline:
          self._suspend_deadline = None
      else:
        if self._presenter_announcement:
          self._HandlePresenterAnnouncement()
        else:
          self.CheckPresenterConnection()


class DUTLinkManager(object):
  """The manager that runs on the presenter to maintain the link to the DUT."""

  def __init__(self,
               check_interval=5,
               methods=None,
               rpc_timeout=1,
               connect_hook=None,
               disconnect_hook=None,
               standalone=False):
    self._check_interval = check_interval
    self._rpc_timeout = rpc_timeout
    self._connect_hook = connect_hook
    self._disconnect_hook = disconnect_hook
    self._standalone = standalone
    self._suspend_deadline = None
    self._methods = methods or {}
    self._methods.update({'Register': self._DUTRegister,
                          'ConnectionGood': self.DUTIsAlive,
                          'SuspendMonitoring': self.SuspendMonitoring,
                          'ResumeMonitoring': self.ResumeMonitoring})
    self._reported_announcement = set()
    self._dut_proxy = None
    self._dut_ping_proxy = None
    self._dut_ip = None
    self._dut_connected = False
    self._lock = threading.Lock()
    self._kick_event = threading.Event()
    self._abort_event = threading.Event()
    self._server = JSONRPCServer(port=PRESENTER_LINK_RPC_PORT,
                                 methods=self._methods)
    self._ping_server = PingServer(PRESENTER_PING_PORT)
    self._thread = threading.Thread(target=self.MonitorLink)

    self._dhcp_servers = []
    self._dhcp_event_ip = None

  def __getattr__(self, name):
    """A wrapper that proxies the RPC calls to the real server proxy."""
    if not self._dut_connected:
      raise LinkDownError()
    try:
      return self._dut_proxy.__getattr__(name)
    except AttributeError:
      # _dut_proxy is None. Link is probably down.
      raise LinkDownError()

  def OnDHCPEvent(self, ip):
    """Call backs on 'add' or 'old' events from DHCP server."""
    logging.info('DHCP event: %s', ip)
    # Save the IP address and try to talk to it. If it fails, the device may
    # be booting and is not ready for connection. Retry later.
    self._dhcp_event_ip = ip
    self.AnnounceToLastDUT()

  def AnnounceToLastDUT(self):
    """Make announcement to the last DHCP event client."""
    if not self._dhcp_event_ip:
      return
    if (self._dut_connected and self._dut_ip == self._dhcp_event_ip and
        self._dut_proxy.IsConnected()):
      return
    proxy = MakeTimeoutServerProxy(self._dhcp_event_ip, DUT_LINK_RPC_PORT,
                                   timeout=0.05)
    dhcp_subnet = self._dhcp_event_ip.rsplit('.', 1)[0]
    my_ip = dhcp_subnet + '.1'
    try:
      proxy.Announce(self._dhcp_event_ip, my_ip)
    except: # pylint: disable=W0702
      pass

  def _GetDHCPInterfaceBlacklist(self):
    """Returns the blacklist of DHCP interfaces.

    This parses board/dhcp_interface_blacklist for a list of network
    interfaces on which we don't want to run DHCP.
    """
    blacklist_file = os.path.join(factory.FACTORY_PATH, 'board',
                                  'dhcp_interface_blacklist')
    if os.path.exists(blacklist_file):
      with open(blacklist_file) as f:
        return [line.strip() for line in f.readlines()]
    return []

  def _StartDHCPServers(self):
    dhcp_manager.DHCPManager.CleanupStaleInstance()
    if utils.in_cros_device():
      # Wait for shill to start
      sync_utils.WaitFor(lambda: service_manager.GetServiceStatus('shill') ==
                         service_manager.Status.START, 15)
      # Give shill some time to run DHCP
      time.sleep(3)
    # OK, shill has done its job now. Let's see what interfaces are not managed.
    intf_blacklist = self._GetDHCPInterfaceBlacklist()
    intfs = [intf for intf in net_utils.GetUnmanagedEthernetInterfaces()
             if intf not in intf_blacklist]

    for intf in intfs:
      network_cidr = net_utils.GetUnusedIPV4RangeCIDR()
      # DHCP server IP assignment:
      # my_ip: the first available IP. e.g.: 192.168.0.1
      # ip_start: the second available IP. e.g.: 192.168.0.2
      # ip_end: the third from the last IP. since .255 is the broadcast address
      # and .254 is usually used by gateway, skip it to avoid unexpected
      # problems.
      dhcp_server = dhcp_manager.DHCPManager(
          interface=intf,
          my_ip=str(network_cidr.SelectIP(1)),
          netmask=str(network_cidr.Netmask()),
          ip_start=str(network_cidr.SelectIP(2)),
          ip_end=str(network_cidr.SelectIP(-3)),
          lease_time=3600,
          on_add=self.OnDHCPEvent,
          on_old=self.OnDHCPEvent)
      dhcp_server.StartDHCP()
      self._dhcp_servers.append(dhcp_server)

    # Start NAT service
    managed_intfs = [x for x in net_utils.GetEthernetInterfaces()
                     if x not in intfs]
    if not managed_intfs:
      return
    nat_out_interface = managed_intfs[0]
    net_utils.StartNATService(intfs, nat_out_interface)

  def Start(self):
    """Starts services."""
    self._server.Start()
    self._thread.start()
    if self._standalone:
      self._dhcp_event_ip = '127.0.0.1'
    else:
      self._StartDHCPServers()

  def Stop(self):
    """Stops and destroys the link manager."""
    for dhcp_server in self._dhcp_servers:
      dhcp_server.StopDHCP()
    self._server.Destroy()
    self._abort_event.set()
    self._kick_event.set()
    self._thread.join()
    self._ping_server.Stop()

  def SuspendMonitoring(self, interval_sec):
    """Suspend monitoring of connection for a given period.

    Args:
      interval_sec: Number of seconds to suspend.
    """
    self._suspend_deadline = time.time() + interval_sec

  def ResumeMonitoring(self):
    """Immediately resume suspended monitoring of connection."""
    self._suspend_deadline = None
    self.Kick()

  def _DUTRegister(self, dut_ip):
    with self._lock:
      try:
        self._dut_ip = dut_ip
        self._dut_proxy = MakeTimeoutServerProxy(dut_ip,
                                                 DUT_LINK_RPC_PORT,
                                                 self._rpc_timeout)
        self._dut_ping_proxy = MakeTimeoutServerProxy(dut_ip,
                                                      DUT_PING_PORT,
                                                      self._rpc_timeout)
        self._dut_proxy.IsAlive()
        self._dut_ping_proxy.IsAlive()
        self._dut_connected = True
        logging.info('DUT %s registered', dut_ip)
        self._reported_announcement.clear()
        if self._connect_hook:
          self._connect_hook(dut_ip)
      except (socket.error, socket.timeout):
        self._dut_ip = None
        self._dut_proxy = None

  def DUTIsAlive(self):
    """Pings the DUT."""
    if not self._dut_connected:
      return False
    try:
      self._dut_ping_proxy.IsAlive()
      return True
    except (socket.error, socket.timeout, AttributeError):
      return False

  def CheckDUTConnection(self):
    """Check the connection to the DUT.

    If the connection is down, put ourselves into disconnected state and start
    announcing ourselves to potential DUTs again.
    """
    if self._lock.acquire(False):
      try:
        if self._dut_connected:
          if self.DUTIsAlive():
            return  # All good!
          else:
            logging.info('Disconnected from DUT %s', self._dut_ip)
            self._dut_connected = False
            self._dut_ip = None
            self._dut_proxy = None
            self._dut_ping_proxy = None
            if self._disconnect_hook:
              self._disconnect_hook()
        else:
          self.AnnounceToLastDUT()
      finally:
        self._lock.release()

  def Kick(self):
    """Kick the link manager to check the connection or announce ourselves."""
    self._kick_event.set()

  def MonitorLink(self):
    while True:
      if self._suspend_deadline:
        if time.time() > self._suspend_deadline:
          self._suspend_deadline = None
      else:
        self.CheckDUTConnection()
      self._kick_event.wait(self._check_interval)
      self._kick_event.clear()
      if self._abort_event.isSet():
        return

if __name__ == '__main__':
  # If this script runs by itself, it serves as a ping server, which replies
  # to JSON RPC pings.
  parser = argparse.ArgumentParser(description='Run ping server')
  parser.add_argument('--port', type=int,
                      help='The port to expect ping')
  args = parser.parse_args()

  assert args.port

  def _SIGTERMHandler(unused_signum, unused_frame):
    raise Exception('SIGTERM received')
  signal.signal(signal.SIGTERM, _SIGTERMHandler)

  try:
    server = JSONRPCServer(port=args.port)
    server.Start()
    # Serve forever until we're terminated
    while True:
      time.sleep(1000)
  except KeyboardInterrupt:
    pass  # Server is destroyed in finally clause
  finally:
    server.Destroy()
