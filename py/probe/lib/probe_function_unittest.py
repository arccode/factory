#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.lib import probe_function


class ProbeFunctionTest(unittest.TestCase):
  class MockProbeFunction(probe_function.ProbeFunction):
    def Probe(self):
      return {'result': 'FOO'}

  class MockProbeFunction2(probe_function.ProbeFunction):
    def Probe(self):
      return [{'result': 'FOO1'}, {'result': 'FOO2'}]

  def testProbeFunction(self):
    """Probe function returns a dict."""
    func = self.MockProbeFunction()
    self.assertEquals(func(function.INITIAL_DATA), [{'result': 'FOO'}])
    self.assertEquals(func([{'other': 'BAR'}]),
                      [{'result': 'FOO', 'other': 'BAR'}])
    self.assertEquals(func([{'other': 'BAR1'},
                            {'other': 'BAR2'}]),
                      [{'result': 'FOO', 'other': 'BAR1'},
                       {'result': 'FOO', 'other': 'BAR2'}])

  def testProbeFunctionWithList(self):
    """Probe function returns a list of dict."""
    func = self.MockProbeFunction2()
    self.assertEquals(func(function.INITIAL_DATA),
                      [{'result': 'FOO1'}, {'result': 'FOO2'}])
    self.assertEquals(func([{'other': 'BAR1'},
                            {'other': 'BAR2'}]),
                      [{'result': 'FOO1', 'other': 'BAR1'},
                       {'result': 'FOO1', 'other': 'BAR2'},
                       {'result': 'FOO2', 'other': 'BAR1'},
                       {'result': 'FOO2', 'other': 'BAR2'}])

  def testNotProbeWhenFail(self):
    func = self.MockProbeFunction()
    func.Probe = mock.MagicMock()
    ret = func(function.NOTHING)
    func.Probe.assert_not_called()
    self.assertEquals(ret, function.NOTHING)


if __name__ == '__main__':
  unittest.main()
