#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import jsonrpclib
import logging
import socket
import threading

import factory_common  # pylint: disable=W0611
from cros.factory.goofy.discoverer import DUTDiscoverer
from cros.factory.goofy.discoverer import HostDiscoverer
from cros.factory.test import utils
from cros.factory.test.network import GetAllIPs
from cros.factory.utils.jsonrpc_utils import JSONRPCServer
from cros.factory.utils.jsonrpc_utils import TimeoutJSONRPCTransport
from cros.factory.utils.net_utils import GetEthernetInterfaces
from cros.factory.utils.net_utils import GetEthernetIp


# Standard RPC ports.  These may be replaced by unit tests.
HOST_LINK_RPC_PORT = 4020
DUT_LINK_RPC_PORT = 4021


class LinkDownError(Exception):
  """The exception raised on RPC calls when the link is down."""
  pass

class HostLinkManager(object):
  """The link manager that runs on the DUT to maintain the link to the host."""
  def __init__(self,
               check_interval=5,
               methods=None,
               handshake_timeout=0.3,
               rpc_timeout=1):
    self._check_interval = check_interval
    self._handshake_timeout = handshake_timeout
    self._rpc_timeout = rpc_timeout
    self._methods = methods or {}
    self._methods.update({'Announce': self._HostAnnounce})
    self._host_connected = False
    self._host_ip = None
    self._host_proxy = None
    self._host_announcement = None
    self._discoverer = HostDiscoverer()
    self._kick_event = threading.Event()
    self._abort_event = threading.Event()
    self._server = JSONRPCServer(port=DUT_LINK_RPC_PORT, methods=self._methods)
    self._server.Start()
    self._thread = threading.Thread(target=self.MonitorLink)
    self._thread.start()

  def __getattr__(self, name):
    """A wrapper that proxies the RPC calls to the real server proxy."""
    if not self._host_connected:
      raise LinkDownError()
    try:
      return self._host_proxy.__getattr__(name)
    except AttributeError:
      # _host_proxy is None. Link is probably down.
      raise LinkDownError()

  def Stop(self):
    """Stops and destroys the link manager."""
    self._server.Destroy()
    self._abort_event.set()
    self._kick_event.set() # Kick the thread
    self._thread.join()

  def HostIsAlive(self):
    """Pings the host."""
    if not self._host_connected:
      return False
    try:
      return self._host_proxy.IsAlive()
    except (socket.error, socket.timeout, AttributeError):
      return False

  def _HostAnnounce(self, my_ip, host_ips):
    self._host_announcement = (my_ip, host_ips)
    self._kick_event.set()

  def _HandleHostAnnouncement(self):
    my_ip, host_ips = self._host_announcement
    self._host_announcement = None
    for host_ip in host_ips:
      self._MakeHostConnection(my_ip, host_ip)
      if self._host_connected:
        return

  def _MakeTimeoutServerProxy(self, host_ip, timeout):
    return jsonrpclib.Server('http://%s:%d/' % (host_ip, HOST_LINK_RPC_PORT),
                             transport=TimeoutJSONRPCTransport(timeout))

  def _MakeHostConnection(self, my_ip, host_ip):
    """Attempts to connect the the host.

    Args:
      my_ip: The IP address of this DUT received from the host; None to guess.
      host_ip: The IP address of the host.
    """
    if self._host_connected and self._host_ip == host_ip:
      return
    try:
      logging.info("Attempting to connect to host %s", host_ip)
      self._host_proxy = self._MakeTimeoutServerProxy(host_ip,
                                                      self._handshake_timeout)
      self._host_ip = host_ip
      self._host_proxy.IsAlive()

      # Host is alive. Let's register!
      logging.info("Registering to host %s", host_ip)
      if not my_ip:
        if utils.in_chroot():
          my_ip = '127.0.0.1'
        else:
          my_ip = map(GetEthernetIp, GetEthernetInterfaces())
          my_ip = [x for x in my_ip if x != '127.0.0.1']
        logging.info("Trying available IP addresses %s", my_ip)
      elif type(my_ip) != list:
        my_ip = [my_ip]

      for ip in my_ip:
        logging.info("Trying IP address %s", ip)
        self._host_proxy.Register(ip)

        # Make sure the host sees us
        logging.info("Registered. Checking connection.")
        if not self._host_proxy.ConnectionGood():
          logging.info("Registration failed.")
          continue
        self._host_connected = True
        logging.info("Connected to host %s", host_ip)
        # Now that we are connected, use a longer timeout for the proxy
        self._host_proxy = self._MakeTimeoutServerProxy(host_ip,
                                                        self._rpc_timeout)
        return
      self._host_ip = None
      self._host_proxy = None
    except (socket.error, socket.timeout):
      self._host_ip = None
      self._host_proxy = None
      logging.info("Connection failed.")

  def CheckHostConnection(self):
    """Check the connection to the host.

    If the connection is down, put ourselves into disconnected state and attempt
    to establish the connection again.
    """
    if self._host_connected:
      if self.HostIsAlive():
        return # everything's fine
      else:
        logging.info("Lost connection to host %s", self._host_ip)
        self._host_connected = False
        self._host_ip = None
        self._host_proxy = None

    ips = self._discoverer.Discover()
    if ips is None:
      return
    if type(ips) != list:
      ips = [ips]
    for ip in ips:
      self._MakeHostConnection(None, ip)
      if self._host_connected:
        return

  def MonitorLink(self):
    while True:
      self._kick_event.wait(self._check_interval)
      self._kick_event.clear()
      if self._abort_event.isSet():
        return
      if self._host_announcement:
        self._HandleHostAnnouncement()
      else:
        self.CheckHostConnection()


class DUTLinkManager(object):
  """The link manager that runs on the host to maintain the link to the DUT."""
  def __init__(self,
               check_interval=5,
               methods=None,
               rpc_timeout=1):
    self._check_interval = check_interval
    self._rpc_timeout = rpc_timeout
    self._methods = methods or {}
    self._methods.update({'Register': self._DUTRegister,
                          'ConnectionGood': self.DUTIsAlive})
    self._dut_proxy = None
    self._dut_ip = None
    self._dut_connected = False
    self._lock = threading.Lock()
    self._kick_event = threading.Event()
    self._abort_event = threading.Event()
    self._discoverer = DUTDiscoverer()
    self._server = JSONRPCServer(port=HOST_LINK_RPC_PORT,
                                 methods=self._methods)
    self._server.Start()
    self._thread = threading.Thread(target=self.MonitorLink)
    self._thread.start()

  def __getattr__(self, name):
    """A wrapper that proxies the RPC calls to the real server proxy."""
    if not self._dut_connected:
      raise LinkDownError()
    try:
      return self._dut_proxy.__getattr__(name)
    except AttributeError:
      # _dut_proxy is None. Link is probably down.
      raise LinkDownError()

  def Stop(self):
    """Stops and destroys the link manager."""
    self._server.Destroy()
    self._abort_event.set()
    self._kick_event.set()
    self._thread.join()

  def _MakeTimeoutServerProxy(self, dut_ip, timeout):
    return jsonrpclib.Server('http://%s:%d/' % (dut_ip, DUT_LINK_RPC_PORT),
                             transport=TimeoutJSONRPCTransport(timeout))

  def _DUTRegister(self, dut_ip):
    with self._lock:
      try:
        self._dut_ip = dut_ip
        self._dut_proxy = self._MakeTimeoutServerProxy(dut_ip,
                                                       self._rpc_timeout)
        self._dut_proxy.IsAlive()
        self._dut_connected = True
        logging.info("DUT %s registered", dut_ip)
      except (socket.error, socket.timeout):
        self._dut_ip = None
        self._dut_proxy = None

  def DUTIsAlive(self):
    """Pings the DUT."""
    if not self._dut_connected:
      return False
    try:
      self._dut_proxy.IsAlive()
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
            return # All good!
          else:
            logging.info("Disconnected from DUT %s", self._dut_ip)
            self._dut_connected = False
            self._dut_ip = None
            self._dut_proxy = None

        ips = self._discoverer.Discover()
        if ips is None:
          return
        if type(ips) != list:
          ips = [ips]
        for ip in ips:
          try:
            # We don't get response from the DUT for announcement, so let's
            # keep the timeout short.
            proxy = self._MakeTimeoutServerProxy(ip, timeout=0.05)
            my_ips = GetAllIPs()
            logging.info("Announcing to DUT %s: host ip is %s", ip, my_ips)
            proxy.Announce(ip, my_ips)
          except (socket.error, socket.timeout):
            pass
      finally:
        self._lock.release()

  def Kick(self):
    """Kick the link manager to check the connection or announce ourselves."""
    self._kick_event.set()

  def MonitorLink(self):
    while True:
      self.CheckDUTConnection()
      self._kick_event.wait(self._check_interval)
      self._kick_event.clear()
      if self._abort_event.isSet():
        return
