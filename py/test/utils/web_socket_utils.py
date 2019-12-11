# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Web socket related utilities."""

import base64
import hashlib
import http.client
import logging


from cros.factory.external import ws4py


def WebSocketHandshake(request):
  """Takes a HTTP request and upgrades it to web socket connection.

  Args:
    request: A RequestHandler object containing the request.

  Returns:
    True if the connection is upgraded successfully. Otherwise, False.
  """
  def send_error(msg):
    logging.error('Unable to start WebSocket connection: %s', msg)
    request.send_response(400, msg)
    request.end_headers()

  # Can encode utf-8, check ws4py/server/cherrypyserver.py +150
  encoded_key = request.headers.get('Sec-WebSocket-Key').encode('utf-8')

  if (request.headers.get('Upgrade') != 'websocket' or
      request.headers.get('Connection') != 'Upgrade' or
      not encoded_key):
    send_error('Missing/unexpected headers in WebSocket request')
    return False

  key = base64.b64decode(encoded_key)
  # Make sure the key is 16 characters, as required by the
  # WebSockets spec (RFC6455).
  if len(key) != 16:
    send_error('Invalid key length')
    return False

  version = request.headers.get('Sec-WebSocket-Version')
  if not version or version not in [str(x) for x in ws4py.WS_VERSION]:
    send_error('Unsupported WebSocket version %s' % version)
    return False

  request.send_response(http.client.SWITCHING_PROTOCOLS)
  request.send_header('Upgrade', 'websocket')
  request.send_header('Connection', 'Upgrade')
  request.send_header(
      'Sec-WebSocket-Accept',
      base64.b64encode(hashlib.sha1(
          encoded_key + ws4py.WS_KEY).digest()).decode('utf-8'))
  request.end_headers()
  request.wfile.flush()

  return True
