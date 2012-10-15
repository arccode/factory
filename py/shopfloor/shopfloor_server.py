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
import hashlib
import imp
import logging
import optparse
import os
import shutil
import SimpleXMLRPCServer
import socket
import zipfile
from fnmatch import fnmatch

import factory_common
from cros.factory import shopfloor


DEFAULT_SERVER_PORT = 8082
# By default, this server is supposed to serve on same host running omaha
# server, accepting connections from client devices; so the address to bind is
# "all interfaces (0.0.0.0)". For partners running server on clients, they may
# want to change address to "localhost".
_DEFAULT_SERVER_ADDRESS = '0.0.0.0'


def _LoadShopFloorModule(module_name):
  '''Loads a specified python module.

  Args:
    module_name: Name of module containing a ShopFloor class.

  Returns:
    Module reference.
  '''
  logging.debug('_LoadShopFloorModule: trying %s', module_name)
  return __import__(module_name, fromlist=['ShopFloor']).ShopFloor


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
  server = SimpleXMLRPCServer.SimpleXMLRPCServer((address, port),
                                                 allow_none=True,
                                                 logRequests=False)
  server.register_introspection_functions()
  server.register_instance(instance)
  logging.info('Server started: http://%s:%s "%s" version %s',
               address, port, instance.NAME, instance.VERSION)
  server.serve_forever()


def main():
  '''Main entry when being invoked by command line.'''
  if 'CROS_WORKON_SRCROOT' in os.environ:
    default_data_dir = os.path.join(
        os.environ['CROS_WORKON_SRCROOT'],
        'src', 'platform', 'factory', 'shopfloor_data')
  else:
    default_data_dir = 'shopfloor_data'

  parser = optparse.OptionParser()
  parser.add_option('-a', '--address', dest='address', metavar='ADDR',
                    default=_DEFAULT_SERVER_ADDRESS,
                    help='address to bind (default: %default)')
  parser.add_option('-p', '--port', dest='port', metavar='PORT', type='int',
                    default=DEFAULT_SERVER_PORT,
                    help='port to bind (default: %default)')
  parser.add_option(
      '-m', '--module', dest='module', metavar='MODULE',
      default='cros.factory.shopfloor',
      help=('shop floor system module to load, in '
            'PACKAGE.MODULE.CLASS format. E.g.: '
            'cros.factory.shopfloor.simple_shopfloor '
            '(default: %default)'))
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
  parser.add_option('--simple', action='store_true',
                    help=('use simple shopfloor server (equivalent to '
                          '-m cros.factory.shopfloor.simple_shopfloor)'))
  parser.add_option('--dummy', action='store_true',
                    help=('run dummy shopfloor server, using simple shopfloor '
                          'server and data from testdata directory (implies '
                          '--simple)'))
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

  try:
    logging.debug('Loading shop floor system module: %s', options.module)
    instance = _LoadShopFloorModule(options.module)()

    if not isinstance(instance, shopfloor.ShopFloorBase):
      logging.critical('Module does not inherit ShopFloorBase: %s',
                       options.module)
      exit(1)

    instance.data_dir = options.data_dir
    instance.config = options.config

    instance._InitBase()

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
  except:
    logging.exception('Failed loading module: %s', options.module)
    exit(1)

  # Find the HWID updater (if any).  Throw an exception if there are >1.
  hwid_updater_path = instance._GetHWIDUpdaterPath()
  if hwid_updater_path:
    logging.info('Using HWID updater %s (md5sum %s)' % (
        hwid_updater_path,
        hashlib.md5(open(hwid_updater_path).read()).hexdigest()))
  else:
    logging.warn('No HWID updater id currently available; add a single '
                 'file named %s to enable dynamic updating of HWIDs.' %
                 os.path.join(options.data_dir, shopfloor.HWID_UPDATER_PATTERN))

  try:
    instance._StartBase()
    logging.debug('Starting RPC server...')
    _RunAsServer(address=options.address, port=options.port, instance=instance)
  finally:
    instance._StopBase()


if __name__ == '__main__':
  main()
