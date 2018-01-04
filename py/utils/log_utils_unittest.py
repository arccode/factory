#!/usr/bin/env python
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import log_utils


class NoisyLoggerTest(unittest.TestCase):

  class Counter(object):

    def __init__(self):
      self.counter = 0

    def Call(self, message):
      del message  # Unused.
      self.counter += 1

  def testUnlimited(self):
    c = self.Counter()
    a = log_utils.NoisyLogger(c.Call)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('different')
    self.assertEquals(c.counter, 2)
    a.Log('different')
    self.assertEquals(c.counter, 2)

  def testSupressLimit(self):
    c = self.Counter()
    a = log_utils.NoisyLogger(c.Call, 3)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 1)
    a.Log('test')
    self.assertEquals(c.counter, 2)
    a.Log('test')
    self.assertEquals(c.counter, 2)
    a.Log('test')
    self.assertEquals(c.counter, 2)
    a.Log('test')
    self.assertEquals(c.counter, 2)
    a.Log('test')
    self.assertEquals(c.counter, 3)
    a.Log('different')
    self.assertEquals(c.counter, 4)
    a.Log('different')
    self.assertEquals(c.counter, 4)


if __name__ == '__main__':
  unittest.main()
