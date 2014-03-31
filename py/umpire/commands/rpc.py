# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101

"""Umpired RPC command class."""


from twisted.web import xmlrpc

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.utils import Registry


# Specification for Fault Code Interoperability, version 20010516
SERVER_ERROR_INTERNAL_XMLRPC_ERROR = -32603

def _HandleRPCResult(deferred):
  """Handles RPC result by appending a callback pair.

  For successful RPC call, the callback just returns 'SUCCESS'.
  For failed RPC call, the errback packs error message to a Fault object
  and returns it.

  Args:
    deferred: a delegation object. Callbacks and errbacks are chained in
    the object. So the actual action can be added after triggering the async
    function. Refer:
        http://twistedmatrix.com/documents/13.0.0/core/howto/defer.html

  Returns:
    The deferred object passed in.
  """
  deferred.addCallbacks(
      lambda _: 'SUCCESS',
      lambda f: xmlrpc.Fault(
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
    return _HandleRPCResult(_Umpired().Deploy(config_file))

  def xmlrpc_stop(self):
    return _HandleRPCResult(_Umpired().Stop())
