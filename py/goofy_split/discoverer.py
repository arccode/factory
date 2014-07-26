#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import jsonrpclib
import socket
import threading
import weakref
from multiprocessing.pool import ThreadPool

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils

from cros.factory.utils.jsonrpc_utils import TimeoutJSONRPCTransport
from cros.factory.utils.net_utils import GetAllWiredIPs


class DiscovererBase(object):
  """Base class for discoverers."""
  LOCALHOST = '127.0.0.1'

  def TryRemote(self, ip, port, ip_list, timeout=0.2):
    """Try to connect to remote RPC server.

    Tries to connect to a remote link manager RPC server. On success, adds
    the remote IP address to 'ip_list' and returns True. On error or timeout,
    returns False.

    Note that most ports are blocked on DUT by default. If the scan does not
    show the DUT, check iptables setting or use SSH tunnel.

    Params:
      ip: The IP address of the RPC server to try.
      port: The port of the RPC server to try.
      ip_list: The list to store successful remote IP addresses.
      timeout: RPC call timeout.

    Returns:
      True on success. Otherwise, False.
    """
    proxy = jsonrpclib.Server('http://%s:%d/' % (ip, port),
                              transport=TimeoutJSONRPCTransport(timeout))
    try:
      proxy.IsAlive()
      if ip_list is not None:
        ip_list.append(ip)
      return True
    except socket.error:
      return False

  def ScanSubnets(self, ip_prefixes, port, num_threads=25):
    """Scan all machines in class-C subnet.

    Tries to connect to remote link manager RPC servers on all machines in
    class-C subnets in parallel.

    Params:
      ip_prefixes: A list of prefixes of subnets to scan. For example, to scan
          192.168.0.0/24 and 10.0.0.0/24, pass in: ['192.168.0', '10.0.0']
      port: The port of the RPC server.
      num_threads: Number of threads to use.

    Returns:
      A list of IP addresses with RPC server alive.
    """
    ip_list = []
    dut_list = []
    # Workaround enabling constructing ThreadPool on a background thread
    # See http://bugs.python.org/issue10015
    cur_thread = threading.current_thread()
    if not hasattr(cur_thread, "_children"):
      cur_thread._children = weakref.WeakKeyDictionary()
    pool = ThreadPool(num_threads)
    if type(ip_prefixes) != list:
      ip_prefixes = [ip_prefixes]
    for prefix in ip_prefixes:
      dut_list.extend([('%s.%d' % (prefix, i), port, ip_list)
                        for i in xrange(1, 255)])
    pool.map(lambda p: self.TryRemote(*p), dut_list)
    return ip_list

  def ScanMySubnets(self, port):
    """Scan all subnet this machine is in."""
    my_ips = GetAllWiredIPs()
    subnets = [ip.rsplit('.', 1)[0] for ip in my_ips]
    return self.ScanSubnets(subnets, port)

  def Discover(self):
    """Returns IP addresses of the potential presenter/DUT."""
    raise NotImplementedError()


class DUTDiscoverer(DiscovererBase):
  """Discoverer that looks for the DUT."""
  def __init__(self, port):
    super(DUTDiscoverer, self).__init__()
    self._port = port

  def Discover(self):
    if (utils.in_chroot() or
        self.TryRemote(self.LOCALHOST, self._port, None, timeout=0.1)):
      return self.LOCALHOST
    return self.ScanMySubnets(self._port)


class PresenterDiscoverer(DiscovererBase):
  """Discoverer that looks for the presenter."""
  def __init__(self, port):
    super(PresenterDiscoverer, self).__init__()
    self._port = port

  def Discover(self):
    if (utils.in_chroot() or
        self.TryRemote(self.LOCALHOST, self._port, None, timeout=0.1)):
      return self.LOCALHOST
    return self.ScanMySubnets(self._port)
