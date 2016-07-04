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
import os
import time

import instalog_common  # pylint: disable=W0611
from instalog import plugin_base
from instalog.utils.arg_utils import Arg


_DEFAULT_BATCH_SIZE = 5
_DEFAULT_TIMEOUT = 5
_DEFAULT_PORT = 8880
_DEFAULT_THRESHOLD_BYTES = 4 * 1024 * 1024  # 4mb
_DEFAULT_MAX_BYTES = 16 * 1024 * 1024  # 16mb


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

  def Start(self):
    """Stores handler to input RPC server."""
    self.rpc_server = jsonrpclib.Server(
        'http://%s:%d' % (self.args.hostname, self.args.port))

  def Main(self):
    """Main thread of the plugin."""
    while not self.IsStopping():
      event_stream = self.NewStream()
      if not event_stream:
        # TODO(kitching): Find a better way to block the plugin when we are in
        #                 one of the PAUSING, PAUSED, or UNPAUSING states.
        time.sleep(1)
        continue

      # Get all current events from the EventStream object.
      events = []
      total_size = 0
      for event in event_stream.iter(timeout=self.args.timeout,
                                     count=self.args.batch_size):
        events.append(event)
        self.debug('len(events) = %d', len(events))
        for att_id, att_path in event.attachments.iteritems():
          total_size += os.path.getsize(att_path)
        if total_size > self.args.threshold_bytes:
          # We have enough data to send.
          self.info('Total attachment size %d > %d, transmit batch',
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
        time.sleep(1)
        continue

      # Send to input RPC server.
      rpc_success = False
      if events:
        start_time = time.time()
        serialized_events = []
        for event in events:
          for att_id, att_path in event.attachments.iteritems():
            # Read in the attachment and replace the path with file content.
            # We are currently not doing any compression.
            with open(att_path) as f:
              event.attachments[att_id] = {
                  '__filedata__': True,
                  'value': base64.b64encode(f.read())}
          serialized_events.append(event.Serialize())

        try:
          rpc_success = self.rpc_server.RemoteEmit(serialized_events)
          rpc_result_str = 'success' if rpc_success else 'failure'
        except Exception as e:
          if 'Connection refused' in str(e):
            rpc_result_str = 'connection refused'
          else:
            rpc_result_str = 'unexpected exception'
            self.exception(e)
        self.info('Pack and transmit %d events in %.2fs: %s',
                  len(events), time.time() - start_time, rpc_result_str)

      if rpc_success:
        # Commit these events.
        commit_result_str = 'success' if event_stream.Commit() else 'failure'
        self.info('Commit %d events: %s', len(events), commit_result_str)
      else:
        self.info('Abort %d events', len(events))
        event_stream.Abort()
        # TODO(kitching): Find a better way to slow down the plugin in the case
        #                 that it repeatedly aborts.
        time.sleep(1)


if __name__ == '__main__':
  plugin_base.main()
