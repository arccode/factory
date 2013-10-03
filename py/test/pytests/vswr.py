# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.event import Event
from cros.factory.test.factory import TestState
from cros.factory.test.media_util import MediaMonitor


class VSWRState(object):
  """VSWR state and its relative callbacks.

  Attributes:
    name: String that represent this state.
    message_id: HTML block ID to display on the screen. If not given, use name.
    callback: Function to invoke in this state.
    on_usb_insert: Function to invoke if any USB's been inserted in this state.
    on_usb_remove: Function to invoke if any USB's been removed in this state.
    on_key_press: Function to invoke if key_to_contine's been pressed.
    key_to_continue: The key to trigger on_key_press callback.
    next_state_name: String to specify the next state.
  """

  def __init__(self, name, message_id=None, callback=None,
               on_usb_insert=None, on_usb_remove=None,
               on_key_press=None, key_to_continue=None,
               next_state_name=None):
    self.name = name
    self.message_id = message_id if message_id is not None else name
    self.callback = callback
    self.on_usb_insert = on_usb_insert
    self.on_usb_remove = on_usb_remove
    self.on_key_press = on_key_press
    self.key_to_continue = key_to_continue
    self.next_state_name = next_state_name


class VSWR(unittest.TestCase):
  """A test for antenna modules using fixture Agilent E5017C (ENA).

  In general, a pytest runs on a DUT, and runs only once. However, this test
  runs on a host Chromebook that controls the ENA, and runs forever because it
  was designed to test many antennas.

  Ideally, the test won't stop after it has been started. But practically, to
  prevent operators from overusing some accessories. It will stop after
  reaching self.allowed_iterations. Reminding the operator to change those
  accessories.
  """

  # Items in the final result table.
  _RESULT_IDS = [
      'sn', 'cell-main', 'cell-aux', 'wifi-main', 'wifi-aux', 'final-result']
  _RESULTS_TO_CHECK = [
      'sn', 'cell-main', 'cell-aux', 'wifi-main', 'wifi-aux']

  ARGS = [
    Arg('config_path', str, 'Configuration path relative to the root of USB '
        'disk or shopfloor parameters. E.g. path/to/config_file_name.',
        optional=True),
    Arg('timezone', str, 'Timezone of shopfloor.', default='Asia/Taipei'),
    Arg('load_from_shopfloor', bool, 'Whether to load parameters from '
        'shopfloor or not.', default=True),
  ]

  def _AdvanceState(self, dummy_event=None):
    """Advances to the next state."""
    old_state = self._states[self._current_state_index]
    # If next_state_name is not specified, default to advance to the next state
    # in self._state array relative to the current state.
    if not old_state.next_state_name:
      self._current_state_index += 1
    else:
      # Find the state that next_state_name specified.
      found = False
      for index, state in enumerate(self._states):
        if state.name == old_state.next_state_name:
          found = True
          self._current_state_index = index
          break
      if not found:
        raise Exception("Can't find state %s" % old_state.next_state_name)
    self._current_state = self._states[self._current_state_index]
    factory.console.info('Advance to state %s', self._current_state.name)
    # Update UI.
    self._ui.RunJS('showMessage("%s")' % self._current_state.message_id)
    # Register callback.
    self._ui.PostEvent(Event(Event.Type.TEST_UI_EVENT, subtype='callback'))

  def _CheckCalibration(self, dummy_event):
    """Checks if the Trace are flat as expected."""
    # TODO(littlecvr) Implement this.
    self._AdvanceState()

  def _ConnectEna(self, dummy_event):
    """Connnects to E5071C(ENA), initialize the SCPI object."""
    # TODO(littlecvr) Implement this.
    self._AdvanceState()

  def _DownloadFromShopfloor(self, dummy_event):
    """Downloads parameters from shopfloor."""
    self._AdvanceState()
    # TODO(littlecvr) Implement this.

  def _ResetDataForNextTest(self, dummy_event):
    """Resets internal data for the next testing cycle."""
    self._ui.RunJS('$("result").style.display = "none"')
    # TODO(littlecvr) Implement this.

  def _LoadConfigFromUSB(self, dummy_event):
    """Loads USB parameters when USB inserted."""
    self._AdvanceState()
    # TODO(littlecvr) Implement this.

  def _RaiseUSBRemovalException(self, dummy_event):
    """Prevents unexpected USB removal."""
    # TODO(littlecvr) Implement this.

  def _InputSN(self, dummy_event):
    """Callback for sn_input_widget when enter pressed."""
    self._AdvanceState()
    # TODO(littlecvr) Implement this.

  def _TestMainAntennas(self, dummy_event):
    """Tests the main antenna of cellular and wifi."""
    self._AdvanceState()
    # TODO(littlecvr) Implement this.

  def _TestAuxAntennas(self, dummy_event):
    """Tests the aux antenna of cellular and wifi."""
    self._AdvanceState()
    # TODO(littlecvr) Implement this.

  def _SaveLog(self, dummy_event):
    """Saves the logs and writes event log."""
    self._AdvanceState()
    # TODO(littlecvr) Implement this.

  def _ShowResults(self, dummy_event):
    """Displays the final result."""
    for name in self._RESULT_IDS:
      self._ui.SetHTML(self._results[name], id='result-%s' % name)
    self._ui.RunJS('$("result").style.display = ""')

  def _HandleCallbackEvent(self, event):
    """Handler of the "callback" event that triggers the corresponding callback
       if necessary."""
    if self._current_state.callback:
      self._current_state.callback(event)

  def _HandleKeyPressEvent(self, event):
    """Handler of the "keypress" event that triggers the corresponding callback
       if necessary."""
    event.key = str(event.data['key'])
    if self._current_state.on_key_press:
      if event.key == str(self._current_state.key_to_continue):
        self._current_state.on_key_press(event)

  def _HandleUSBInsertEvent(self, event):
    """Handler of the "usbinsert" event that triggers the corresponding callback
       if necessary."""
    if self._current_state.on_usb_insert:
      self._current_state.on_usb_insert(event)

  def _HandleUSBRemoveEvent(self, event):
    """Handler of the "usbremove" event that triggers the corresponding callback
       if necessary."""
    if self._current_state.on_usb_remove:
      self._current_state.on_usb_remove(event)

  def setUp(self):
    factory.console.info(
        '(config_path: %s, timezone: %s, load_from_shopfloor: %s)',
        self.args.config_path, self.args.timezone,
        self.args.load_from_shopfloor)

    # Set timezone.
    os.environ['TZ'] = self.args.timezone

    self._results = {name: TestState.UNTESTED for name in self._RESULT_IDS}

    # Set callbacks of each state.
    self._states = [
        VSWRState('initial',
                  next_state_name='download-from-shopfloor'
                      if self.args.load_from_shopfloor
                      else 'wait-for-usb'),
        VSWRState('download-from-shopfloor',
                  callback=self._DownloadFromShopfloor),
        VSWRState('wait-for-usb',
                  message_id='wait-for-usb-log'
                      if self.args.load_from_shopfloor
                      else 'wait-for-usb-parameters-and-log',
                  on_usb_insert=self._AdvanceState
                      if self.args.load_from_shopfloor
                      else self._LoadConfigFromUSB),
        VSWRState('connect-to-ena',
                  callback=self._ConnectEna,
                  on_usb_remove=self._RaiseUSBRemovalException),
        VSWRState('check-calibration',
                  callback=self._CheckCalibration,
                  on_usb_remove=self._RaiseUSBRemovalException),
        VSWRState('prepare-panel',
                  callback=self._ResetDataForNextTest,
                  on_usb_remove=self._RaiseUSBRemovalException,
                  on_key_press=self._AdvanceState,
                  key_to_continue=test_ui.ENTER_KEY),
        VSWRState('enter-sn',
                  callback=lambda _: self._ui.RunJS('resetSNAndGetFocus()'),
                  on_usb_remove=self._RaiseUSBRemovalException,
                  on_key_press=self._InputSN,
                  key_to_continue=test_ui.ENTER_KEY),
        VSWRState('prepare-main-antenna',
                  on_usb_remove=self._RaiseUSBRemovalException,
                  on_key_press=self._AdvanceState,
                  key_to_continue='A'),
        VSWRState('test-main-antenna',
                  callback=self._TestMainAntennas,
                  on_usb_remove=self._RaiseUSBRemovalException),
        VSWRState('prepare-aux-antenna',
                  on_usb_remove=self._RaiseUSBRemovalException,
                  on_key_press=self._AdvanceState,
                  key_to_continue='K'),
        VSWRState('test-aux-antenna',
                  callback=self._TestAuxAntennas,
                  on_usb_remove=self._RaiseUSBRemovalException),
        VSWRState('save-log',
                  callback=self._SaveLog,
                  on_usb_remove=self._RaiseUSBRemovalException),
        VSWRState('show-result',
                  callback=self._ShowResults,
                  on_usb_remove=self._RaiseUSBRemovalException,
                  on_key_press=self._AdvanceState,
                  key_to_continue=test_ui.ENTER_KEY,
                  next_state_name='prepare-panel')]
    # Set initial state.
    self._current_state_index = 0
    self._current_state = self._states[self._current_state_index]

    # Set up UI and register event handlers.
    self._ui = test_ui.UI()
    self._ui.AddEventHandler('callback', self._HandleCallbackEvent)
    self._ui.AddEventHandler('keypress', self._HandleKeyPressEvent)
    self._ui.AddEventHandler('usbinsert', self._HandleUSBInsertEvent)
    self._ui.AddEventHandler('usbremove', self._HandleUSBRemoveEvent)

    # Find every key_to_continue and bind them. Note that the keypress event
    # must be emitted from JS or it won't be able to get the value of input
    # box.
    self._bound_keys = set()
    for state in self._states:
      if state.key_to_continue:
        self._bound_keys.add(state.key_to_continue)
    for key in self._bound_keys:
      self._ui.BindKeyJS(key, 'emitKeyPressEvent("%s")' % key)

    # Set up USB monitor.
    self._monitor = MediaMonitor()
    self._monitor.Start(
        on_insert=lambda dev_path: self._ui.PostEvent(Event(
            Event.Type.TEST_UI_EVENT, subtype='usbinsert', dev_path=dev_path)),
        on_remove=lambda dev_path: self._ui.PostEvent(Event(
            Event.Type.TEST_UI_EVENT, subtype='usbremove', dev_path=dev_path)))

  def runTest(self):
    self._AdvanceState()
    self._ui.Run()
