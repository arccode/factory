#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''
This file starts a server for factory shop floor system.

To use it, invoke as a standalone program and assign the shop floor system
module you want to use (modules are located in "shopfloor" subdirectory).

Example:
  ./shopfloor_server -m cros.factory.shopfloor.simple_shopfloor
'''


import glob
import logging
import optparse
import os
import shutil
import SimpleXMLRPCServer
import signal
import socket
import SocketServer
import threading
import time
import zipfile
from fnmatch import fnmatch
from SimpleXMLRPCServer import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler

import factory_common  # pylint: disable=W0611
from cros.factory import shopfloor
from cros.factory.test import utils
from cros.factory.utils import debug_utils


DEFAULT_SERVER_PORT = 8082
# By default, this server is supposed to serve on same host running omaha
# server, accepting connections from client devices; so the address to bind is
# "all interfaces (0.0.0.0)". For partners running server on clients, they may
# want to change address to "localhost".
_DEFAULT_SERVER_ADDRESS = '0.0.0.0'

# File containing name of default shopfloor module
SHOPFLOOR_MODULE_TXT = 'shopfloor_module.txt'

# pylint: disable=W0212


def _LoadShopFloorModule(module_name):
  '''Loads a specified python module.

  Args:
    module_name: Name of module containing a ShopFloor class.

  Returns:
    Module reference.
  '''
  logging.debug('_LoadShopFloorModule: trying %s', module_name)
  return __import__(module_name, fromlist=['ShopFloor']).ShopFloor

def _LoadFactoryUpdater(updater_name):
  '''Loads factory updater module.

  Args:
    updater_name: Name of updater module containing a FactoryUpdateServer class.

  Returns:
    Module reference.
  '''
  logging.debug('_LoadUpdater: trying %s', updater_name)
  return __import__(updater_name,
                    fromlist=['FactoryUpdater']).FactoryUpdater

class MyXMLRPCServer(SocketServer.ThreadingMixIn,
                     SimpleXMLRPCServer):
  """XML/RPC server subclass that logs method calls."""
  # For saving method name and exception between _marshaled_dispatch and
  # _dispatch.
  local = threading.local()

  def _marshaled_dispatch(  # pylint: disable=W0221
      self, data, dispatch_method=None, path=None):
    self.local.method = None
    self.local.exception = None

    response_data = ''
    start_time = time.time()
    try:
      extra_args = [path] if path else []
      response_data = SimpleXMLRPCServer._marshaled_dispatch(
          self, data, dispatch_method, *extra_args)
      return response_data
    finally:
      logging.info('%s %s [%.3f s, %d B in, %d B out]%s',
                   self.local.client_address[0],
                   self.local.method,
                   time.time() - start_time,
                   len(data),
                   len(response_data),
                   (': %s' % self.local.exception
                    if self.local.exception else ''))

  def _dispatch(self, method, params):
    try:
      self.local.method = method
      return SimpleXMLRPCServer._dispatch(self, method, params)
    except:
      logging.exception('Exception in method %s', method)
      self.local.exception = utils.FormatExceptionOnly()
      raise


class MyXMLRPCRequestHandler(SimpleXMLRPCRequestHandler):
  def do_POST(self):
    MyXMLRPCServer.local.client_address = self.client_address
    SimpleXMLRPCRequestHandler.do_POST(self)


def _RunAsServer(address, port, instance):
  '''Starts a XML-RPC server in given address and port.

  Args:
    address: Address to bind server.
    port: Port for server to listen.
    instance: Server instance for incoming XML RPC requests.

  Returns:
    Never returns if the server is started successfully, otherwise some
    exception will be raised.
  '''
  server = MyXMLRPCServer((address, port),
                          MyXMLRPCRequestHandler,
                          allow_none=True,
                          logRequests=False)
  server.register_introspection_functions()
  server.register_instance(instance)
  logging.info('Server started: http://%s:%s "%s" version %s',
               address, port, instance.NAME, instance.VERSION)
  server.serve_forever()


def GetDefaultShopFloorModule():
  """Returns the default shopfloor module.

  This is read from SHOPFLOOR_MODULE_TXT; if that file does not
  exist, then cros.factory.shopfloor is used.
  """
  module_txt = os.path.join(
      os.path.dirname(os.path.realpath(__file__)),
      SHOPFLOOR_MODULE_TXT)
  if os.path.exists(module_txt):
    with open(module_txt) as f:
      return f.read().strip()
  return 'cros.factory.shopfloor'


def main():
  '''Main entry when being invoked by command line.'''
  default_data_dir = 'shopfloor_data'
  external_updater_dir = 'updates'
  if not os.path.exists(default_data_dir) and (
      'CROS_WORKON_SRCROOT' in os.environ):
    default_data_dir = os.path.join(
        os.environ['CROS_WORKON_SRCROOT'],
        'src', 'platform', 'factory', 'shopfloor_data')

  parser = optparse.OptionParser()
  parser.add_option('-a', '--address', dest='address', metavar='ADDR',
                    default=_DEFAULT_SERVER_ADDRESS,
                    help='address to bind (default: %default)')
  parser.add_option('-p', '--port', dest='port', metavar='PORT', type='int',
                    default=DEFAULT_SERVER_PORT,
                    help='port to bind (default: %default)')
  parser.add_option(
      '-m', '--module', dest='module', metavar='MODULE',
      default=GetDefaultShopFloorModule(),
      help=('shop floor system module to load, in '
            'PACKAGE.MODULE.CLASS format. E.g.: '
            'cros.factory.shopfloor.simple_shopfloor '
            '(default: %default; may be overridden with a file '
            'called shopfloor_module.txt)'))
  parser.add_option('-c', '--config', dest='config', metavar='CONFIG',
                    help='configuration data for shop floor system')
  parser.add_option('-d', '--data-dir', dest='data_dir', metavar='DIR',
                    default=default_data_dir,
                    help=('data directory for shop floor system '
                          '(default: %default)'))
  parser.add_option('-v', '--verbose', action='count', dest='verbose',
                    help='increase message verbosity')
  parser.add_option('-q', '--quiet', action='store_true', dest='quiet',
                    help='turn off verbose messages')
  parser.add_option(
      '--auto-archive-logs', metavar='TEMPLATE',
      default='/media/shopfloorlg/logs.DATE.tar.bz2',
      help=("File in which to automatically archive previous few days' logs. "
            "Logs will be archived if this path's parent exists.  The format "
            "must contain the string 'DATE'; this will be replaced with "
            "the date. (default: %default)"))
  parser.add_option(
      '--auto-archive-logs-days', metavar='NUM_DAYS', type=int,
      default=3, help="Number of previous days' logs to save to USB.")
  parser.add_option('--simple', action='store_true',
                    help=('use simple shopfloor server (equivalent to '
                          '-m cros.factory.shopfloor.simple_shopfloor)'))
  parser.add_option('--dummy', action='store_true',
                    help=('run dummy shopfloor server, using simple shopfloor '
                          'server and data from testdata directory (implies '
                          '--simple)'))
  parser.add_option('-f', '--fcgi', dest='fastcgi', action='store_true',
                    default=False, help='run as a FastCGI process')
  parser.add_option('-u', '--updater', dest='updater', metavar='UPDATER',
                    default=None,
                    help=('factory updater module to load, in'
                          'PACKAGE.MODULE.CLASS format. E.g.: '
                          'cros.factory.shopfloor.launcher.external_updater '
                          '(default: %default)'))
  parser.add_option('--updater-dir', dest='updater_dir', metavar='UPDATE_DIR',
                    default=external_updater_dir,
                    help='external updater module dir. (default: %default)')
  (options, args) = parser.parse_args()
  if args:
    parser.error('Invalid args: %s' % ' '.join(args))

  if not options.module:
    parser.error('You need to assign the module to be loaded (-m).')

  verbosity_map = {0: logging.INFO,
                   1: logging.DEBUG}
  verbosity = verbosity_map.get(options.verbose or 0, logging.NOTSET)
  log_format = '%(asctime)s %(levelname)s '
  if options.verbose > 0:
    log_format += '(%(filename)s:%(lineno)d) '
  log_format += '%(message)s'
  logging.basicConfig(level=verbosity, format=log_format)
  if options.quiet:
    logging.disable(logging.INFO)

  debug_utils.MaybeStartDebugServer()

  # Disable all DNS lookups, since otherwise the logging code may try to
  # resolve IP addresses, which may delay request handling.
  def FakeGetFQDN(name=''):
    return name or 'localhost'
  socket.getfqdn = FakeGetFQDN

  if options.dummy:
    options.simple = True
  if options.simple:
    options.module = 'cros.factory.shopfloor.simple_shopfloor'

  SHOPFLOOR_SUFFIX = '.ShopFloor'
  if options.module.endswith(SHOPFLOOR_SUFFIX):
    options.module = options.module[0:-len(SHOPFLOOR_SUFFIX)]
    logging.warn("The value of the '-m' flag no longer needs to end with %r; "
                 "use '-m %s' instead", SHOPFLOOR_SUFFIX, options.module)

  updater = None
  if options.updater:
    logging.debug('Loading factory updater: %s', options.updater)
    updater = _LoadFactoryUpdater(options.updater)(options.updater_dir)

  try:
    logging.debug('Loading shop floor system module: %s', options.module)
    instance = _LoadShopFloorModule(options.module)()

    if not isinstance(instance, shopfloor.ShopFloorBase):
      logging.critical('Module does not inherit ShopFloorBase: %s',
                       options.module)
      exit(1)

    instance.data_dir = options.data_dir
    instance.config = options.config

    # Shopfloor module contains update server in its base class. When it is
    # configured to FastCGI mode, update server will be started by launcher.
    instance._InitBase(options.auto_archive_logs,
                       options.auto_archive_logs_days,
                       updater=updater)

    if options.dummy:
      root, ext, path = __file__.partition('.par/')
      if ext:
        # We're inside a .par file.  Load test data from inside the par.
        # TODO(jsalz): Factor this logic out to a separate method.
        z = zipfile.ZipFile(root + ext[:-1])
        pattern = os.path.join(os.path.dirname(path), 'testdata', '*.csv')
        csvs = [x for x in z.namelist() if fnmatch(x, pattern)]
        if not csvs:
          logging.critical('No test files matching %s', pattern)
          exit(1)
        for f in csvs:
          logging.warn('Using data file %s%s%s from dummy shopfloor server',
                       root, ext, f)
          with open(os.path.join(instance.data_dir, os.path.basename(f)),
                    'w') as out:
            out.write(z.read(f))
        z.close()
      else:
        pattern = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            'testdata', '*.csv')
        csvs = glob.glob(pattern)
        if not csvs:
          logging.critical('No test files matching %s', pattern)
          exit(1)
        for f in csvs:
          logging.warn('Using data file %s from dummy shopfloor server', f)
          shutil.copy(f, instance.data_dir)

    instance.Init()
  except:  # pylint: disable=W0702
    logging.exception('Failed loading module: %s', options.module)
    exit(1)

  def handler(signum, frame):  # pylint: disable=W0613
    raise SystemExit
  signal.signal(signal.SIGTERM, handler)

  try:
    instance._StartBase()
    if options.fastcgi:
      logging.debug('Starting RPC FastCGI...')
      # TODO(rong): move FastCGI import back to file header and purge
      #             standalone web server.
      # Shopfloor server can be ran in standalone mode without frontend. To
      # keep it compatible to v1 environment, the import is delayed until
      # we do need it.
      from cros.factory.shopfloor.launcher.fcgi_shopfloor import RunAsFastCGI
      RunAsFastCGI(address=options.address, port=options.port,
                   instance=instance)
    else:
      logging.debug('Starting RPC server...')
      _RunAsServer(address=options.address, port=options.port,
                   instance=instance)
  finally:
    instance._StopBase()


if __name__ == '__main__':
  main()
