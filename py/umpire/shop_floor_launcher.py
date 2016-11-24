#!/usr/bin/python

# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Loads ShopFloorHandler module and wraps it as a XMLRPC server.

Note that it only accepts requests with path "/shop_floor/<port>/<token>".

Example:
  /path/to/shop_floor_launcher -a 127.0.0.1 -p 8085 -t abcde \
    -m cros.factory.umpire.<board>_shop_floor_handler
"""

import logging
import optparse
import socket
import sys
from twisted.internet import reactor
from twisted.web import http
from twisted.web import resource
from twisted.web import server
from twisted.web import xmlrpc

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.umpire import shop_floor_handler
from cros.factory.umpire.web import xmlrpc as umpire_xmlrpc


def _LoadShopFloorHandler(module_name, directory):
  """Loads a ShopFloorHandler module.

  Args:
    module_name: Name of module containing a ShopFloorHandler class.
    directory: Path of the directory where the module lives in.

  Returns:
    Module reference.
  """
  sys.path.insert(0, directory)
  module_path = module_name.split('.')
  # Reload modules on the module path to make sure that they're using the
  # updated sys.path.
  try:
    module = sys.modules[module_path[0]]
    reload(module)
    for name in module_path[1:]:
      module = getattr(module, name)
      reload(module)
  except (KeyError, AttributeError):
    pass
  logging.debug('_LoadShopFloorHandler: %s', module_name)
  return __import__(module_name, fromlist=['ShopFloorHandler']).ShopFloorHandler


def _SetLogging(verbosity, quiet):
  """Sets logging level and format.

  Args:
    verbosity: logging verbosity. 0 for INFO and 1 for DEBUG.
    quiet: True to disable INFO logging.
  """
  VERBOSITY_MAP = {0: logging.INFO,
                   1: logging.DEBUG}
  log_level = VERBOSITY_MAP.get(verbosity or 0, logging.NOTSET)

  log_format = ['%(asctime)s %(levelname)s']
  if verbosity > 0:
    log_format.append('(%(filename)s:%(lineno)d)')
  log_format.append('%(message)s')
  logging.basicConfig(level=log_level, format=' '.join(log_format))
  if quiet:
    logging.disable(logging.INFO)


def _DisableDNSLookup():
  """Disables all DNS lookups.

  Since otherwise the logging code may try to resolve IP addresses, which may
  delay request handling.
  """
  def FakeGetFQDN(name=None):
    return name or 'localhost'
  socket.getfqdn = FakeGetFQDN


def _ShopFloorHandlerFactory(module, directory):
  """Creates ShopFloorHandler instance.

  It exits the program if either ShopFloorHandler module fails to load or
  the module does not inherit from ShopFloorHandlerBase.

  Args:
    module: ShopFloorHandler module name.

  Returns:
    A ShopFloorHandler instance.
  """
  try:
    logging.debug('Loading ShopFloorHandler module from %s: %s',
                  directory, module)
    instance = _LoadShopFloorHandler(module, directory)()

    if not isinstance(instance, shop_floor_handler.ShopFloorHandlerBase):
      logging.critical('Module does not inherit ShopFloorHandlerBase: %s',
                       module)
      exit(1)
  except:  # pylint: disable=W0702
    logging.exception('Failed loading module: %s', module)
    exit(1)
  return instance


class _ShopFloorRootResource(resource.Resource, object):
  """Twisted resource that handles POST of a sub-resource on a given path.

  It responds 410 Gone if the request have wrong path.

  Args:
    sub_resource: Resource that should be used on the path.
    path: path that the resource is on.
  """

  isLeaf = True
  allowedMethods = (b'POST',)

  def __init__(self, sub_resource, path):
    super(_ShopFloorRootResource, self).__init__()
    self.sub_resource = sub_resource
    self.path = path

  def MatchPath(self, path):
    """Test if a given path does match"""
    return self.path == path

  def render_POST(self, request):
    if self.MatchPath('/'.join(request.postpath)):
      return self.sub_resource.render_POST(request)
    else:
      request.setResponseCode(http.GONE)
      return ''


def _StartShopFloorProxyServer(address, port, instance, path=None):
  """Starts an XMLRPC service that handles XML-RPC at given address:port.

  It scans methods in the given instance and registers the ones with
  @RPCCall decorated as XMLRPC methods. It uses twisted server as XMLRPC
  server with wrapped application based on the instance.

  It runs forever.

  Args:
    address: IP address to bind.
    port: Port for server to listen.
    instance: Server instance to handle XML RPC requests.
    path: If specified, only accept requests in which their
        request.postpath matches the path array.
  """
  # Resource that actually handle XMLRPC Call
  rpc_resource = umpire_xmlrpc.XMLRPCContainer()
  rpc_resource.AddHandler(instance)
  xmlrpc.addIntrospection(rpc_resource)

  # Resource to dispatch request depends on the path
  root_resource = _ShopFloorRootResource(rpc_resource, path)

  rpc_site = server.Site(root_resource)

  # Listen to rpc server port.
  reactor.listenTCP(port, rpc_site, interface=address)
  reactor.run()


def main():
  description = (
      'It wraps the ShopFloorHandler module as an XMLRPC service which '
      'handles XMLRPC requests. Note that it only handles POST requests with '
      'path "/shop_floor/<port>/<token>".')

  parser = optparse.OptionParser(description=description)
  parser.add_option('-a', '--address', dest='address', metavar='ADDR',
                    default='127.0.0.1',
                    help='address to bind (default: %default)')
  parser.add_option('-p', '--port', dest='port', metavar='PORT', type='int',
                    help='port to bind')
  parser.add_option(
      '-m', '--module', dest='module', metavar='MODULE',
      help=('ShopFloorHandler module to load, in PACKAGE.MODULE format. '
            'e.g. cros.factory.umpire.<board>_shop_floor_handler'))
  parser.add_option(
      '-d', '--directory', dest='directory', metavar='TOOLKIT_DIR',
      help="Location of device toolkit's py_pkg")
  parser.add_option('-t', '--token', dest='token', metavar='TOKEN',
                    help='a unique token for the handler process')
  parser.add_option('-v', '--verbose', action='count', dest='verbose',
                    help='increase message verbosity')
  parser.add_option('-q', '--quiet', action='store_true', dest='quiet',
                    help='turn off verbose messages')

  # Parse args.
  (options, args) = parser.parse_args()
  if args:
    parser.error('Invalid args: %s' % ' '.join(args))

  if not options.module:
    parser.error('You need to assign the module to be loaded (-m).')

  if not options.directory:
    parser.error('You need to assign the root directory to be loaded (-d).')

  _SetLogging(options.verbose, options.quiet)
  _DisableDNSLookup()
  instance = _ShopFloorHandlerFactory(options.module, options.directory)

  # remove starting / from HANDLER_BASE.
  path = '%s/%d/%s' % (
      common.HANDLER_BASE[1:], options.port, options.token)

  logging.info(
      'Starting ShopFloor XMLRPC server (module:%s) on http://%s:%d/%s',
      options.module, options.address, options.port, path)
  # XMLRPC server runs forever.
  _StartShopFloorProxyServer(options.address, options.port, instance, path=path)


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG,
                      format='%(levelname)5s %(message)s')
  main()
