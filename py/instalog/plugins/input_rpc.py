#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input RPC plugin.

Waits for events from an output RPC plugin running on another Instalog node.
"""

from __future__ import print_function

import base64
import tempfile
import threading
import zlib

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import plugin_base
from instalog.utils.arg_utils import Arg
from instalog.utils import file_utils

# pylint: disable=no-name-in-module
from instalog.external.jsonrpclib import SimpleJSONRPCServer


_DEFAULT_HOSTNAME = '0.0.0.0'
_DEFAULT_PORT = 8880


class InputRPC(plugin_base.InputPlugin):

  ARGS = [
      Arg('hostname', (str, unicode),
          'Hostname that RPC server should bind to.',
          optional=True, default=_DEFAULT_HOSTNAME),
      Arg('port', int, 'Port that RPC server should bind to.',
          optional=True, default=_DEFAULT_PORT)
  ]

  def __init__(self, *args, **kwargs):
    # Store reference to the JSON RPC server.
    self.server = None
    self.server_thread = None
    super(InputRPC, self).__init__(*args, **kwargs)

  def SetUp(self):
    """Sets up the plugin."""
    # Start the JSON RPC server.  If the port is already used, an exception will
    # be thrown, and plugin will be taken down.
    # TODO(kitching): Writes log messages for every HTTP request.  Figure out
    #                 how to suppress these messages.
    self.server = SimpleJSONRPCServer.SimpleJSONRPCServer(
        (self.args.hostname, self.args.port))
    self.server.register_function(self.RemoteEmit)
    self.server.register_function(self.Ping)
    self.server_thread = threading.Thread(target=self.server.serve_forever)
    self.server_thread.start()

  def TearDown(self):
    """Tears down the plugin."""
    # Stop the JSON RPC server.
    # shutdown() waits until any executing requests finish.
    if self.server:
      self.server.shutdown()
      self.server.server_close()
    else:
      self.warning('Stop: RPC server was never started')

  def Ping(self):
    """Returns 'pong' to verify the connection to this RPC server."""
    return 'pong'

  def RemoteEmit(self, serialized_events):
    """Emits events remotely."""
    # TODO(kitching): Figure out a way to turn down transfers immediately
    #                 when plugin is paused.

    # Create the temporary directory for attachments.
    with file_utils.TempDirectory(prefix='input_rpc_') as tmp_dir:
      self.debug('Temporary directory for attachments: %s', tmp_dir)

      events = []
      for event in serialized_events:
        event = datatypes.Event.Deserialize(event)
        for att_id, att_data in event.attachments.iteritems():
          with tempfile.NamedTemporaryFile(
              'w', dir=tmp_dir, delete=False) as f:
            f.write(zlib.decompress(base64.b64decode(att_data['value'])))
            event.attachments[att_id] = f.name
        events.append(event)
      self.info('Received %d events', len(events))
      return self.Emit(events)


if __name__ == '__main__':
  plugin_base.main()
