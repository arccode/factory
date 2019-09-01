#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions.approx_match import ApproxMatchFunction


class ApproxMatchTest(unittest.TestCase):
  def testMatchDict(self):
    approx_match = ApproxMatchFunction(
        rule={'foo': 'FOO', 'bar': 'BAR', 'FOO': '!re FOO[0-9]*$',
              'id': '!num < 100'}, max_mismatch=3)

    item = {'foo': 'FOO', 'bar': 'BAR', 'FOO': 'FOO123', 'id': 1}
    res = approx_match.Match(item)
    self.assertApproxMatch(res, True, 4,
                           {'foo': True, 'bar': True, 'FOO': True, 'id': True},
                           item)

    item = {'foo': 'FO', 'bar': 'BAR', 'FOO': 'FOO123', 'id': 1}
    res = approx_match.Match(item)
    self.assertApproxMatch(res, False, 3,
                           {'foo': False, 'bar': True, 'FOO': True, 'id': True},
                           item)

    item = {'foo': 'FO', 'bar': 'BAR', 'FOO': 'FOOa', 'id': 1}
    res = approx_match.Match(item)
    self.assertApproxMatch(res, False, 2,
                           {'foo': False,
                            'bar': True,
                            'FOO': False,
                            'id': True},
                           item)

    item = {'foo': 'FO', 'bar': 'B', 'FOO': 'FOOa', 'id': 100}
    res = approx_match.Match(item)
    self.assertApproxMatch(res, False, 0,
                           {'foo': False,
                            'bar': False,
                            'FOO': False,
                            'id': False},
                           item)

  def testMatchStr(self):
    approx_match = ApproxMatchFunction(rule='!re FOO[0-9]*$')

    item = {'foo': 'FOO123'}
    res = approx_match.Match(item)
    self.assertApproxMatch(res, True, 1, {'foo': True}, item)

    item = {'bar': 'FOOabc'}
    res = approx_match.Match(item)
    self.assertApproxMatch(res, False, 0, {'bar': False}, item)

  def testApproxMatchFilter(self):
    def _GenerateFakeResults(matched_nums):
      return [(None, matched_num, None, None) for matched_num in matched_nums]

    approx_match = ApproxMatchFunction(rule={'a': 'a', 'b': 'b', 'c': 'c',
                                             'd': 'd', 'e': 'e'},
                                       max_mismatch=1)

    match_results = _GenerateFakeResults([0, 1, 2, 3, 4])
    filtered_results = _GenerateFakeResults([4])
    self.assertEqual(approx_match.ApproxMatchFilter(match_results),
                     filtered_results)

    match_results = _GenerateFakeResults([0, 1, 4, 4, 4])
    filtered_results = _GenerateFakeResults([4, 4, 4])
    self.assertEqual(approx_match.ApproxMatchFilter(match_results),
                     filtered_results)

    match_results = _GenerateFakeResults([0, 0, 0, 0, 0])
    filtered_results = []
    self.assertEqual(approx_match.ApproxMatchFilter(match_results),
                     filtered_results)

  def assertApproxMatch(self, res, perfect_match_expect, matched_num_expect,
                        rule_expect, item_expect):
    perfect_match, matched_num, rule, item = res
    self.assertEqual(perfect_match, perfect_match_expect)
    self.assertEqual(matched_num, matched_num_expect)
    self.assertEqual(item, item_expect)
    for rule_name, expect in rule_expect.iteritems():
      self.assertEqual(rule[rule_name]['result'], expect)


if __name__ == '__main__':
  unittest.main()
