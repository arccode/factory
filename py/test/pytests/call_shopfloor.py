# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import types
import unittest


import factory_common  # pylint: disable=W0611
from cros.factory.test import factory, shopfloor
from cros.factory.test.args import Arg


class Env(object):
  def __init__(self):
    self.state = factory.get_state_instance()
    self.shopfloor = shopfloor

  def GetMACAddress(self, interface):
    return open('/sys/class/net/%s/address' % interface).read().strip()


class CallShopfloor(unittest.TestCase):
  ARGS = [
    Arg('method', str,
        'Name of shopfloor method to call'),
    Arg('args', (list, types.FunctionType),
        'Method arguments')
  ]

  def runTest(self):
    env = type('Env', (), dict(state=factory.get_state_instance(),
                               shopfloor=shopfloor))
    if isinstance(self.args.args, types.FunctionType):
      self.args.args = self.args.args(env)
      self.assertTrue(isinstance(self.args.args, types.FunctionType))

    method = getattr(shopfloor.get_instance(detect=True), self.args.method)
    method(*self.args.args)
