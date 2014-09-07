#!/usr/bin/python

# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Loads ShopFloorHandler module and wraps it as a FastCGI server.

Note that it only accepts requests with path "/shop_floor/<port>/<token>".

Example:
  /path/to/shop_floor_launcher -a 127.0.0.1 -p 8085 -t abcde \
    -m cros.factory.umpire.<board>_shop_floor_handler
"""

import logging
import optparse
import socket

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import fastcgi_server
from cros.factory.umpire import shop_floor_handler


def _LoadShopFloorHandler(module_name):
  """Loads a ShopFloorHandle module.

  Args:
    module_name: Name of module containing a ShopFloorHandler class.

  Returns:
    Module reference.
  """
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


def _ShopFloorHandlerFactory(module):
  """Creates ShopFloorHandler instance.

  It exists the program if either ShopFloorHandler module fails to load or
  the module does not inherit from ShopFloorHandlerBase.

  Args:
    module: ShopFloorHandler module name.

  Returns:
    A ShopFloorHandler instance.
  """
  try:
    logging.debug('Loading ShopFloorHandler module: %s', module)
    instance = _LoadShopFloorHandler(module)()

    if not isinstance(instance, shop_floor_handler.ShopFloorHandlerBase):
      logging.critical('Module does not inherit ShopFloorHandlerBase: %s',
                       module)
      exit(1)
  except:  # pylint: disable=W0702
    logging.exception('Failed loading module: %s', module)
    exit(1)
  return instance


def main():
  description = (
      'It wraps the ShopFloorHandler module as an FastCGI service which '
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

  _SetLogging(options.verbose, options.quiet)
  _DisableDNSLookup()
  instance = _ShopFloorHandlerFactory(options.module)

  # WSGI environ's SCRIPT_NAME to accept.
  script_name = '/shop_floor/%d/%s' % (options.port, options.token)

  logging.info(
      'Starting FastCGI server (module:%s) on http://%s:%d%s',
      options.module, options.address, options.port, script_name)
  # FastCGI server runs forever.
  fastcgi_server.FastCGIServer(
      options.address, options.port, instance, script_name=script_name)


if __name__ == '__main__':
  main()
