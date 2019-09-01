#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import probe_utils


class ProbeTest(unittest.TestCase):
  _FULL_PROBE_STATEMENTS = {
      'foo': {
          'foo_1': {
              'eval': 'shell:echo fooo',
              'expect': {'shell_raw': 'xxx'}
          },
          'foo_2': {
              'eval': 'shell:echo fooo',
          }
      },
      'bar': {
          'bar_1': {
              'eval': 'shell:echo barr',
              'expect': {'shell_raw': 'barr'},
              'information': {'key1': 'value1'}
          }
      }
  }
  _FULL_EXPECTED_VALUE = {
      'foo': [
          {'name': 'foo_2', 'values': {'shell_raw': 'fooo'}}
      ],
      'bar': [
          {'name': 'bar_1', 'values': {'shell_raw': 'barr'},
           'information': {'key1': 'value1'}}
      ]
  }

  def testNormal(self):
    self.assertEqual(probe_utils.Probe(self._FULL_PROBE_STATEMENTS),
                     self._FULL_EXPECTED_VALUE)

  def testProbeNoComps(self):
    self.assertEqual(probe_utils.Probe(self._FULL_PROBE_STATEMENTS, comps=[]),
                     {})

  def testProbeSomeComps(self):
    expected_value = copy.deepcopy(self._FULL_EXPECTED_VALUE)
    expected_value.pop('foo')
    self.assertEqual(probe_utils.Probe(self._FULL_PROBE_STATEMENTS,
                                       comps=['bar']), expected_value)


if __name__ == '__main__':
  unittest.main()
