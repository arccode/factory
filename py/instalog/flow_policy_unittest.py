#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for Instalog Event flow policy."""

import logging
import unittest

from cros.factory.instalog import datatypes
from cros.factory.instalog import flow_policy
from cros.factory.instalog import log_utils


_SAMPLE_TIME = 629467932.000012

_SAMPLE_PROCESS_STAGE1 = datatypes.ProcessStage(
    node_id='node_id1',
    time=_SAMPLE_TIME,
    plugin_id='plugin_id1',
    plugin_type='plugin_type1',
    target=datatypes.ProcessStage.BUFFER)
_SAMPLE_PROCESS_STAGE2 = datatypes.ProcessStage(
    node_id='node_id2',
    time=_SAMPLE_TIME,
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

  def testNegativePosition(self):
    rule1 = flow_policy.HistoryRule(
        node_id='node_id1',
        position=-2)
    self.assertTrue(rule1.MatchEvent(_SAMPLE_EVENT))
    rule2 = flow_policy.HistoryRule(
        node_id='node_id2',
        position=-1)
    self.assertTrue(rule2.MatchEvent(_SAMPLE_EVENT))

  def testPositionMismatch(self):
    rule = flow_policy.HistoryRule(
        node_id='node_id2',
        position=0)
    self.assertFalse(rule.MatchEvent(_SAMPLE_EVENT))


class TestTestlogRule(unittest.TestCase):

  def testMatchEvent(self):
    rule = flow_policy.TestlogRule(type='station.test_run')

    self.assertFalse(rule.MatchEvent(
        datatypes.Event({'type': 'station.message'})))
    self.assertFalse(rule.MatchEvent(
        datatypes.Event({})))

    self.assertTrue(rule.MatchEvent(
        datatypes.Event({'type': 'station.test_run'})))

  def testFlowPolicyAllow(self):
    policy = flow_policy.FlowPolicy(
        allow=[{'rule': 'testlog', 'type': 'station.test_run'}])

    self.assertFalse(policy.MatchEvent(
        datatypes.Event({'type': 'station.message'})))
    self.assertFalse(policy.MatchEvent(
        datatypes.Event({})))

    self.assertTrue(policy.MatchEvent(
        datatypes.Event({'type': 'station.test_run'})))

  def testFlowPolicyDeny(self):
    policy = flow_policy.FlowPolicy(
        allow=[{'rule': 'all'}],
        deny=[{'rule': 'testlog', 'type': 'station.message'},
              {'rule': 'testlog', 'type': 'station.status'}])

    self.assertFalse(policy.MatchEvent(
        datatypes.Event({'type': 'station.message'})))
    self.assertFalse(policy.MatchEvent(
        datatypes.Event({'type': 'station.status'})))

    self.assertTrue(policy.MatchEvent(
        datatypes.Event({})))
    self.assertTrue(policy.MatchEvent(
        datatypes.Event({'type': 'station.test_run'})))


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
