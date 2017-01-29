#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input socket plugin.

Waits for events from an output socket plugin running on another Instalog node.

See socket_common.py for protocol definition.
See input_socket_unittest.py for reference examples.
"""

from __future__ import print_function

import hashlib
import os
import shutil
import socket
import tempfile
import threading
import time

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import log_utils
from instalog import plugin_base
from instalog.plugins import socket_common
from instalog.utils.arg_utils import Arg


_DEFAULT_HOSTNAME = '0.0.0.0'


class ChecksumError(Exception):
  """Represents a checksum mismatch."""
  pass


class InputSocket(plugin_base.InputPlugin):

  ARGS = [
      Arg('hostname', (str, unicode), 'Hostname that server should bind to.',
          optional=True, default=_DEFAULT_HOSTNAME),
      Arg('port', int, 'Port that server should bind to.',
          optional=True, default=socket_common.DEFAULT_PORT)
  ]

  # Default class instance variables.
  _sock = None
  _accept_thread = None
  _tmp_dir = None
  _threads = {}

  def SetUp(self):
    """Sets up the plugin."""
    # Create the temporary directory for attachments.
    self._tmp_dir = tempfile.mkdtemp(prefix='input_socket_')
    self.info('Temporary directory for attachments: %s', self._tmp_dir)

    self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.debug('Socket created')

    # Bind socket.
    try:
      self._sock.bind((self.args.hostname, self.args.port))
    except socket.error as msg:
      self.exception('Bind failed. Error %d: %s' % (msg[0], msg[1]))
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
      for thread in self._threads.keys():
        if not thread.is_alive():
          del self._threads[thread]

      conn, addr = self._sock.accept()
      conn.settimeout(socket_common.SOCKET_TIMEOUT)

      # Since sock.accept is a blocking call, check for the STOPPING state
      # afterwards.  TearDown may have purposely initiated a connection in order
      # to break the sock.accept call.
      if self.IsStopping():
        conn.close()
        return

      t = InputSocketRequest(self.logger, conn, addr, self, self._tmp_dir)
      t.daemon = False
      self._threads[t] = True
      t.start()

  def TearDown(self):
    """Tears down the plugin."""
    if self._sock:
      self.info('Closing socket and shutting down accept thread...')
      # Initiate a fake connection in order to break a blocking sock.accept call.
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

    self.info('Join on %d InputSocketRequest threads...', len(self._threads))
    for thread in self._threads:
      thread.join()

    # Remove the temporary directory.
    if self._tmp_dir:
      self.info('Removing temporary directory %s...', self._tmp_dir)
      shutil.rmtree(self._tmp_dir)
    else:
      self.warning('TearDown: Temporary directory was never created')

    self.info('Shutdown complete')


class InputSocketRequest(log_utils.LoggerMixin, threading.Thread):
  """Represents a request from an output socket plugin."""

  def __init__(self, logger, conn, addr, plugin_api, tmp_dir):
    # log_utils.LoggerMixin creates shortcut functions for convenience.
    self.logger = logger
    self._conn = conn
    self._addr = addr
    self._plugin_api = plugin_api
    self._tmp_dir = tmp_dir
    super(InputSocketRequest, self).__init__()

  def run(self):
    """Run method of the thread."""
    self.info('Connected with %s:%d' % (self._addr[0], self._addr[1]))
    try:
      events = []
      num_events = self.RecvInt()
      if num_events == 0:
        return self.Pong()
      total_bytes = 0
      start_time = time.time()
      for event_id in range(num_events):
        event_bytes, event = self.RecvEvent()
        self.debug('Received event[%d] size: %.2f kB',
                   event_id, event_bytes / 1024.0)
        total_bytes += event_bytes
        events.append(event)
      elapsed_time = time.time() - start_time
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
    if not self._plugin_api.Emit(events):
      self.error('Unable to emit, aborting')
      self.Close()
      return

    try:
      self.debug('Success; sending emit-success to transmitting side (syn-ack)')
      self._conn.sendall(socket_common.EMIT_SUCCESS_CHAR)
    except Exception:
      self.exception('Received events were emitted successfully, but failed '
                     'to confirm success with remote side: duplicate data '
                     'may occur')
    finally:
      total_kbytes = total_bytes / 1024.0
      self.info('Received %d events, total %.2f kB in %.1f sec (%.2f kB/sec)',
                len(events), total_kbytes, elapsed_time,
                total_kbytes / elapsed_time)
      self.Close()

  def Pong(self):
    """Called for an empty transfer (0 events)."""
    self.info('Empty transfer: Pong!')
    try:
      self._conn.sendall(socket_common.PING_RESPONSE)
    except Exception:
      pass
    finally:
      self.Close()

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
    buf = ''
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
      recv_size = min(total - progress, socket_common.CHUNK_SIZE)
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
    if remote_checksum != local_checksum:
      raise ChecksumError

  def RecvField(self):
    """Returns the next field in socket stream."""
    buf = ''
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
    event = datatypes.Event.Deserialize(event_field)

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
    fd, tmp_path = tempfile.mkstemp(dir=self._tmp_dir)
    # If anything in the 'try' block raises an exception, make sure we
    # close the file handle created by mkstemp.
    try:
      with open(tmp_path, 'w') as f:
        for progress, bin_part in self.RecvFieldParts():
          f.write(bin_part)
    finally:
      os.close(fd)
    return progress, tmp_path


if __name__ == '__main__':
  plugin_base.main()
