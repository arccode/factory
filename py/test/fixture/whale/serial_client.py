#!/usr/bin/env python2
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Client to connect to serial server."""

from __future__ import print_function

import logging
import optparse
import sys
import xmlrpclib

import factory_common  # pylint: disable=unused-import
from cros.factory.test.fixture.whale.host import dolphin_server


__all__ = ['SerialClientError', 'SerialClient']


class SerialClientError(Exception):
  """Exception class for serial_client."""
  pass


class SerialClient(object):
  """Class to interface with serial_server via XMLRPC.

  For multiple serial connection established of serial server. serial_index is
  used for indicating the corresponding n-th serial connection (zero based)
  while requesting 'send' and 'receive' commands on the server side.
  """

  def __init__(self, host, tcp_port, verbose=False):
    """Constructor.

    Args:
      host: Name or IP address of serial server host.
      tcp_port: TCP port on which serial server is listening on.
      verbose: Enables verbose messaging across xmlrpclib.ServerProxy.
    """
    remote = 'http://%s:%s' % (host, tcp_port)
    self._server = xmlrpclib.ServerProxy(remote, verbose=verbose)

  def Send(self, serial_index, command):
    """Sends a command through serial server.

    Args:
      serial_index: index of serial connections.
      command: command to send.

    Raises:
      SerialClientError if error occurs.
    """
    try:
      self._server.Send(serial_index, command)
    except Exception as e:
      raise SerialClientError('Fail to send command %s to serial_index %d: %s' %
                              (command, serial_index, e))

  def Receive(self, serial_index, num_bytes):
    """Receives N byte data through serial server.

    Args:
      serial_index: index of serial connections.
      num_bytes: number of bytes to receive. 0 means receiving what already in
          the input buffer.

    Returns:
      Received N bytes.

    Raises:
      SerialClientError if error occurs.
    """
    try:
      recv = self._server.Receive(serial_index, num_bytes)
      logging.debug('Receive data: %s', recv)
      return recv
    except Exception as e:
      raise SerialClientError(
          'Fail to receive %d bytes from serial_index %d: %s' %
          (num_bytes, serial_index, e))

  def GetSerialAmount(self):
    """Gets total serial amount on server.

    Returns:
      Number of serial connections.
    """
    try:
      serial_amount = self._server.GetSerialAmount()
      logging.debug('Get total serial amount = %d', serial_amount)
      return serial_amount
    except Exception as e:
      raise SerialClientError('Fail to get serial amount: %s' % e)


def ParseArgs():
  """Parses commandline arguments.

  Returns:
    tuple (options, args) from optparse.parse_args().
  """
  usage = (
      'usage: %prog [options] <function> <serial_index> <arg1 arg2 ...> ...\n'
      '\t- function is [send, receive, get_serial_num].\n'
      '\t- serial_index is serial connection index.\n'
      '\t- arg<n> is the function arguments.\n'
  )

  description = (
      '%prog is command-line tool to test serial server. '
  )

  examples = (
      '\nExamples:\n'
      '   > %prog send 0 usbc_action usb\n'
      '\tSend command \'usbc_action usb\' to serial connection index 0.\n'
  )

  parser = optparse.OptionParser(usage=usage)
  parser.description = description
  parser.add_option('-d', '--debug', action='store_true', default=False,
                    help='enable debug messages')
  parser.add_option('', '--host', default=dolphin_server.DEFAULT_HOST,
                    type=str, help='hostname of server')
  parser.add_option('', '--port', default=dolphin_server.DEFAULT_PORT,
                    type=int, help='port that server is listening on')

  parser.set_usage(parser.get_usage() + examples)
  return parser.parse_args()


def CallFunction(commands, sclient):
  """Parses function call to serial server.

  Args:
    commands: list of function commands, like:
        Send command: ['send', serial_index, contents to send...]
        Receive command: ['receive', serial_index, number of bytes to receive]
        Get serial amount command: ['get_serial_num']
    sclient: SerialClient object.
  """
  if not commands:
    raise SerialClientError('No command is given')

  function = commands.pop(0)
  if function == 'get_serial_num':
    sclient.GetSerialAmount()
    return

  if not commands:
    raise SerialClientError('No serial index is assigned')

  serial_index = int(commands.pop(0))
  if function == 'receive':
    sclient.Receive(serial_index, int(commands[0]))
  elif function == 'send':
    sclient.Send(serial_index, ' '.join(commands))
  else:
    raise SerialClientError('Invalid function ' + function)


def real_main():
  (options, commands) = ParseArgs()
  if options.debug:
    log_level = logging.DEBUG
  else:
    log_level = logging.INFO
  log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  logging.basicConfig(level=log_level, format=log_format)
  sclient = SerialClient(host=options.host, tcp_port=options.port,
                         verbose=options.debug)
  CallFunction(commands, sclient)


def main():
  try:
    real_main()
  except KeyboardInterrupt:
    sys.exit(0)
  except SerialClientError as e:
    sys.stderr.write(e.message + '\n')
    sys.exit(1)


if __name__ == '__main__':
  main()
