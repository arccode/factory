#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input RPC plugin.

Waits for events from an output RPC plugin running on another Instalog node.
"""

from __future__ import print_function

from jsonrpclib import SimpleJSONRPCServer

import base64
import os
import shutil
import tempfile
import threading
import zlib

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import plugin_base
from instalog.utils.arg_utils import Arg


_DEFAULT_HOSTNAME = '0.0.0.0'
_DEFAULT_PORT = 8880


class InputRPC(plugin_base.InputPlugin):

  ARGS = [
      Arg('hostname', (str, unicode), 'Hostname that RPC server should bind to.',
          optional=True, default=_DEFAULT_HOSTNAME),
      Arg('port', int, 'Port that RPC server should bind to.',
          optional=True, default=_DEFAULT_PORT)
  ]

  def __init__(self, *args, **kwargs):
    # Store reference to the JSON RPC server.
    self.server = None
    super(InputRPC, self).__init__(*args, **kwargs)

  def Start(self):
    """Starts the plugin."""
    # Create the temporary directory for attachments.
    self._tmp_dir = tempfile.mkdtemp(prefix='input_rpc_')
    self.info('Temporary directory for attachments: %s', self._tmp_dir)

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

  def Stop(self):
    """Stops the plugin."""
    # Stop the JSON RPC server.
    # shutdown() waits until any executing requests finish.
    if self.server:
      self.server.shutdown()
      self.server.server_close()
    else:
      self.warning('Stop: RPC server was never started')

    # Remove the temporary directory.
    shutil.rmtree(self._tmp_dir)

  def Ping(self):
    """Returns 'pong' to verify the connection to this RPC server."""
    return 'pong'

  def RemoteEmit(self, serialized_events):
    """Emits events remotely."""
    # TODO(kitching): Figure out a way to turn down transfers immediately
    #                 when plugin is paused.
    events = []
    for event in serialized_events:
      event = datatypes.Event.Deserialize(event)
      for att_id, att_data in event.attachments.iteritems():
        fd, tmp_path = tempfile.mkstemp(dir=self._tmp_dir)
        # If anything in the 'try' block raises an exception, make sure we
        # close the file handle created by mkstemp.
        try:
          with open(tmp_path, 'w') as f:
            f.write(zlib.decompress(base64.b64decode(att_data['value'])))
        finally:
          os.close(fd)
        event.attachments[att_id] = tmp_path
      events.append(event)
    self.info('Received %d events', len(events))
    # TODO(kitching): Remove files on failure.
    return self.Emit(events)


if __name__ == '__main__':
  plugin_base.main()
