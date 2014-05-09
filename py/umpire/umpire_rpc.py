# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire RPC base class."""


import factory_common  # pylint: disable=W0611


class UmpireRPC(object):

  """RPC base class.

  Properties:
    env: UmpireEnv object.
  """
  def __init__(self, env):
    super(UmpireRPC, self).__init__()
    self.env = env


def RPCCall(method):
  """Enables the method to be Umpire RPC function.

  Args:
    method: an unbound derived UmpireRPC class method.

  Example:
    class Foo(UmpireRPC):
      def NonRPCFunction():
        pass

      @RPCCall
      def RPCFunction(parameter, ...):
        pass
  """
  method.is_rpc_method = True
  return method
