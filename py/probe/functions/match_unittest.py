#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import match


class MatchedRuleTest(unittest.TestCase):
  def testMatchPlainText(self):
    rule = match.MatchFunction(rule={'foo': 'FOO', 'bar': 'BAR'})
    self.assertTrue(rule.Match({'foo': 'FOO', 'bar': 'BAR'}))
    self.assertTrue(rule.Match({'foo': 'FOO', 'bar': 'BAR', 'extra': 'FINE'}))
    self.assertFalse(rule.Match({'foo': 'FOO1', 'bar': 'bar'}))
    self.assertFalse(rule.Match({'foo': 'FOO1'}))
    self.assertFalse(rule.Match({'foo': 'FOO'}))

  def testMatchRegex(self):
    rule = match.MatchFunction(rule={'foo': '!re FOO[0-9]*',
                                     'bar': '!re BAR[S|s]'})
    self.assertTrue(rule.Match({'foo': 'FOO', 'bar': 'BARs'}))
    self.assertTrue(rule.Match({'foo': 'FOO123', 'bar': 'BARS'}))
    self.assertTrue(rule.Match({'foo': 'FOO0', 'bar': 'BARS', 'extra': 'OK'}))

  def testMatchSingleValue(self):
    rule = match.MatchFunction(rule='!re FOO[0-9]*')
    self.assertTrue(rule.Match({'foo': 'FOO'}))
    self.assertTrue(rule.Match({'idx': 'FOO123'}))
    self.assertFalse(rule.Match({'foo': 'FOO123', 'extra': 'NOT OK'}))

  def testMatchNumberComparison(self):
    rule = match.MatchFunction(rule='!num == 100')
    self.assertFalse(rule.Match({'foo': '0'}))
    self.assertTrue(rule.Match({'foo': '100'}))
    self.assertFalse(rule.Match({'foo': '200'}))
    self.assertFalse(rule.Match({'foo': '200k'}))  # not a valid float number

    rule = match.MatchFunction(rule='!num <= 100')
    self.assertTrue(rule.Match({'foo': '0'}))
    self.assertTrue(rule.Match({'foo': '100'}))
    self.assertFalse(rule.Match({'foo': '200'}))
    self.assertFalse(rule.Match({'foo': '200k'}))  # not a valid float number

    rule = match.MatchFunction(rule='!num < 100')
    self.assertTrue(rule.Match({'foo': '0'}))
    self.assertFalse(rule.Match({'foo': '100'}))
    self.assertFalse(rule.Match({'foo': '200'}))
    self.assertFalse(rule.Match({'foo': '200k'}))  # not a valid float number

    rule = match.MatchFunction(rule='!num > 100')
    self.assertFalse(rule.Match({'foo': '0'}))
    self.assertFalse(rule.Match({'foo': '100'}))
    self.assertTrue(rule.Match({'foo': '200'}))
    self.assertFalse(rule.Match({'foo': '200k'}))  # not a valid float number

    rule = match.MatchFunction(rule='!num >= 100')
    self.assertFalse(rule.Match({'foo': '0'}))
    self.assertTrue(rule.Match({'foo': '100'}))
    self.assertTrue(rule.Match({'foo': '200'}))
    self.assertFalse(rule.Match({'foo': '200k'}))  # not a valid float number

    rule = match.MatchFunction(rule='!num != 100')
    self.assertTrue(rule.Match({'foo': '0'}))
    self.assertFalse(rule.Match({'foo': '100'}))
    self.assertTrue(rule.Match({'foo': '200'}))
    self.assertFalse(rule.Match({'foo': '200k'}))  # not a valid float number


if __name__ == '__main__':
  unittest.main()
