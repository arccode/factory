# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import xmlrpc.server

# port for the listening the RPC call
INTERACTIVE_RPC_SERVER_PORT = 7601


class GenericInteractiveRpcServer:
  """A simple RPC server interacts with other platform.

  Partner is expected to inherit this and implement the Execute() function.
  """
  def __init__(self, port):
    self._message = 'Initialing RPC Server'
    logging.info('Start DUT server.')
    server = xmlrpc.server.SimpleXMLRPCServer(
        ('0.0.0.0', port), allow_none=True)
    server.register_introspection_functions()
    server.register_function(self.GetStatus)
    server.register_function(self.SetStatus)
    server.register_function(self.Execute)
    # Start the server thread
    server.serve_forever()

  def GetStatus(self):
    return self._message

  def SetStatus(self, message):
    self._message = message
    return True

  def Execute(self, cmd_type, payload):
    # TODO(partner): Determine what action to take based on cmd_type
    # TODO(partner): Extract the info from payload for additional message
    # TODO(partner): Excute the external binary.
    # TODO(partner): Wrap the output in JSON format and return.

    # A simple example:
    #   Remote on the DUT side is calling to list files under root directory.
    #   d = xmlrpclib.ServerProxy('http://localhost:7601')
    #   print d.Execute('LIST', {'path': '/'})
    #
    # Coressponding snippet code here could be:
    # if cmd_type != 'LIST':
    #   raise ValueError('Unrecognized cmd_type %s' % cmd_type)
    # ret = subprocess.check_output(['dir', payload.get('path')])
    # logging.info(json.dumps(ret))
    # return json.dumps(ret)
    raise NotImplementedError

if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  GenericInteractiveRpcServer(INTERACTIVE_RPC_SERVER_PORT)
