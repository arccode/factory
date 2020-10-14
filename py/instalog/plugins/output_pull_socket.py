#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Output pull socket plugin.

Transmits events to an input pull socket plugin running on another Instalog
node.

See socket_common.py for protocol definition.
"""

import socket

from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import output_socket
from cros.factory.instalog.plugins import socket_common
from cros.factory.instalog.utils.arg_utils import Arg


_DEFAULT_BATCH_SIZE = 500
_DEFAULT_TIMEOUT = 5
_DEFAULT_HOSTNAME = '0.0.0.0'
_ACCEPT_TIMEOUT = 1
_ACCEPT_LOG_INTERVAL = 60  # interval = _ACCEPT_TIMEOUT * _ACCEPT_LOG_INTERVAL =
                           # 60s


# TODO(chuntsen): Encryption and authentication
class OutputPullSocket(plugin_base.OutputPlugin):

  ARGS = [
      Arg('batch_size', int, 'How many events to queue before transmitting.',
          default=_DEFAULT_BATCH_SIZE),
      Arg('timeout', (int, float), 'Timeout to transmit without full batch.',
          default=_DEFAULT_TIMEOUT),
      Arg('hostname', str, 'Hostname that server should bind to.',
          default=_DEFAULT_HOSTNAME),
      Arg('port', int, 'Port that server should bind to.',
          default=socket_common.DEFAULT_PULL_PORT)
  ]

  def __init__(self, *args, **kwargs):
    self._sock = None
    self._accept_sock = None
    super(OutputPullSocket, self).__init__(*args, **kwargs)

  def GetSocket(self):
    """Accepts a socket from input pull socket."""
    self._accept_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self._accept_sock.settimeout(_ACCEPT_TIMEOUT)
    self._accept_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.debug('Socket created')

    # Bind socket.
    try:
      self._accept_sock.bind((self.args.hostname, self.args.port))
    except socket.error as e:
      self.exception('Bind failed. Error : %s' % e)
      raise
    self.debug('Socket bind complete')

    try:
      # Queue up to 1 requests.
      self._accept_sock.listen(1)
      self.debug('Socket now listening on %s:%d...',
                 self.args.hostname, self.args.port)
      self._sock, addr = self._accept_sock.accept()
      self._sock.settimeout(socket_common.SOCKET_TIMEOUT)
      self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF,
                            socket_common.SOCKET_BUFFER_SIZE)
      self.info('Connected with %s:%d' % (addr[0], addr[1]))
      self._accept_sock.shutdown(socket.SHUT_RDWR)
      self._accept_sock.close()
      # Receive qing.
      # We use recvfrom because we need to control unittest mock.
      received_char, _unused_addr = self._sock.recvfrom(1)
      self.debug('Received a char: %s', received_char)
      if not received_char == socket_common.QING:
        self.info('Invalid qing: %s', received_char)
        self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()
        return False
      # Send qong.
      self._sock.sendall(socket_common.QING_RESPONSE)
      return True
    except Exception:
      return False

  def Main(self):
    """Main Thread of the plugin."""
    while not self.IsStopping():
      # Since we need to know the number of events being sent before beginning
      # the transmission, cache events in memory before making the connection.
      events = []
      event_stream = self.NewStream()
      if not event_stream:
        self.Sleep(1)
        continue
      for event in event_stream.iter(timeout=self.args.timeout,
                                     count=self.args.batch_size):
        events.append(event)

      # If no events are available, don't bother sending an empty transmission.
      if not events:
        self.debug('No events available for transmission')
        event_stream.Commit()
        continue

      # Accepts a connection only when we have some events. Or input pull socket
      # will connect, wait event number and time out.
      success = False
      while not success:
        for unused_i in range(_ACCEPT_LOG_INTERVAL):
          success = self.GetSocket()
          if self.IsStopping():
            event_stream.Abort()
            return
          if success:
            break
        if not success:
          self.warning('No connection when listening')

      sender = output_socket.OutputSocketSender(
          self.logger.name, self._sock, self)
      if sender.ProcessRequest(events):
        event_stream.Commit()
      else:
        event_stream.Abort()


if __name__ == '__main__':
  plugin_base.main()
