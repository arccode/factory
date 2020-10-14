#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for Instalog plugin sandbox.

Ensures that state commands (Start, Stop, Pause, etc.) work correctly, and that
plugins can only run particular Plugin API commands during those different
states.
"""

import logging
import threading
import time
import unittest
from unittest import mock

from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_base
from cros.factory.instalog import plugin_sandbox


class WellBehavedInput(plugin_base.InputPlugin):
  """Basic well-behaved input plugin."""
  def Main(self):
    while not self.IsStopping():
      time.sleep(0.1)


class WellBehavedInputNoMain(plugin_base.InputPlugin):
  """Basic well-behaved input plugin with no Main function."""


class RunawayThreadInput(plugin_base.InputPlugin):
  """Starts a runaway thread which keeps accessing API functions."""

  def _RunawayEmit(self):
    while True:
      self.GetDataDir()
      time.sleep(0.1)

  def SetUp(self):
    t = threading.Thread(target=self._RunawayEmit)
    # No need to set t.daemon = True, since the _RunawayEmit function will stop
    # executing once it receives the UnexpectedAccess exception.
    t.start()


class TestPluginSandbox(unittest.TestCase):

  _plugin_objects = []

  def tearDown(self):
    """Stops any runaway plugins."""
    for p in self._plugin_objects:
      if p.IsLoaded():
        p._event_stream_map = {}  # pylint: disable=protected-access
        p.AdvanceState(True)
        p.Stop(True)

  def _CheckStateCommand(self, p, fail_fns, success_fn,
                         expected_state, sync=False):
    """Runs state commands expecting that they will raise a exceptions."""
    # State changes that should result in failures.
    for fail_fn in fail_fns:
      with self.assertRaises(plugin_base.StateCommandError):
        fail_fn(sync)

    # State change that should succeed.
    success_fn(sync)

    # Check that no state change commands work during transition.
    if not sync:
      for fail_fn in [p.Start, p.Stop, p.Pause, p.Unpause, p.TogglePause]:
        logging.info('Calling %s while in state %s',
                     fail_fn.__name__, p.GetState())
        with self.assertRaises(plugin_base.StateCommandError):
          fail_fn(sync)
      p.AdvanceState(True)

    # Verify new state.
    self.assertEqual(expected_state, p.GetState())

  def _TestStateCommands(self, p, sync):
    """Runs the plugin sandbox through all possible states."""
    # pylint: disable=protected-access
    self.assertEqual(plugin_sandbox.DOWN, p.GetState())

    # Start
    self._CheckStateCommand(
        p,
        fail_fns=[p.Stop, p.Pause, p.Unpause, p.TogglePause],
        success_fn=p.Start,
        expected_state=plugin_sandbox.UP,
        sync=sync)

    # Save the current plugin reference.
    plugin_ref = p._plugin

    # Pause
    self._CheckStateCommand(
        p,
        fail_fns=[p.Start, p.Unpause],
        success_fn=p.Pause,
        expected_state=plugin_sandbox.PAUSED,
        sync=sync)

    # Unpause
    self._CheckStateCommand(
        p,
        fail_fns=[p.Start, p.Pause],
        success_fn=p.Unpause,
        expected_state=plugin_sandbox.UP,
        sync=sync)

    # TogglePause (Pause)
    self._CheckStateCommand(
        p,
        fail_fns=[p.Start, p.Unpause],
        success_fn=p.TogglePause,
        expected_state=plugin_sandbox.PAUSED,
        sync=sync)

    # TogglePause (Unpause)
    self._CheckStateCommand(
        p,
        fail_fns=[p.Start, p.Pause],
        success_fn=p.TogglePause,
        expected_state=plugin_sandbox.UP,
        sync=sync)

    # Stop
    self._CheckStateCommand(
        p,
        fail_fns=[p.Start, p.Unpause],
        success_fn=p.Stop,
        expected_state=plugin_sandbox.DOWN,
        sync=sync)

    # Start
    self._CheckStateCommand(
        p,
        fail_fns=[p.Stop, p.Pause, p.Unpause, p.TogglePause],
        success_fn=p.Start,
        expected_state=plugin_sandbox.UP,
        sync=sync)

    # Ensure that the plugin reference is different.
    self.assertNotEqual(plugin_ref, p._plugin)

    # Pause
    self._CheckStateCommand(
        p,
        fail_fns=[p.Start, p.Unpause],
        success_fn=p.Pause,
        expected_state=plugin_sandbox.PAUSED,
        sync=sync)

    # Stop
    self._CheckStateCommand(
        p,
        fail_fns=[p.Start, p.Pause],
        success_fn=p.Stop,
        expected_state=plugin_sandbox.DOWN,
        sync=sync)

  def testStateCommands(self):
    """Tests all state commands."""
    for plugin_class in [WellBehavedInput, WellBehavedInputNoMain]:
      for sync in [True, False]:
        p = plugin_sandbox.PluginSandbox(
            'plugin_id', _plugin_class=plugin_class)
        self._plugin_objects.append(p)
        self._TestStateCommands(p, sync)

  def testRunawayThread(self):
    """Tests a plugin that starts a runaway thread accessing core functions."""
    # pylint: disable=protected-access
    p = plugin_sandbox.PluginSandbox(
        'plugin_id', _plugin_class=RunawayThreadInput)
    self._plugin_objects.append(p)
    p.Start(True)
    p.Stop(True)

    # Give thread enough time to run one core command and stop due to receiving
    # an UnexpectedAccess exception.
    time.sleep(2)
    self.assertEqual(1, len(p._unexpected_accesses))
    self.assertEqual('GetDataDir', p._unexpected_accesses[0]['caller_name'])

  def testGatekeeper(self):
    """Tests plugin API calls across different plugin states."""
    # pylint: disable=protected-access
    p = plugin_sandbox.PluginSandbox(
        'plugin_id', _plugin_class=WellBehavedInput)
    self._plugin_objects.append(p)

    # Check during the STOPPED state.
    with self.assertRaises(plugin_base.UnexpectedAccess):
      p.GetDataDir(p._plugin)
    with self.assertRaises(plugin_base.UnexpectedAccess):
      p.IsStopping(p._plugin)
    with self.assertRaises(plugin_base.UnexpectedAccess):
      p.Emit(p._plugin, None)
    with self.assertRaises(plugin_base.UnexpectedAccess):
      p.NewStream(p._plugin)
    with self.assertRaises(plugin_base.UnexpectedAccess):
      p.EventStreamNext(p._plugin, None)
    with self.assertRaises(plugin_base.UnexpectedAccess):
      p.EventStreamCommit(p._plugin, None)
    with self.assertRaises(plugin_base.UnexpectedAccess):
      p.EventStreamAbort(p._plugin, None)
    self.assertEqual(
        len(p._unexpected_accesses),
        min(7, plugin_sandbox._UNEXPECTED_ACCESSES_MAX))

    p.Start(True)

    # Check during the UP state.
    p.GetDataDir(p._plugin)
    self.assertFalse(p.IsStopping(p._plugin))
    with self.assertRaises(NotImplementedError):
      p.Emit(p._plugin, [])
    with self.assertRaises(NotImplementedError):
      p.NewStream(p._plugin)
    with self.assertRaises(plugin_base.UnexpectedAccess):
      p.EventStreamNext(p._plugin, None)
    with self.assertRaises(plugin_base.UnexpectedAccess):
      p.EventStreamCommit(p._plugin, None)
    with self.assertRaises(plugin_base.UnexpectedAccess):
      p.EventStreamAbort(p._plugin, None)

    buffer_stream = plugin_base.BufferEventStream()
    m = mock.Mock(return_value=buffer_stream)
    with mock.patch.object(p._core_api, 'NewStream', m):
      with mock.patch.object(p._core_api, 'GetNodeID', return_value='testing'):
        plugin_stream = p.NewStream(p._plugin)
    self.assertEqual(p._event_stream_map, {plugin_stream: buffer_stream})

    with self.assertRaises(NotImplementedError):
      p.EventStreamNext(p._plugin, plugin_stream)
    with self.assertRaises(NotImplementedError):
      p.EventStreamCommit(p._plugin, plugin_stream)
    self.assertEqual(p._event_stream_map, {})
    with self.assertRaises(plugin_base.UnexpectedAccess):
      p.EventStreamCommit(p._plugin, plugin_stream)

    p.Pause(False)

    # Check during the PAUSING state.
    buffer_stream = plugin_base.BufferEventStream()
    m = mock.Mock(return_value=buffer_stream)
    with mock.patch.object(p._core_api, 'NewStream', m):
      with mock.patch.object(p._core_api, 'GetNodeID', return_value='testing'):
        plugin_stream = p.NewStream(p._plugin)
    self.assertEqual(p._event_stream_map, {plugin_stream: buffer_stream})

    with self.assertRaises(plugin_base.WaitException):
      p.EventStreamNext(p._plugin, plugin_stream)
    with self.assertRaises(NotImplementedError):
      p.EventStreamCommit(p._plugin, plugin_stream)
    self.assertEqual(p._event_stream_map, {})
    with self.assertRaises(plugin_base.UnexpectedAccess):
      p.EventStreamCommit(p._plugin, plugin_stream)

    p.AdvanceState(True)

    # Check during the PAUSED state.
    p.GetDataDir(p._plugin)
    with self.assertRaises(plugin_base.WaitException):
      p.Emit(p._plugin, None)
    with self.assertRaises(plugin_base.WaitException):
      p.NewStream(p._plugin)
    with self.assertRaises(plugin_base.WaitException):
      p.EventStreamNext(p._plugin, None)
    with self.assertRaises(plugin_base.WaitException):
      p.EventStreamCommit(p._plugin, None)
    with self.assertRaises(plugin_base.WaitException):
      p.EventStreamAbort(p._plugin, None)

    p.Stop(True)

  def testPausingWaitForEventStreamCommit(self):
    """Tests a plugin in the PAUSING state waits for event streams to expire."""
    # pylint: disable=protected-access
    p = plugin_sandbox.PluginSandbox(
        'plugin_id', _plugin_class=WellBehavedInput)
    self._plugin_objects.append(p)

    p.Start(True)

    buffer_stream = plugin_base.BufferEventStream()
    m = mock.Mock(return_value=buffer_stream)
    with mock.patch.object(p._core_api, 'NewStream', m):
      with mock.patch.object(p._core_api, 'GetNodeID', return_value='testing'):
        plugin_stream = p.NewStream(p._plugin)

    p.Pause(False)
    p.AdvanceState(False)
    self.assertEqual(p.GetState(), plugin_sandbox.PAUSING)

    with mock.patch.object(buffer_stream, 'Commit', return_value=True):
      p.EventStreamCommit(p._plugin, plugin_stream)

    p.AdvanceState(False)
    self.assertEqual(p.GetState(), plugin_sandbox.PAUSED)

    p.Stop(True)

  def testInvalidCoreAPI(self):
    """Tests that a sandbox passed an invalid CoreAPI object will complain."""
    with self.assertRaisesRegex(TypeError, 'Invalid CoreAPI object'):
      plugin_sandbox.PluginSandbox('plugin_id', core_api=True)


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
