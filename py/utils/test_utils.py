# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''Test-related utilities...'''

import SocketServer

def FindUnusedTCPPort():
  '''Returns an unused TCP port for testing.'''
  server = SocketServer.TCPServer(('localhost', 0),
                                  SocketServer.BaseRequestHandler)
  return server.server_address[1]
