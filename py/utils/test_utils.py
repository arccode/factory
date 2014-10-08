# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test-related utilities."""

from __future__ import print_function

import SocketServer

from contextlib import contextmanager

import factory_common  # pylint: disable=W0611
from cros.factory.utils import net_utils


def FindUnusedTCPPort():
  """Returns an unused TCP port for testing."""
  server = SocketServer.TCPServer((net_utils.LOCALHOST, 0),
                                  SocketServer.BaseRequestHandler)
  return server.server_address[1]


@contextmanager
def StubOutAttributes(obj, **args):
  """Stubs out attributes in an object (e.g., a module).

  The attributes are replaced with the given values, and replaced
  when the context manager exits.

  Args:
    args: Dictionary of attributes to replace and their values.

  Returns:
    A context manager.
  """
  old_values = {}
  for k, v in args.iteritems():
    try:
      old_values[k] = getattr(obj, k)
    except AttributeError:
      pass
    setattr(obj, k, v)

  try:
    yield
  finally:
    for k, v in args.iteritems():
      try:
        setattr(obj, k, old_values[k])
      except KeyError:  # v not in old_values
        delattr(obj, k)
