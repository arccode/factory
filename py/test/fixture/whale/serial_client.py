#!/usr/bin/env python3
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Client to connect to serial server."""

import argparse
import logging
import sys
import xmlrpc.client

from cros.factory.test.fixture.whale.host import dolphin_server
from cros.factory.utils import type_utils


__all__ = ['SerialClientError', 'SerialClient']
FUNCTIONS = type_utils.Enum(['send', 'receive', 'get_serial_num'])


class SerialClientError(Exception):
  """Exception class for serial_client."""


class SerialClient:
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
      verbose: Enables verbose messaging across xmlrpc.client.ServerProxy.
    """
    remote = 'http://%s:%s' % (host, tcp_port)
    self._server = xmlrpc.client.ServerProxy(remote, verbose=verbose)

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
    args from argparse.parse_args().
  """
  description = (
      'A command-line tool to test serial server.'
  )

  examples = (
      '\nExamples:\n'
      '   > serial_client.py send 0 usbc_action usb\n'
      '\tSend command \'usbc_action usb\' to serial connection index 0.\n'
  )

  parser = argparse.ArgumentParser(
      formatter_class=argparse.RawTextHelpFormatter, description=description,
      epilog=examples)
  parser.add_argument('-d', '--debug', action='store_true', default=False,
                      help='enable debug messages')
  parser.add_argument('--host', default=dolphin_server.DEFAULT_HOST,
                      type=str, help='hostname of server')
  parser.add_argument('--port', default=dolphin_server.DEFAULT_PORT,
                      type=int, help='port that server is listening on')
  parser.add_argument('function', type=str, choices=FUNCTIONS)
  parser.add_argument('serial_index', type=int, default=-1, nargs='?',
                      help='serial connection index')
  parser.add_argument('function_args', nargs=argparse.REMAINDER,
                      help='function arguments')

  return parser.parse_args()


def CallFunction(args, sclient):
  """Parses function call to serial server.

  Args:
    args: dict of function commands, like:
        Send command: {
            function: FUNCTIONS.send,
            serial_index: 0,
            function_args: ['contents to send']}
        Receive command: {
            function: FUNCTIONS.receive,
            serial_index: 0,
            function_args: ['number of bytes to receive']}
        Get serial amount command: {
            function: FUNCTIONS.get_serial_num
            serial_index: -1}
    sclient: SerialClient object.
  """
  if args.function == FUNCTIONS.get_serial_num:
    sclient.GetSerialAmount()
    return

  if args.serial_index == -1:
    raise SerialClientError('No serial index is assigned')

  if args.function == FUNCTIONS.receive:
    sclient.Receive(args.serial_index, int(args.function_args[0]))
  elif args.function == FUNCTIONS.send:
    sclient.Send(args.serial_index, ' '.join(args.function_args))
  else:
    raise SerialClientError('Invalid function ' + args.function)


def real_main():
  args = ParseArgs()
  if args.debug:
    log_level = logging.DEBUG
  else:
    log_level = logging.INFO
  log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  logging.basicConfig(level=log_level, format=log_format)
  sclient = SerialClient(host=args.host, tcp_port=args.port,
                         verbose=args.debug)
  CallFunction(args, sclient)


def main():
  try:
    real_main()
  except KeyboardInterrupt:
    sys.exit(0)
  except SerialClientError as e:
    sys.stderr.write(str(e) + '\n')
    sys.exit(1)


if __name__ == '__main__':
  main()
