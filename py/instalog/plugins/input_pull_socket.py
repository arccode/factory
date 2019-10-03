#!/usr/bin/env python2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input pull socket plugin.

Waits for events from an output pull socket plugin running on another Instalog
node.

See socket_common.py for protocol definition.
"""

from __future__ import print_function

from six.moves import xrange
import socket

import instalog_common  # pylint: disable=unused-import
from instalog import plugin_base
from instalog.plugins import input_socket
from instalog.plugins import socket_common
from instalog.utils.arg_utils import Arg


_CONNECT_INTERVAL = 1
_CONNECT_LOG_INTERVAL = 60  # interval
                            #     = _CONNECT_INTERVAL * _CONNECT_LOG_INTERVAL
                            #     = 60s


class ChecksumError(Exception):
  """Represents a checksum mismatch."""
  pass


# TODO(chuntsen): Encryption and authentication
class InputPullSocket(plugin_base.InputPlugin):

  ARGS = [
      Arg('hostname', (str, unicode), 'Hostname that server should bind to.'),
      Arg('port', int, 'Port that server should bind to.',
          default=socket_common.DEFAULT_PULL_PORT)
  ]

  def __init__(self, *args, **kwargs):
    self._sock = None
    super(InputPullSocket, self).__init__(*args, **kwargs)

  def GetSocket(self):
    """Creates and returns a new socket connection to the target host."""
    self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self._sock.settimeout(socket_common.SOCKET_TIMEOUT)
    self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF,
                          socket_common.SOCKET_BUFFER_SIZE)
    try:
      self._sock.connect((self.args.hostname, self.args.port))
      # Send qing.
      self._sock.sendall(socket_common.QING)
      # Receive qong.
      received_char = self._sock.recv(1)
      self.debug('Received a char: %s', received_char)
      if not received_char == socket_common.QING_RESPONSE:
        self.debug('Invalid qong: %s', received_char)
        self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()
        return False
      return True
    except Exception:
      return False

  def Main(self):
    """Main Thread of the plugin."""
    while not self.IsStopping():
      success = False
      while not success:
        for _unused_i in xrange(_CONNECT_LOG_INTERVAL):
          success = self.GetSocket()
          if self.IsStopping():
            return
          if success:
            break
          self.Sleep(_CONNECT_INTERVAL)
        if not success:
          self.warning('Connection to target unavailable')

      receiver = input_socket.InputSocketReceiver(
          self.logger.name, self._sock, self)
      receiver.ProcessRequest()


if __name__ == '__main__':
  plugin_base.main()
