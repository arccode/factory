# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101

"""Umpired RPC command class."""


from twisted.web import xmlrpc

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.utils import Registry


DEFAULT_COMMAND_PORT = 8032

# Specification for Fault Code Interoperability, version 20010516
SERVER_ERROR_INTERNAL_XMLRPC_ERROR = -32603

def _AddCallbacks(deferred):
  """Adds return messages to callback results.

  Args:
    deferred: a delegation object. Callbacks and error callbacks are chained in
    the object. So the actual action can be added after triggering the async
    function.

  Example:
    def OnDataReceived(data):
      pass

    def OnReadError(error):
      pass

    d = ReadFile(f, len)
    d.addErrback(OnReadError)
    d.addCallback(OnDataReceived)
    d.addCallback(BackupData)
  """
  deferred.addCallback(lambda _: 'SUCCESS')
  deferred.addErrback(lambda f: xmlrpc.Fault(
      SERVER_ERROR_INTERNAL_XMLRPC_ERROR,
      '%s\n%s' % (repr(f.value), f.getTraceback())))
  return deferred


def _Umpired():
  """Returns umpired instance from Registry.

  UmpireDaemon() is created in '__main__'. And the daemon adds itself into
  system registry.
  """
  return Registry().umpired


# TODO: Sample RPC functions are for server test only.
class UmpireCommand(xmlrpc.XMLRPC):
  """Umpire XMLRPC commands.

  Twisted web application example:
    rpc = xmlrpc.XMLRPC()    # a resource.Resource
    site = server.Site(rpc)  # subclassed http.HTTPFactory
    port = reactor.listenTCP(rpc_port, site)  # creates server endpoint
                                              # and listen to it
    reactor.run()

  Returns:
    defer.Deferred: the server waits for the callback/errback.
    xmlrpc.Fault(): the server converts the error to
                    twisted.python.failure.Failure(xmlrpclib.Fault())
    Other values: return to caller.
  """
  def xmlrpc_deploy(self, config_file):
    """Deploy Umpire config file."""
    return _AddCallbacks(_Umpired().Deploy(config_file))

  def xmlrpc_stop(self):
    return _AddCallbacks(_Umpired().Stop())
