#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Output RPC plugin.

Transmits events to an input RPC plugin running on another Instalog node.
"""

from __future__ import print_function

import base64
import jsonrpclib
import socket
import time
import zlib

import instalog_common  # pylint: disable=W0611
from instalog import plugin_base
from instalog.utils import time_utils
from instalog.utils.arg_utils import Arg


# TODO(kitching): Find a better way of doing this, since this timeout
#                 applies for the full duration of a request, even if it
#                 is working.
_SOCKET_TIMEOUT = 120
_CONNECTION_FAILURE_WARN_THRESHOLD = 30
_DEFAULT_BATCH_SIZE = 5000
_DEFAULT_TIMEOUT = 5
_DEFAULT_PORT = 8880
_DEFAULT_THRESHOLD_BYTES = 1 * 1024 * 1024  # 1mb
_DEFAULT_MAX_BYTES = 4 * 1024 * 1024  # 4mb


class OutputRPC(plugin_base.OutputPlugin):

  ARGS = [
      Arg('batch_size', int, 'How many events to queue before transmitting.',
          optional=True, default=_DEFAULT_BATCH_SIZE),
      Arg('timeout', (int, float), 'Timeout to transmit without full batch.',
          optional=True, default=_DEFAULT_TIMEOUT),
      Arg('hostname', (str, unicode), 'Hostname of input RPC server.',
          optional=False),
      Arg('port', int, 'Port of input RPC server.',
          optional=True, default=_DEFAULT_PORT),
      Arg('threshold_bytes', int,
          'Sum of attachment sizes in bytes when a batch should be sent.',
          optional=True, default=_DEFAULT_THRESHOLD_BYTES),
      Arg('max_bytes', int,
          'Maximum sum of attachment sizes in bytes.',
          optional=True, default=_DEFAULT_MAX_BYTES)
  ]

  def SetUp(self):
    """Stores handler to input RPC server."""
    # TODO(kitching): Find a better way of doing this, since this timeout
    #                 applies for the full duration of a request, even if it
    #                 is working.
    socket.setdefaulttimeout(_SOCKET_TIMEOUT)
    self.rpc_server = jsonrpclib.Server(
        'http://%s:%d' % (self.args.hostname, self.args.port))

  def Main(self):
    """Main thread of the plugin."""
    # TODO(kitching): Refactor the main loop into several separate functions.
    # Set connection_attempts to the threshold initially to trigger the warning
    # message if failure is encountered on the first attempt.
    connection_attempts = _CONNECTION_FAILURE_WARN_THRESHOLD
    while not self.IsStopping():
      # Verify that we have a connection available before creating an
      # EventStream object and retrieving events.
      try:
        connection_attempts += 1
        assert self.rpc_server.Ping() == 'pong'
      except Exception:
        # Periodically print an error about the connection problem.
        if connection_attempts >= _CONNECTION_FAILURE_WARN_THRESHOLD:
          self.warning(
              'No connection to target RPC server available (tried %d times)',
              _CONNECTION_FAILURE_WARN_THRESHOLD)
          connection_attempts = 0
        # TODO(kitching): Find a better way to slow down the plugin in the case
        #                 that it repeatedly fails to get a connection to RPC
        #                 server.
        self.Sleep(1)
        continue
      connection_attempts = 0

      # We have a connection to the RPC server.  Create an EventStream.
      event_stream = self.NewStream()
      if not event_stream:
        # TODO(kitching): Find a better way to block the plugin when we are in
        #                 one of the PAUSING, PAUSED, or UNPAUSING states.
        self.Sleep(1)
        continue

      # Get all current events from the EventStream object.
      serialized_events = []
      total_size = 0
      for event in event_stream.iter(timeout=self.args.timeout,
                                     count=self.args.batch_size):
        # First let's read in the attachments, and create a serialized event.
        for att_id, att_path in event.attachments.iteritems():
          # Read in the attachment and replace the path with compressed
          # file content.
          with open(att_path) as f:
            event.attachments[att_id] = {
                '__filedata__': True,
                'value': base64.b64encode(zlib.compress(f.read()))}
        serialized_event = event.Serialize()
        total_size += len(serialized_event)
        serialized_events.append(serialized_event)
        self.debug('len(serialized_events)=%d, total_size=%d',
                   len(serialized_events), total_size)

        if total_size > self.args.threshold_bytes:
          # We have enough data to send.
          self.info('Total data size %d > %d, transmit batch',
                    total_size, self.args.threshold_bytes)
          break
        if total_size > self.args.max_bytes:
          # We have too much data to send; abort.
          break

      if total_size > self.args.max_bytes:
        self.error('Total attachment size %d > %d, abort',
                   total_size, self.args.max_bytes)
        event_stream.Abort()
        # TODO(kitching): Find a better way to slow down the plugin in the case
        #                 that it repeatedly aborts.
        self.Sleep(1)
        continue

      # Send to input RPC server.
      rpc_success = False
      if serialized_events:
        start_time = time_utils.MonotonicTime()
        try:
          rpc_success = self.rpc_server.RemoteEmit(serialized_events)
          rpc_result_str = 'success' if rpc_success else 'failure'
        except Exception as e:
          if 'Connection refused' in str(e):
            rpc_result_str = 'connection refused'
          else:
            rpc_result_str = 'unexpected exception'
            self.exception(e)
        self.info('Pack and transmit %d events (%d KB) in %.2fs: %s',
                  len(serialized_events), total_size / 1024,
                  time_utils.MonotonicTime() - start_time, rpc_result_str)

      if rpc_success:
        # Commit these events.
        self.info('Commit %d events', len(serialized_events))
        event_stream.Commit()
      else:
        if len(serialized_events) > 0:
          self.info('Abort %d events', len(serialized_events))
        event_stream.Abort()
        # TODO(kitching): Find a better way to slow down the plugin in the case
        #                 that it repeatedly aborts.
        self.Sleep(1)


if __name__ == '__main__':
  plugin_base.main()
