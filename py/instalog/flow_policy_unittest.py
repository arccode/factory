#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for Instalog Event flow policy."""

from __future__ import print_function

import datetime
import logging
import unittest

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import flow_policy
from instalog import log_utils


_SAMPLE_DATETIME = datetime.datetime(1989, 12, 12, 12, 12, 12, 12)

_SAMPLE_PROCESS_STAGE1 = datatypes.ProcessStage(
    node_id='node_id1',
    orig_time=_SAMPLE_DATETIME,
    time=_SAMPLE_DATETIME,
    plugin_id='plugin_id1',
    plugin_type='plugin_type1',
    target=datatypes.ProcessStage.BUFFER)
_SAMPLE_PROCESS_STAGE2 = datatypes.ProcessStage(
    node_id='node_id2',
    orig_time=_SAMPLE_DATETIME,
    time=_SAMPLE_DATETIME,
    plugin_id='plugin_id2',
    plugin_type='plugin_type2',
    target=datatypes.ProcessStage.EXTERNAL)
_SAMPLE_EVENT = datatypes.Event({})
_SAMPLE_EVENT.AppendStage(_SAMPLE_PROCESS_STAGE1)
_SAMPLE_EVENT.AppendStage(_SAMPLE_PROCESS_STAGE2)


class TestFlowPolicy(unittest.TestCase):

  def testFlowPolicyRulesCreation(self):
    policy = flow_policy.FlowPolicy(
        allow=[{'rule': 'history', 'node_id': 'node_id2'}])
    rule = flow_policy.HistoryRule(node_id='node_id2')
    self.assertEqual(policy.allow[0], rule)

  def testEmptyPolicyMatch(self):
    policy = flow_policy.FlowPolicy()
    self.assertFalse(policy.MatchEvent(_SAMPLE_EVENT))

  def testAllRulePolicyMatch(self):
    policy = flow_policy.FlowPolicy(allow=[{'rule': 'all'}])
    self.assertTrue(policy.MatchEvent(_SAMPLE_EVENT))

  def testAllowSingleMatch(self):
    policy = flow_policy.FlowPolicy(
        allow=[{'rule': 'history', 'node_id': 'node_id2'}])
    self.assertTrue(policy.MatchEvent(_SAMPLE_EVENT))

  def testAllowDoubleMatch(self):
    policy = flow_policy.FlowPolicy(
        allow=[{'rule': 'history', 'node_id': 'node_id2'},
                     {'rule': 'history', 'plugin_id': 'plugin_id'}])
    self.assertTrue(policy.MatchEvent(_SAMPLE_EVENT))

  def testAllowDenyMatch(self):
    policy = flow_policy.FlowPolicy(
        allow=[{'rule': 'history', 'node_id': 'node_id2'}],
        deny=[{'rule': 'history', 'plugin_id': 'non_existent'}])
    self.assertTrue(policy.MatchEvent(_SAMPLE_EVENT))

  def testAllowDenyMismatch(self):
    policy = flow_policy.FlowPolicy(
        allow=[{'rule': 'history', 'node_id': 'node_id2'}],
        deny=[{'rule': 'history', 'node_id': 'node_id1'}])
    self.assertFalse(policy.MatchEvent(_SAMPLE_EVENT))


class TestHistoryRule(unittest.TestCase):

  def testSingleAttribute(self):
    rule = flow_policy.HistoryRule(node_id='node_id2')
    self.assertTrue(rule.MatchEvent(_SAMPLE_EVENT))

  def testDoubleAttributeMatch(self):
    rule = flow_policy.HistoryRule(
        node_id='node_id2',
        plugin_id='plugin_id2')
    self.assertTrue(rule.MatchEvent(_SAMPLE_EVENT))

  def testDoubleAttributeMismatch(self):
    rule = flow_policy.HistoryRule(
        node_id='node_id2',
        plugin_id='plugin_id1')
    self.assertFalse(rule.MatchEvent(_SAMPLE_EVENT))

  def testPositionMatch(self):
    rule = flow_policy.HistoryRule(
        node_id='node_id2',
        position=1)
    self.assertTrue(rule.MatchEvent(_SAMPLE_EVENT))

  def testPositionMismatch(self):
    rule = flow_policy.HistoryRule(
        node_id='node_id2',
        position=0)
    self.assertFalse(rule.MatchEvent(_SAMPLE_EVENT))


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG, format=log_utils.LOG_FORMAT)
  unittest.main()
