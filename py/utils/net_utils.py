# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Networking-related utilities."""

import httplib
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
