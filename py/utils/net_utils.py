# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Networking-related utilities."""

import glob
import httplib
import os
import subprocess
import time
import xmlrpclib

DEFAULT_TIMEOUT = 10


class TimeoutHTTPConnection(httplib.HTTPConnection):
  def connect(self):
    httplib.HTTPConnection.connect(self)
    self.sock.settimeout(self.timeout)

class TimeoutHTTP(httplib.HTTP):
  _connection_class = TimeoutHTTPConnection
  def set_timeout(self, timeout):
    self._conn.timeout = timeout

class TimeoutXMLRPCTransport(xmlrpclib.Transport):
  '''Transport subclass supporting timeout.'''
  def __init__(self, timeout=DEFAULT_TIMEOUT, *args, **kwargs):
    xmlrpclib.Transport.__init__(self, *args, **kwargs)
    self.timeout = timeout

  def make_connection(self, host):
    conn = TimeoutHTTP(host)
    conn.set_timeout(self.timeout)
    return conn

class TimeoutXMLRPCServerProxy(xmlrpclib.ServerProxy):
  '''XML/RPC ServerProxy supporting timeout.'''
  def __init__(self, uri, timeout=10, *args, **kwargs):
    if timeout:
      kwargs['transport'] = TimeoutXMLRPCTransport(
        timeout=timeout)
    xmlrpclib.ServerProxy.__init__(self, uri, *args, **kwargs)

def FindUsableEthDevice():
  """Find the real ethernet interface when the flimflam is unavailable.

  Some devices with 4G modules may bring up fake eth interfaces during
  the factory flow. Flimflam is often used to tell the real interface type
  in the case. Unfortunately, we may sometimes need to turn it off to
  perform tests on network components. We thus need another way to reliably
  distinguish the real interface type.
  """
  good_eth = None
  last_level = 0
  candidates = glob.glob('/sys/class/net/eth*')
  for path in candidates:
    dev = os.path.basename(path)
    p = subprocess.Popen('ethtool %s' % dev, shell=True,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stat = p.communicate()[0]

    # A 4G introduced ethernet interface would not be able to report its
    # setting data because it won't get online during the factory flow.
    # In case that there are several real ethernet interfaces available,
    # we favor the one that has the cable connected end-to-end.
    current_level = 0
    if 'Supported ports:' in stat:
      current_level = 1
      if 'Link detected: yes' in stat:
        current_level = 2
    if current_level > last_level:
      good_eth = dev
      last_level = current_level
  return good_eth
