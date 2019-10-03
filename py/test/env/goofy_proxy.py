# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from jsonrpclib import jsonrpc

from cros.factory.utils import net_utils

# Default address and port that goofy server will bind on.
DEFAULT_GOOFY_PORT = 0x0FAC
DEFAULT_GOOFY_ADDRESS = net_utils.LOCALHOST
DEFAULT_GOOFY_BIND = net_utils.INADDR_ANY

# The URL for state and goofy server.
# TODO(shunhsingou): currently goofy_rpc and state use the same instance and
# URL path. Separate them in the future.
STATE_URL = '/goofy'
GOOFY_RPC_URL = '/goofy'
GOOFY_SERVER_URL = '/'


def GetRPCProxy(address=None, port=None, url=GOOFY_RPC_URL):
  """Gets an instance (for client side) to access the goofy server.

  Args:
    address: Address of the server to be connected.
    port: Port of the server to be connected.
    url: Target URL for the RPC server. Default to Goofy RPC.
  """
  address = address or DEFAULT_GOOFY_ADDRESS
  port = port or DEFAULT_GOOFY_PORT
  return jsonrpc.ServerProxy(
      'http://%s:%d%s' % (address, port, url))
