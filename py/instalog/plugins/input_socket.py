#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input socket plugin.

Waits for events from an output socket plugin running on another Instalog node.

See socket_common.py for protocol definition.
See input_socket_unittest.py for reference examples.
"""

import hashlib
import logging
import socket
import tempfile
import threading
import time

from cros.factory.instalog import datatypes
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import socket_common
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils


_DEFAULT_HOSTNAME = '0.0.0.0'


class ChecksumError(Exception):
  """Represents a checksum mismatch."""


class InputSocket(plugin_base.InputPlugin):

  ARGS = [
      Arg('hostname', str, 'Hostname that server should bind to.',
          default=_DEFAULT_HOSTNAME),
      Arg('port', int, 'Port that server should bind to.',
          default=socket_common.DEFAULT_PORT)
  ]

  def __init__(self, *args, **kwargs):
    self._sock = None
    self._accept_thread = None
    self._threads = {}
    super(InputSocket, self).__init__(*args, **kwargs)

  def SetUp(self):
    """Sets up the plugin."""
    self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.debug('Socket created')

    # Bind socket.
    try:
      self._sock.bind((self.args.hostname, self.args.port))
    except socket.error as e:
      self.exception('Bind failed. Error : %s' % e)
      raise
    self.debug('Socket bind complete')

    # Queue up to 5 requests.
    self._sock.listen(5)
    self.info('Socket now listening on %s:%d...',
              self.args.hostname, self.args.port)

    # Start the AcceptLoop thread to wait for incoming connections.
    self._accept_thread = threading.Thread(target=self.AcceptLoop)
    self._accept_thread.daemon = False
    self._accept_thread.start()

  def AcceptLoop(self):
    """Main accept loop which waits for incoming connections."""
    while not self.IsStopping():
      # Purge any finished threads.
      for thread in list(self._threads.keys()):
        if not thread.is_alive():
          del self._threads[thread]

      conn, addr = self._sock.accept()
      self.info('Connected with %s:%d' % (addr[0], addr[1]))
      conn.settimeout(socket_common.SOCKET_TIMEOUT)
      conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF,
                      socket_common.SOCKET_BUFFER_SIZE)

      # Since sock.accept is a blocking call, check for the STOPPING state
      # afterwards.  TearDown may have purposely initiated a connection in order
      # to break the sock.accept call.
      if self.IsStopping():
        conn.close()
        return

      receiver = InputSocketReceiver(self.logger.name, conn, self)
      t = threading.Thread(target=receiver.ProcessRequest)
      t.daemon = False
      self._threads[t] = True
      t.start()

  def TearDown(self):
    """Tears down the plugin."""
    if self._sock:
      self.info('Closing socket and shutting down accept thread...')
      # Initiate a fake connection in order to break a blocking sock.accept
      # call.
      socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
          (self.args.hostname, self.args.port))
      self._sock.shutdown(socket.SHUT_RDWR)
      self._sock.close()
      if self._accept_thread:
        self._accept_thread.join()
      else:
        self.warning('TearDown: AcceptLoop thread was never started')
    else:
      self.warning('TearDown: Socket was never opened')

    self.info('Join on %d InputSocketReceiver threads...', len(self._threads))
    for thread in self._threads:
      thread.join()

    self.info('Shutdown complete')


class InputSocketReceiver(log_utils.LoggerMixin):
  """Receives a request from an output socket plugin."""

  def __init__(self, logger_name, conn, plugin_api):
    # log_utils.LoggerMixin creates shortcut functions for convenience.
    self.logger = logging.getLogger(logger_name)
    self._conn = conn
    self._plugin_api = plugin_api
    self._tmp_dir = None
    super(InputSocketReceiver, self).__init__()

  def ProcessRequest(self):
    """Receives a request from an output socket plugin."""
    # Create the temporary directory for attachments.
    with file_utils.TempDirectory(prefix='input_socket_') as self._tmp_dir:
      self.debug('Temporary directory for attachments: %s', self._tmp_dir)
      try:
        events = []
        num_events = self.RecvInt()
        while num_events == 0:
          self.Pong()
          num_events = self.RecvInt()
        total_bytes = 0
        start_time = time.time()
        for event_id in range(num_events):
          event_bytes, event = self.RecvEvent()
          self.debug('Received event[%d] size: %.2f kB', event_id,
                     event_bytes / 1024)
          total_bytes += event_bytes
          events.append(event)
        receive_time = time.time() - start_time
      except socket.timeout:
        self.error('Socket timeout error, remote connection closed?')
        self.Close()
        return
      except ChecksumError:
        self.error('Checksum mismatch, abort')
        self.Close()
        return
      except Exception:
        self.exception('Unknown exception encountered')
        self.Close()
        return

      self.debug('Notifying transmitting side of data-received (syn)')
      self._conn.sendall(socket_common.DATA_RECEIVED_CHAR)
      self.debug('Waiting for request-emit (ack)...')
      if self._conn.recv(1) != socket_common.REQUEST_EMIT_CHAR:
        self.error('Did not receive request-emit (ack), aborting')
        self.Close()
        return

      self.debug('Calling Emit()...')
      start_time = time.time()
      if not self._plugin_api.Emit(events):
        self.error('Unable to emit, aborting')
        self.Close()
        return
      emit_time = time.time() - start_time

      try:
        self.debug('Success; sending emit-success to transmitting side '
                   '(syn-ack)')
        self._conn.sendall(socket_common.EMIT_SUCCESS_CHAR)
      except Exception:
        self.exception('Received events were emitted successfully, but failed '
                       'to confirm success with remote side: duplicate data '
                       'may occur')
      finally:
        total_kbytes = total_bytes / 1024
        self.info('Received %d events, total %.2f kB in %.1f+%.1f sec '
                  '(%.2f kB/sec)',
                  len(events), total_kbytes, receive_time, emit_time,
                  total_kbytes / receive_time)
        self.Close()

  def Pong(self):
    """Called for an empty transfer (0 events)."""
    self.debug('Empty transfer: Pong!')
    try:
      self._conn.sendall(socket_common.PING_RESPONSE)
    except Exception:
      pass

  def Close(self):
    """Shuts down and closes the socket stream."""
    try:
      self.debug('Closing socket')
      self._conn.shutdown(socket.SHUT_RDWR)
      self._conn.close()
    except Exception:
      self.exception('Error closing socket')

  def RecvItem(self):
    """Returns the next item in socket stream."""
    buf = b''
    while True:
      data = self._conn.recv(1)
      if not data:
        raise socket.timeout
      if data == socket_common.SEPARATOR:
        break
      buf += data
    return buf

  def RecvInt(self):
    """Returns the next integer in socket stream."""
    return int(self.RecvItem())

  def RecvFieldParts(self):
    """Returns a generator to retrieve the next field in socket stream."""
    total = self.RecvInt()
    self.debug('RecvFieldParts total = %d bytes' % total)
    progress = 0
    local_hash = hashlib.sha1()
    while progress < total:
      recv_size = total - progress
      # Recv may return any number of bytes <= recv_size, so it's important
      # to check the size of its output.
      out = self._conn.recv(recv_size)
      if not out:
        raise socket.timeout
      local_hash.update(out)
      progress += len(out)
      yield progress, out

    # Verify SHA1 checksum.
    remote_checksum = self.RecvItem()
    local_checksum = local_hash.hexdigest()
    if remote_checksum.decode('utf-8') != local_checksum:
      raise ChecksumError

  def RecvField(self):
    """Returns the next field in socket stream."""
    buf = b''
    for unused_progress, field in self.RecvFieldParts():
      buf += field
    return buf

  def RecvEvent(self):
    """Returns the next event in socket stream.

    Returns:
      A tuple with (total bytes, Event object)
    """
    total_bytes = 0
    # Retrieve the event itself.
    event_field = self.RecvField()
    total_bytes += len(event_field)
    event = datatypes.Event.Deserialize(event_field.decode('utf-8'))

    # An event is followed by its number of attachments.
    num_atts = self.RecvInt()
    self.debug('num_atts = %d', num_atts)

    for att_index in range(num_atts):
      # Attachment format: <attachment_id> <attachment_data>
      att_id = self.RecvField()
      total_bytes += len(att_id)
      att_size, att_path = self.RecvAttachmentData()
      total_bytes += att_size
      self.debug('Attachment[%d] %s: %d bytes', att_index, att_id, att_size)
      event.attachments[att_id] = att_path
    self.debug('Retrieved event (%d bytes): %s', total_bytes, event)
    return total_bytes, event

  def RecvAttachmentData(self):
    """Receives attachment data and writes to a temporary file on disk.

    Returns:
      A tuple with (total bytes received, temporary path).
    """
    progress = 0
    with tempfile.NamedTemporaryFile('wb', dir=self._tmp_dir,
                                     delete=False) as f:
      for progress, bin_part in self.RecvFieldParts():
        f.write(bin_part)
      return progress, f.name


if __name__ == '__main__':
  plugin_base.main()
