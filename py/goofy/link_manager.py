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
from cros.factory.test import network
from cros.factory.test.env import paths
from cros.factory.test.utils import dhcp_utils
from cros.factory.utils.jsonrpc_utils import JSONRPCServer
from cros.factory.utils.jsonrpc_utils import TimeoutJSONRPCTransport
from cros.factory.utils.process_utils import Spawn


# Standard RPC ports.  These may be replaced by unit tests.
PRESENTER_LINK_RPC_PORT = 4020
DUT_LINK_RPC_PORT = 4021
PRESENTER_PING_PORT = 4022
DUT_PING_PORT = 4023
LOCALHOST = '127.0.0.1'
STANDALONE = 'standalone'


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
    self._my_ip = None
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
    self._presenter_proxy.SuspendMonitoring(interval_sec, self._my_ip)

  def ResumeMonitoring(self):
    """Immediately resume suspended monitoring of connection."""
    self._suspend_deadline = None
    self.Kick()
    self._presenter_proxy.ResumeMonitoring(self._my_ip)

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
      self._my_ip = my_ip
      self._presenter_proxy.IsAlive()
      self._presenter_ping_proxy.IsAlive()

      # Presenter is alive. Let's register!
      log('Registering to presenter %s', presenter_ip)
      try:
        log('Trying IP address %s', my_ip)
        self._presenter_proxy.Register(my_ip)

        # Make sure the presenter sees us
        log('Registered. Checking connection.')
        if self._presenter_proxy.ConnectionGood(my_ip):
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
    self._my_ip = None
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
        self._my_ip = None
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

  class DUT(object):
    """Maintain the DUTs info and provide the necessary functions"""
    def __init__(self, ip, dongle_mac_address):
      self._suspend_deadline = None
      self._dut_ip = ip
      self._dut_proxy = None
      self._dut_ping_proxy = None
      self._dut_dongle_mac_address = dongle_mac_address

    def Reset(self):
      """Reset after a DUT is disconnected. If self._dut_ip is setted to None,
      running factory_restart will fail when calling self.ProxyAlive().
      """
      self._suspend_deadline = None
      self._dut_proxy = None
      self._dut_ping_proxy = None

    def GetDongleMacAddress(self):
      return self._dut_dongle_mac_address

    def GetSuspendDeadline(self):
      return self._suspend_deadline

    def GetProxy(self):
      return self._dut_proxy

    def SetSuspendDeadline(self, suspend_deadline):
      self._suspend_deadline = suspend_deadline

    def SetProxy(self, rpc_timeout):
      self._dut_proxy = MakeTimeoutServerProxy(self._dut_ip, DUT_LINK_RPC_PORT,
                                               rpc_timeout)

    def SetPingProxy(self, rpc_timeout):
      self._dut_ping_proxy = MakeTimeoutServerProxy(self._dut_ip, DUT_PING_PORT,
                                                    rpc_timeout)

    def ProxyConnected(self):
      return self._dut_proxy.IsConnected()

    def ProxyAlive(self):
      self._dut_proxy.IsAlive()

    def Ping(self):
      self._dut_ping_proxy.IsAlive()

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
    self._methods = methods or {}
    self._methods.update({'Register': self._DUTRegister,
                          'ConnectionGood': self.DUTIsAlive,
                          'SuspendMonitoring': self.SuspendMonitoring,
                          'ResumeMonitoring': self.ResumeMonitoring})
    self._reported_announcement = set()
    self._dut_ips = []
    self._duts = {}
    self._lock = threading.Lock()
    self._kick_event = threading.Event()
    self._abort_event = threading.Event()
    self._server = JSONRPCServer(port=PRESENTER_LINK_RPC_PORT,
                                 methods=self._methods)
    self._ping_server = PingServer(PRESENTER_PING_PORT)
    self._thread = threading.Thread(target=self.MonitorLink)

    self._dhcp_server = None
    self._dhcp_event_ip = None
    self._relay_process = None

  def __getattr__(self, name):
    """A wrapper that proxies the RPC calls to the real server proxy."""
    if not self._dut_ips:
      raise LinkDownError()

    dut_ip = self._dut_ips[-1]
    try:
      dut_proxy = self._duts[dut_ip].GetProxy()
      return dut_proxy.__getattr__(name)
    except AttributeError:
      # _dut_proxies is None. Link is probably down.
      raise LinkDownError()

  def OnDHCPEvent(self, ip, dongle_mac_address):
    """Call backs on 'add' or 'old' events from DHCP server."""
    logging.info('DHCP event: %s', ip)
    # Save the IP address and try to talk to it. If it fails, the device may
    # be booting and is not ready for connection. Retry later.
    self._dhcp_event_ip = ip
    if ip not in self._duts:
      # calling OnDHCPEvent twice may set _dut_proxy and _dut_ping_proxy to None
      self._duts[ip] = self.DUT(ip, dongle_mac_address)
    self.AnnounceToLastDUT()

  def AnnounceToLastDUT(self):
    """Make announcement to the last DHCP event client."""
    if not self._dhcp_event_ip:
      return

    if self._dut_ips:
      dut_ip = self._dut_ips[-1]
      if (dut_ip == self._dhcp_event_ip and
          self._duts[dut_ip].ProxyConnected()):
        return
    proxy = MakeTimeoutServerProxy(self._dhcp_event_ip, DUT_LINK_RPC_PORT,
                                   timeout=0.05)
    dhcp_subnet = self._dhcp_event_ip.rsplit('.', 1)[0]
    my_ip = dhcp_subnet + '.1'
    try:
      proxy.Announce(self._dhcp_event_ip, my_ip)
    except: # pylint: disable=W0702
      pass

  def _StartDHCPServer(self):
    self._dhcp_server = dhcp_utils.StartDHCPManager(
        lease_time=3600,
        on_add=self.OnDHCPEvent,
        on_old=self.OnDHCPEvent)

  def _StartOverlordRelay(self):
    interface_blacklist = network.GetDHCPInterfaceBlacklist()
    interfaces = [interface
                  for interface in network.GetUnmanagedEthernetInterfaces()
                  if interface not in interface_blacklist]

    for interface in interfaces:
      path = os.path.join(paths.FACTORY_PATH, 'bin',
                          'relay_overlord_discovery_packet')
      self._relay_process = Spawn([path, interface], log=True)

  def _StopOverlordRelay(self):
    if self._relay_process is not None:
      self._relay_process.terminate()

  def Start(self):
    """Starts services."""
    self._server.Start()
    self._thread.start()
    if self._standalone:
      self._dhcp_event_ip = LOCALHOST
      self._duts[LOCALHOST] = self.DUT(LOCALHOST, STANDALONE)
    else:
      self._StartDHCPServer()
      self._StartOverlordRelay()

  def Stop(self):
    """Stops and destroys the link manager."""
    if self._dhcp_server:
      self._dhcp_server.StopDHCP()
    self._server.Destroy()
    self._abort_event.set()
    self._kick_event.set()
    self._thread.join()
    self._ping_server.Stop()
    self._StopOverlordRelay()

  def SuspendMonitoring(self, interval_sec, dut_ip):
    """Suspend monitoring of connection for a given period.

    Args:
      interval_sec: Number of seconds to suspend.
    """
    self._duts[dut_ip].SetSuspendDeadline(time.time() + interval_sec)

  def ResumeMonitoring(self, dut_ip):
    """Immediately resume suspended monitoring of connection."""
    self._duts[dut_ip].SetSuspendDeadline(None)
    self.Kick()

  def RemoveDUT(self, dut_ip):
    """If we delete self._duts[dut_ip] here,
    running factory_restart won't get the dongle mac address.
    """
    try:
      self._duts[dut_ip].Reset()
      self._dut_ips.remove(dut_ip)
    except ValueError:
      pass

  def _DUTRegister(self, dut_ip):
    with self._lock:
      try:
        dut = self._duts[dut_ip]
        dut.SetSuspendDeadline(None)
        dut.SetProxy(self._rpc_timeout)
        dut.SetPingProxy(self._rpc_timeout)
        dut.ProxyAlive()
        dut.Ping()

        logging.info('DUT %s registered', dut_ip)
        self._reported_announcement.clear()
        if self._connect_hook:
          self._connect_hook(dut_ip, self._duts[dut_ip].GetDongleMacAddress())

        if dut_ip not in self._dut_ips:
          self._dut_ips.append(dut_ip)
      except (socket.error, socket.timeout):
        self.RemoveDUT(dut_ip)

  def DUTIsAlive(self, dut_ip):
    """Pings the DUT."""
    try:
      self._duts[dut_ip].Ping()
      return True
    except (socket.error, socket.timeout, AttributeError, KeyError):
      return False

  def CheckDUTConnection(self, dut_ip):
    """Check the connection to the DUT.

    If the connection is down, put ourselves into disconnected state and start
    announcing ourselves to potential DUTs again.
    """
    if self._lock.acquire(False):
      try:
        if not self.DUTIsAlive(dut_ip):
          logging.info('Disconnected from DUT %s', dut_ip)
          self.RemoveDUT(dut_ip)
          if self._disconnect_hook:
            self._disconnect_hook(dut_ip)
      finally:
        self._lock.release()

  def Kick(self):
    """Kick the link manager to check the connection or announce ourselves."""
    self._kick_event.set()

  def MonitorLink(self):
    while True:
      if self._dut_ips:
        for dut_ip in self._dut_ips:
          suspend_deadline = self._duts[dut_ip].GetSuspendDeadline()
          if suspend_deadline:
            if time.time() > suspend_deadline:
              self._duts[dut_ip].SetSuspendDeadline(None)
          else:
            self.CheckDUTConnection(dut_ip)
      else:
        # If we are running in standalone mode, OnDHCPEvent is never triggered
        # and thus AnnouceToLastDUT will also never be called. If no DUT is
        # connected, we call AnnouceToLastDUT manually to try to connect to
        # localhost.
        self.AnnounceToLastDUT()
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
