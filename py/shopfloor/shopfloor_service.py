#!/usr/bin/env python2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation of ChromeOS Factory Shopfloor Service, version 1.0."""

import logging
import optparse
import SimpleXMLRPCServer
import socket
import SocketServer


DEFAULT_SERVER_PORT = 8090
DEFAULT_SERVER_ADDRESS = '0.0.0.0'

KEY_SERIAL_NUMBER = 'serials.serial_number'
KEY_MLB_SERIAL_NUMBER = 'serials.mlb_serial_number'


class ShopfloorService(object):

  def __init__(self):
    pass

  def GetVersion(self):
    """Returns the version of supported protocol."""
    return '1.0'

  def NotifyStart(self, data, station):
    """Notifies shopfloor backend that DUT is starting a manufacturing station.

    Args:
      data: A FactoryDeviceData instance.
      station: A string to indicate manufacturing station.

    Returns:
      A mapping in DeviceData format.
    """
    logging.info('DUT %s Entering station %s', data.get(KEY_MLB_SERIAL_NUMBER),
                 station)
    return {}

  def NotifyEnd(self, data, station):
    """Notifies shopfloor backend that DUT has finished a manufacturing station.

    Args:
      data: A FactoryDeviceData instance.
      station: A string to indicate manufacturing station.

    Returns:
      A mapping in DeviceData format.
    """
    logging.info('DUT %s Leaving station %s', data.get(KEY_MLB_SERIAL_NUMBER),
                 station)
    return {}

  def NotifyEvent(self, data, event):
    """Notifies shopfloor backend that the DUT has performed an event.

    Args:
      data: A FactoryDeviceData instance.
      event: A string to indicate manufacturing event.

    Returns:
      A mapping in FactoryDeviceData format.
    """
    assert event in ['Finalize', 'Refinalize']
    logging.info('DUT %s sending event %s', data.get(KEY_MLB_SERIAL_NUMBER),
                 event)
    return {}

  def GetDeviceInfo(self, data):
    """Returns information about the device's expected configuration.

    Args:
      data: A FactoryDeviceData instance.

    Returns:
      A mapping in DeviceData format.
    """
    logging.info('DUT %s requesting device information',
                 data.get(KEY_MLB_SERIAL_NUMBER))
    return {'vpd.ro.region': 'us',
            'vpd.rw.ubind_attribute': '',
            'vpd.rw.gbind_attribute': ''}

  def ActivateRegCode(self, ubind_attribute, gbind_attribute, hwid):
    """Notifies shopfloor backend that DUT has deployed a registration code.

    Args:
      ubind_attribute: A string for user registration code.
      gbind_attribute: A string for group registration code.
      hwid: A string for the HWID of the device.

    Returns:
      A mapping in DeviceData format.
    """
    logging.info('DUT <hwid=%s> requesting to activate regcode(u=%s,g=%s)',
                 hwid, ubind_attribute, gbind_attribute)
    return {}

  def UpdateTestResult(self, data, test_id, status, details=None):
    """Sends the specified test result to shopfloor backend.

    Args:
      data: A FactoryDeviceData instance.
      test_id: A string as identifier of the given test.
      status: A string from TestState; one of PASSED, FAILED, SKIPPED, or
          FAILED_AND_WAIVED.
      details: (optional) A mapping to provide more details, including at least
          'error_message'.

    Returns:
      A mapping in DeviceData format. If 'action' is included, DUT software
      should follow the value to decide how to proceed.
    """
    logging.info('DUT %s updating test results for <%s> with status <%s> %s',
                 data.get(KEY_MLB_SERIAL_NUMBER), test_id, status,
                 details.get('error_message') if details else '')
    return {}


class ThreadedXMLRPCServer(SocketServer.ThreadingMixIn,
                           SimpleXMLRPCServer.SimpleXMLRPCServer):
  """A threaded XML RPC Server."""
  pass



def RunAsServer(address, port, instance, logRequest=False):
  """Starts a XML-RPC server in given address and port.

  Args:
    address: Address to bind server.
    port: Port for server to listen.
    instance: Server instance for incoming XML RPC requests.
    logRequests: Boolean to indicate if we should log requests.

  Returns:
    Never returns if the server is started successfully, otherwise some
    exception will be raised.
  """
  server = ThreadedXMLRPCServer((address, port), allow_none=True,
                                logRequests=logRequest)
  server.register_introspection_functions()
  server.register_instance(instance)
  logging.info('Server started: http://%s:%s "%s" version %s',
               address, port, instance.__class__.__name__,
               instance.GetVersion())
  server.serve_forever()


def main():
  """Main entry when being invoked by command line."""
  parser = optparse.OptionParser()
  parser.add_option('-a', '--address', dest='address', metavar='ADDR',
                    default=DEFAULT_SERVER_ADDRESS,
                    help='address to bind (default: %default)')
  parser.add_option('-p', '--port', dest='port', metavar='PORT', type='int',
                    default=DEFAULT_SERVER_PORT,
                    help='port to bind (default: %default)')
  parser.add_option('-v', '--verbose', dest='verbose', default=False,
                    action='store_true',
                    help='provide verbose logs for debugging.')
  (options, args) = parser.parse_args()
  if args:
    parser.error('Invalid args: %s' % ' '.join(args))

  log_format = '%(asctime)s %(levelname)s %(message)s'
  logging.basicConfig(level=logging.DEBUG if options.verbose else logging.INFO,
                      format=log_format)

  # Disable all DNS lookups, since otherwise the logging code may try to
  # resolve IP addresses, which may delay request handling.
  socket.getfqdn = lambda name: name or 'localhost'

  try:
    RunAsServer(address=options.address, port=options.port,
                instance=ShopfloorService(),
                logRequest=options.verbose)
  finally:
    logging.warn('Server stopped.')


if __name__ == '__main__':
  main()
