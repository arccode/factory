#!/usr/bin/python2
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

import socket

import instalog_common  # pylint: disable=unused-import
from instalog import plugin_base
from instalog.plugins import input_socket
from instalog.plugins import socket_common
from instalog.utils.arg_utils import Arg


_FAILED_CONNECTION_INTERVAL = 60


class ChecksumError(Exception):
  """Represents a checksum mismatch."""
  pass


# TODO(chuntsen): Encryption and authentication
class InputPullSocket(plugin_base.InputPlugin):

  ARGS = [
      Arg('hostname', (str, unicode), 'Hostname that server should bind to.',
          optional=False),
      Arg('port', int, 'Port that server should bind to.',
          optional=True, default=socket_common.DEFAULT_PULL_PORT)
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
      return True
    except Exception:
      return False

  def Main(self):
    """Main Thread of the plugin."""
    while not self.IsStopping():
      if not self.GetSocket():
        self.warning('Connection to target unavailable')
        self.Sleep(_FAILED_CONNECTION_INTERVAL)
        continue

      receiver = input_socket.InputSocketReceiver(self.logger, self._sock, self)
      receiver.ProcessRequest()


if __name__ == '__main__':
  plugin_base.main()
