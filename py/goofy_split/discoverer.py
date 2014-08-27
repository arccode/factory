#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import jsonrpclib
import socket
import sys
import threading
import Queue
import weakref
from multiprocessing.pool import ThreadPool

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.test.network import GetAllWiredIPs

from cros.factory.utils.jsonrpc_utils import TimeoutJSONRPCTransport


class DiscovererBase(object):
  """Base class for discoverers."""
  LOCALHOST = '127.0.0.1'

  def TryRemote(self, ip, port, timeout=0.2):
    """Try to connect to remote RPC server.

    Tries to connect to a remote link manager RPC server. Returns True
    if successful, false on error or timeout.

    Note that most ports are blocked on DUT by default. If the scan does not
    show the DUT, check iptables setting or use SSH tunnel.

    Params:
      ip: The IP address of the RPC server to try.
      port: The port of the RPC server to try.
      timeout: RPC call timeout.

    Returns:
      True on success. Otherwise, False.
    """
    proxy = jsonrpclib.Server('http://%s:%d/' % (ip, port),
                              transport=TimeoutJSONRPCTransport(timeout))
    try:
      return proxy.IsAlive()
    except socket.error:
      return False

  def ScanSubnets(self, ip_prefixes, port, num_threads=25, limit=None):
    """Scan all machines in class-C subnet.

    Tries to connect to remote link manager RPC servers on all machines in
    class-C subnets in parallel.

    Params:
      ip_prefixes: A list of prefixes of subnets to scan. For example, to scan
          192.168.0.0/24 and 10.0.0.0/24, pass in: ['192.168.0', '10.0.0']
      port: The port of the RPC server.
      num_threads: Number of threads to use.
      limit: If a positive integer, the maximum number of results to return.
          Otherwise, returns all the results.

    Returns:
      A list of IP addresses with RPC server alive.
    """
    if not ip_prefixes:
      return []

    # Workaround enabling constructing ThreadPool on a background thread
    # See http://bugs.python.org/issue10015
    cur_thread = threading.current_thread()
    if not hasattr(cur_thread, "_children"):
      cur_thread._children = weakref.WeakKeyDictionary()
    pool = ThreadPool(num_threads)
    if type(ip_prefixes) != list:
      ip_prefixes = [ip_prefixes]

    # We construct a list of addresses to try, and kick off a thread pool
    # to try them. Responding addresses come back on result_queue.
    # When the scan completes, None is enqueued on result_queue. If the
    # specified limit is reached, we return before the scan is complete.
    result_queue = Queue.Queue()
    def enqueue_remote_if_responds(ip):
      if self.TryRemote(ip, port):
        result_queue.put(ip)

    def scan_complete(_):
      result_queue.put(None)

    remotes = ['%s.%d' % (prefix, low_octet)
      for prefix in ip_prefixes
      for low_octet in xrange(1, 255)]
    pool.map_async(enqueue_remote_if_responds, remotes, callback=scan_complete)

    # Dequeue items until we reach our limit or dequeue None,
    # which means that the scan is finished
    responding_ip_list = []
    while len(responding_ip_list) < (limit or sys.maxint):
      elem = result_queue.get(block=True)
      if elem is None:
        break
      responding_ip_list.append(elem)
    # If we stopped before the scan is complete, cancel any outstanding work
    pool.terminate()
    return responding_ip_list

  def ScanMySubnets(self, port, limit):
    """Scan all subnet this machine is in."""
    my_ips = GetAllWiredIPs()
    subnets = [ip.rsplit('.', 1)[0] for ip in my_ips]
    return self.ScanSubnets(subnets, port, limit=limit)

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
        self.TryRemote(self.LOCALHOST, self._port, timeout=0.1)):
      return self.LOCALHOST
    return self.ScanMySubnets(self._port, limit=None)


class PresenterDiscoverer(DiscovererBase):
  """Discoverer that looks for the presenter."""
  def __init__(self, port):
    super(PresenterDiscoverer, self).__init__()
    self._port = port

  def Discover(self):
    if (utils.in_chroot() or
        self.TryRemote(self.LOCALHOST, self._port, timeout=0.1)):
      return self.LOCALHOST
    return self.ScanMySubnets(self._port, limit=1)
