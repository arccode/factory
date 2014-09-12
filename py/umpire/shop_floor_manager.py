# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Manages ShopFloorHandler FastCGI port binding.

See ShopFloorManager for details."""

import binascii
import os

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common


class ShopFloorManager(object):
  """Manages ShopFloorHandler FastCGI port binding.

  For each bundle, it has a ShopFloorHandler process to handle its DUTs'
  ShopFloor requests. For Umpire server, it has a pool of local ports for
  ShopFloorHandler to bind. More over, when deploying a config, the server
  gives each active bundle's ShopFloorHandler instance a token. The token
  is used to identify a specific deploy version. A DUT gets resource map once
  and caches shop_floor_handler path to use. When a DUT sends a ShopFloorHandler
  requests and gets 405 response, it means the path is invalid and the DUT needs
  to refresh resource map again.
  """
  def __init__(self, port_begin, port_end):
    # Bundle ID to (port, token) mapping.
    self._bundle_port = dict()

    # Port to bundle ID mapping.
    self._port_bundle = dict()

    # Handler port range, inclusive.
    if port_begin > port_end:
      raise ValueError('port_begin %d > port_end %d' % (port_begin, port_end))
    self._port_begin = port_begin
    self._port_end = port_end

    # Set of available ports.
    self._available_ports = set(range(port_begin, port_end + 1))

  def _GetToken(self):
    return binascii.b2a_hex(os.urandom(4))

  def Reset(self):
    """Resets port bindings."""
    self._bundle_port.clear()
    self._port_bundle.clear()
    self._available_ports = set(range(self._port_begin, self._port_end + 1))

  def Allocate(self, bundle_id):
    """Allocates an unused port for the bundle_id.

    It also generates a token for the bundle_id.

    Returns:
      (port, token) if there's an unused port; otherwise, (None, None).
    """
    if not self._available_ports:
      return (None, None)
    port = self._available_ports.pop()
    token = self._GetToken()
    self._bundle_port[bundle_id] = (port, token)
    self._port_bundle[port] = bundle_id

    return (port, token)

  def GetHandler(self, bundle_id):
    """Gets ShopFloorHandler (port, token) pair for bundle_id.

    Args:
      bundle_id: a bundle ID.

    Returns:
      (port, token) if bundle_id is deployed. Otherwise, (None, None).
    """
    return self._bundle_port.get(bundle_id, (None, None))

  def Release(self, port):
    """Releases a port.

    If the port's associated bundle_id is in self._bundle_port and its mapping
    port is the port we want to release, the mapping is also released.
    """
    self._available_ports.add(port)
    bundle_id = self._port_bundle.pop(port, None)
    if bundle_id:
      port_assoc_bundle_id = self._bundle_port.get(bundle_id)[0]
      if port == port_assoc_bundle_id:
        self._bundle_port.pop(bundle_id, None)

  def GetPortMapping(self):
    """Retrieves list of (port, bundle_id) pairs in ShopFloor port pool.

    If a port is not assigned, the bundle_id is None.
    Note that a bundle_id may associate to multiple port. It is because
    a bundle_id may allocate more than once. And port-bundle mapping can be
    removed by using Release().

    Returns:
       List of (port, bundle_id) pairs in ShopFloor port pool.
    """
    return [(p, self._port_bundle.get(p))
            for p in xrange(self._port_begin, self._port_end + 1)]

  def GetBundleHandlerMapping(self):
    """Retrieves list of (bundle_id, handler_path).

    handler_path = handler_base/port/token

    Returns:
      List of (bundle_id, handler_path).
    """
    handler_pattern = common.HANDLER_BASE + '/%d/%s'
    return [(bundle_id, handler_pattern % port_token)
            for bundle_id, port_token in self._bundle_port.iteritems()]

  def GetAvailablePorts(self):
    """Returns list of available ports."""
    return sorted(self._available_ports)
