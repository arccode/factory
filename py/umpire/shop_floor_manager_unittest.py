#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.shop_floor_manager import ShopFloorManager


class ShopFloorManagerTest(unittest.TestCase):
  def testOnlyOnePort(self):
    m = ShopFloorManager(9001, 9001)
    port, token = m.Allocate('b1')
    self.assertEqual(9001, port)
    self.assertRegexpMatches(token, r'[0-9a-f]{8}')

    self.assertTupleEqual((port, token), m.GetHandler('b1'))
    self.assertListEqual([(9001, 'b1')], m.GetPortMapping())
    self.assertListEqual([('b1', '/shop_floor/9001/' + token)],
                         m.GetBundleHandlerMapping())

    self.assertTupleEqual((None, None), m.GetHandler('something_else'))

  def testAllocatePortUnavailable(self):
    m = ShopFloorManager(9001, 9001)
    port, token = m.Allocate('b1')
    self.assertTupleEqual((port, token), m.GetHandler('b1'))
    self.assertEqual(9001, port)
    # Allocate b2 failed: no port.
    self.assertTupleEqual((None, None), m.Allocate('b2'))
    self.assertListEqual([(9001, 'b1')], m.GetPortMapping())
    self.assertListEqual([('b1', '/shop_floor/9001/' + token)],
                         m.GetBundleHandlerMapping())


  def testAllocateTwice(self):
    # Give 3 free ports.
    m = ShopFloorManager(9001, 9003)
    port_b1_1, token_b1_1 = m.Allocate('b1')
    port_b1_2, token_b1_2 = m.Allocate('b1')

    self.assertNotEqual(port_b1_1, port_b1_2)
    self.assertNotEqual(token_b1_1, token_b1_2)

    # GetHandler returns last allocated port, token.
    self.assertTupleEqual((port_b1_2, token_b1_2),
                          m.GetHandler('b1'))

    self.assertEqual(1, len(m.GetAvailablePorts()))

    unused_port_b2, token_b2 = m.Allocate('b2')
    self.assertEqual(0, len(m.GetAvailablePorts()))

    # Run out of ports.
    self.assertTupleEqual((None, None), m.Allocate('b2'))

    # Current status:
    self.assertListEqual([(9001, 'b1'), (9002, 'b1'), (9003, 'b2')],
                         m.GetPortMapping())
    self.assertListEqual([('b1', '/shop_floor/9002/' + token_b1_2),
                          ('b2', '/shop_floor/9003/' + token_b2)],
                         m.GetBundleHandlerMapping())

  def testAllocateRelease(self):
    # Give 2 free ports.
    m = ShopFloorManager(9001, 9002)
    (port1, token1) = m.Allocate('b1')
    (port2, token2) = m.Allocate('b2')

    self.assertTupleEqual((port1, token1), m.GetHandler('b1'))
    self.assertEqual(0, len(m.GetAvailablePorts()))

    m.Release(port1)
    self.assertEqual(1, len(m.GetAvailablePorts()))
    self.assertTupleEqual((None, None), m.GetHandler('b1'))
    self.assertTupleEqual((port2, token2), m.GetHandler('b2'))
    self.assertListEqual([(9001, None), (9002, 'b2')], m.GetPortMapping())
    self.assertListEqual([('b2', '/shop_floor/9002/' + token2)],
                         m.GetBundleHandlerMapping())

    m.Release(port2)
    self.assertListEqual([9001, 9002], m.GetAvailablePorts())
    self.assertListEqual([(9001, None), (9002, None)], m.GetPortMapping())
    self.assertListEqual([], m.GetBundleHandlerMapping())


if __name__ == '__main__':
  unittest.main()

