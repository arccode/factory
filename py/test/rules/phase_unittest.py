#!/usr/bin/env python2
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.rules import phase
from cros.factory.test.rules.phase import Phase
from cros.factory.test.rules.phase import PHASE_NAMES
from cros.factory.test.rules.phase import PhaseAssertionError


# Allow access to protected members _state_root_for_testing and _current_phase
# for white-box testing.
# pylint: disable=protected-access


class BasicPhaseTest(unittest.TestCase):

  def testBasicOps(self):
    for l in xrange(len(PHASE_NAMES)):
      for r in xrange(len(PHASE_NAMES)):
        left = Phase(PHASE_NAMES[l])
        right = Phase(PHASE_NAMES[r])
        self.assertEquals(left < right, l < r)
        self.assertEquals(left > right, l > r)
        self.assertEquals(left == right, l == r)
        self.assertEquals(left != right, l != r)
        self.assertEquals(left <= right, l <= r)
        self.assertEquals(left >= right, l >= r)

    self.assertEquals(Phase('EVT'), phase.EVT)
    self.assertEquals(phase.EVT, phase.EVT)
    self.assertNotEquals(Phase('DVT'), phase.EVT)

  def testInvalidName(self):
    self.assertRaisesRegexp(
        ValueError, (r"'evt' is not a valid phase name \(valid names are "
                     r'\[PROTO,EVT,DVT,PVT_DOGFOOD,PVT\]\)'), Phase, 'evt')


class PersistentPhaseTest(unittest.TestCase):

  def setUp(self):
    phase._current_phase = None
    phase._state_root_for_testing = tempfile.mkdtemp()

  def tearDown(self):
    shutil.rmtree(phase._state_root_for_testing)
    phase._current_phase = None
    phase._state_root_for_testing = None

  def testDefaultPhase(self):
    self.assertEquals(phase.PVT, phase.GetPhase())

  def testSetGetPhase(self):
    phase.SetPersistentPhase(phase.EVT)
    with open(os.path.join(phase._state_root_for_testing, 'PHASE')) as f:
      self.assertEquals('EVT', f.read())
    self.assertEquals(phase.EVT, phase._current_phase)

    # Set current phase to None to force it to be re-read
    phase._current_phase = None
    self.assertEquals(phase.EVT, phase.GetPhase())
    self.assertEquals(phase.EVT, phase._current_phase)

    # Delete phase file.  It will be read as the strictest possible
    # phase (PVT).
    phase.SetPersistentPhase(None)
    self.assertEquals(None, phase._current_phase)
    self.assertEquals(phase.PVT, phase.GetPhase())
    self.assertEquals(phase.PVT, phase._current_phase)


class AssertionTest(unittest.TestCase):

  def setUp(self):
    phase._current_phase = phase.EVT

  def tearDown(self):
    phase._current_phase = None

  def testAssertionPasses(self):
    # Condition is True, so these always pass.
    phase.AssertStartingAtPhase(phase.PROTO, True, 'msg')
    phase.AssertStartingAtPhase(phase.EVT, True, 'msg')
    phase.AssertStartingAtPhase(phase.DVT, True, 'msg')

  def testAssertionPassesCallable(self):
    # These always pass, but only PROTO and EVT ones get called.
    called = []
    phase.AssertStartingAtPhase(phase.PROTO,
                                lambda: called.append('PROTO') or True, 'msg')
    phase.AssertStartingAtPhase(phase.EVT,
                                lambda: called.append('EVT') or True, 'msg')
    phase.AssertStartingAtPhase(phase.DVT,
                                lambda: called.append('DVT') or True, 'msg')
    self.assertEquals(['PROTO', 'EVT'], called)

  def testAssertionFails(self):
    # Condition is True, so these always pass.
    self.assertRaisesRegexp(
        PhaseAssertionError,
        r'Assertion starting at PROTO failed \(currently in EVT\): msg',
        phase.AssertStartingAtPhase, phase.PROTO, False, 'msg')
    self.assertRaisesRegexp(
        PhaseAssertionError,
        r'Assertion starting at EVT failed \(currently in EVT\): msg',
        phase.AssertStartingAtPhase, phase.EVT, False, 'msg')
    phase.AssertStartingAtPhase(phase.DVT, False, 'msg')  # Not evaluated

  def testAssertionFailsCallable(self):
    # Only PROTO and EVT ones get evaluated and fail.
    called = []
    self.assertRaisesRegexp(
        PhaseAssertionError,
        r'Assertion starting at PROTO failed \(currently in EVT\): msg',
        phase.AssertStartingAtPhase, phase.PROTO,
        lambda: called.append('PROTO'), 'msg')
    self.assertRaisesRegexp(
        PhaseAssertionError,
        r'Assertion starting at EVT failed \(currently in EVT\): msg',
        phase.AssertStartingAtPhase, phase.EVT,
        lambda: called.append('EVT'), 'msg')
    # DVT check is not evaluated
    phase.AssertStartingAtPhase(phase.DVT,
                                lambda: called.append('DVT') or True, 'msg')
    self.assertEquals(['PROTO', 'EVT'], called)

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
