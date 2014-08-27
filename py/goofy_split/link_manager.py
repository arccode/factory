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
import time

import factory_common  # pylint: disable=W0611
from cros.factory.goofy_split.discoverer import DUTDiscoverer
from cros.factory.goofy_split.discoverer import PresenterDiscoverer
from cros.factory.test import utils
from cros.factory.test.network import GetAllIPs
from cros.factory.utils.jsonrpc_utils import JSONRPCServer
from cros.factory.utils.jsonrpc_utils import TimeoutJSONRPCTransport
from cros.factory.utils.net_utils import GetEthernetInterfaces
from cros.factory.utils.net_utils import GetEthernetIp


# Standard RPC ports.  These may be replaced by unit tests.
PRESENTER_LINK_RPC_PORT = 4020
DUT_LINK_RPC_PORT = 4021


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
               disconnect_hook=None):
    self._check_interval = check_interval
    self._handshake_timeout = handshake_timeout
    self._rpc_timeout = rpc_timeout
    self._connect_hook = connect_hook
    self._disconnect_hook = disconnect_hook
    self._suspend_deadline = None
    self._methods = methods or {}
    self._methods.update({'Announce': self._PresenterAnnounce})
    self._reported_failure = set()
    self._presenter_connected = False
    self._presenter_ip = None
    self._presenter_proxy = None
    self._presenter_announcement = None
    self._discoverer = PresenterDiscoverer(PRESENTER_LINK_RPC_PORT)
    self._kick_event = threading.Event()
    self._abort_event = threading.Event()
    self._server = JSONRPCServer(port=DUT_LINK_RPC_PORT, methods=self._methods)
    self._server.Start()
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

  def Stop(self):
    """Stops and destroys the link manager."""
    self._server.Destroy()
    self._abort_event.set()
    self._kick_event.set() # Kick the thread
    self._thread.join()

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
      return self._presenter_proxy.IsAlive()
    except (socket.error, socket.timeout, AttributeError):
      return False

  def _PresenterAnnounce(self, my_ip, presenter_ips):
    self._presenter_announcement = (my_ip, presenter_ips)
    self._kick_event.set()

  def _HandlePresenterAnnouncement(self):
    my_ip, presenter_ips = self._presenter_announcement
    self._presenter_announcement = None
    for presenter_ip in presenter_ips:
      self._MakePresenterConnection(my_ip, presenter_ip)
      if self._presenter_connected:
        return

  def _MakeTimeoutServerProxy(self, presenter_ip, timeout):
    return jsonrpclib.Server('http://%s:%d/' %
                             (presenter_ip,PRESENTER_LINK_RPC_PORT),
                             transport=TimeoutJSONRPCTransport(timeout))

  def _MakePresenterConnection(self, my_ip, presenter_ip):
    """Attempts to connect the the presenter.

    Args:
      my_ip: The IP address of this DUT received from the presenter; None to guess.
      presenter_ip: The IP address of the presenter.
    """
    if self._presenter_connected and self._presenter_ip == presenter_ip:
      return

    log = (logging.info if presenter_ip not in self._reported_failure else
           lambda *args: None)

    try:
      log('Attempting to connect to presenter %s', presenter_ip)
      self._presenter_proxy = self._MakeTimeoutServerProxy(presenter_ip,
                                                      self._handshake_timeout)
      self._presenter_ip = presenter_ip
      self._presenter_proxy.IsAlive()

      # Presenter is alive. Let's register!
      log('Registering to presenter %s', presenter_ip)
      if not my_ip:
        if utils.in_chroot():
          my_ip = '127.0.0.1'
        else:
          my_ip = map(GetEthernetIp, GetEthernetInterfaces())
          my_ip = [x for x in my_ip if x != '127.0.0.1']
        log('Trying available IP addresses %s', my_ip)
      elif type(my_ip) != list:
        my_ip = [my_ip]

      for ip in my_ip:
        log('Trying IP address %s', ip)
        self._presenter_proxy.Register(ip)

        # Make sure the presenter sees us
        log('Registered. Checking connection.')
        if not self._presenter_proxy.ConnectionGood():
          log('Registration failed.')
          continue
        self._presenter_connected = True
        logging.info('Connected to presenter %s', presenter_ip)
        # Now that we are connected, use a longer timeout for the proxy
        self._presenter_proxy = self._MakeTimeoutServerProxy(presenter_ip,
                                                        self._rpc_timeout)
        if presenter_ip in self._reported_failure:
          self._reported_failure.remove(presenter_ip)
        if self._connect_hook:
          self._connect_hook(presenter_ip)
        return
    except (socket.error, socket.timeout):
      pass

    # If we are here, we failed to make connection. Clean up.
    self._presenter_ip = None
    self._presenter_proxy = None
    self._reported_failure.add(presenter_ip)
    log('Connection failed.')

  def CheckPresenterConnection(self):
    """Check the connection to the presenter.

    If the connection is down, put ourselves into disconnected state and attempt
    to establish the connection again.
    """
    if self._presenter_connected:
      if self.PresenterIsAlive():
        return # everything's fine
      else:
        logging.info('Lost connection to presenter %s', self._presenter_ip)
        self._presenter_connected = False
        self._presenter_ip = None
        self._presenter_proxy = None
        if self._disconnect_hook:
          self._disconnect_hook()

    ips = self._discoverer.Discover()
    if not ips:
      return
    if type(ips) != list:
      ips = [ips]
    for ip in ips:
      self._MakePresenterConnection(None, ip)
      if self._presenter_connected:
        return

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
               disconnect_hook=None):
    self._check_interval = check_interval
    self._rpc_timeout = rpc_timeout
    self._connect_hook = connect_hook
    self._disconnect_hook = disconnect_hook
    self._suspend_deadline = None
    self._methods = methods or {}
    self._methods.update({'Register': self._DUTRegister,
                          'ConnectionGood': self.DUTIsAlive,
                          'SuspendMonitoring': self.SuspendMonitoring,
                          'ResumeMonitoring': self.ResumeMonitoring})
    self._reported_announcement = set()
    self._dut_proxy = None
    self._dut_ip = None
    self._dut_connected = False
    self._lock = threading.Lock()
    self._kick_event = threading.Event()
    self._abort_event = threading.Event()
    self._discoverer = DUTDiscoverer(DUT_LINK_RPC_PORT)
    self._server = JSONRPCServer(port=PRESENTER_LINK_RPC_PORT,
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
            logging.info('Disconnected from DUT %s', self._dut_ip)
            self._dut_connected = False
            self._dut_ip = None
            self._dut_proxy = None
            if self._disconnect_hook:
              self._disconnect_hook()

        ips = self._discoverer.Discover()
        if not ips:
          return
        if type(ips) != list:
          ips = [ips]
        for ip in ips:
          try:
            # We don't get response from the DUT for announcement, so let's
            # keep the timeout short.
            proxy = self._MakeTimeoutServerProxy(ip, timeout=0.05)
            my_ips = GetAllIPs()
            if ip not in self._reported_announcement:
              logging.info('Announcing to DUT %s: presenter ip is %s',
                           ip, my_ips)
              self._reported_announcement.add(ip)
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
      if self._suspend_deadline:
        if time.time() > self._suspend_deadline:
          self._suspend_deadline = None
      else:
        self.CheckDUTConnection()
      self._kick_event.wait(self._check_interval)
      self._kick_event.clear()
      if self._abort_event.isSet():
        return
