# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test external display with optional audio playback test.

Description
-----------
Verify the external display is functional.

The test is defined by a list ``[display_label, display_id,
audio_info, usbpd_port]``. Each item represents an external port:

- ``display_label``: I18n display name seen by operator, e.g. ``_('VGA')``.
- ``display_id``: (str) ID used to identify display in xrandr or modeprint,
  e.g. VGA1.
- ``audio_info``: A list of ``[audio_card, audio_device, init_actions]``,
  or None:

  - ``audio_card`` is either the card's name (str), or the card's index (int).
  - ``audio_device`` is the device's index (int).
  - ``init_actions`` is a list of ``[card_name, action]`` (list).
    action is a dict key defined in audio.json (ref: audio.py) to be passed
    into dut.audio.ApplyAudioConfig.

  e.g. ``[["rt5650", "init_audio"], ["rt5650", "enable_hdmi"]]``.
  This argument is optional. If set, the audio playback test is added.
- ``usbpd_port``: (int) Verify the USB PD TypeC port status, or None.

It can also be configured to run automatically by specifying ``bft_fixture``
argument, and skip some steps by setting ``connect_only``,
``start_output_only`` and ``stop_output_only``.

Test Procedure
--------------
This test can be manual or automated depends on whether ``bft_fixture``
is specified. The test loops through all items in ``display_info`` and:

1. Plug an external monitor to the port specified in dargs.
2. (Optional) If ``audio_info.usbpd_port`` is specified, verify usbpd port
   status automatically.
3. Main display will automatically switch to the external one.
4. Press the number shown on the display to verify display works.
5. (Optional) If ``audio_info`` is specified, the speaker will play a random
   number, and operator has to press the number to verify audio functionality.
6. Unplug the external monitor to finish the test.

Dependency
----------
- Python evdev library <https://github.com/gvalkov/python-evdev>.
- ``display`` component in device API.
- Optional ``audio`` and ``usb_c`` components in device API.
- Optional fixture can be used to support automated test.

Examples
--------
To manual checking external display at USB Port 0, add this in test list::

  {
    "pytest_name": "external_display",
    "args": {
      "display_info": [
        ["i18n! Left HDMI External Display", "HDMI-A-1", null, 0]
      ]
    }
  }
"""

from __future__ import print_function
import logging
import random
import threading
import time
import unittest
import uuid

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.external import evdev
from cros.factory.test import event
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.pytests import audio
from cros.factory.test import state
from cros.factory.test import test_task
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import evdev_utils
from cros.factory.utils.arg_utils import Arg


_DIV_CENTER_INSTRUCTION = """
<div id='instruction-center' class='template-instruction'></div>"""
_CSS = """
  #pass_key {
    font-size: 2.25em;
    font-weight: bold;
  }
  test-template.green-background {
    --template-background-color: #00ff00;
  }
"""

# Interval (seconds) of probing connection state.
_CONNECTION_CHECK_PERIOD_SECS = 2


# Messages for tasks
def _GetTitleConnectTest(display):
  return i18n_test_ui.MakeI18nLabel('{display} Connect', display=display)


def _GetTitleVideoTest(display):
  return i18n_test_ui.MakeI18nLabel('{display} Video', display=display)


def _GetTitleDisconnectTest(display):
  return i18n_test_ui.MakeI18nLabel('{display} Disconnect', display=display)


def _GetMsgConnectTest(display):
  return i18n_test_ui.MakeI18nLabel('Connect external display: {display}',
                                    display=display)


def _GetMsgVideoTest(display):
  return i18n_test_ui.MakeI18nLabel('Do you see video on {display}?',
                                    display=display)


def _GetMsgFixtureVideoTest(display):
  return i18n_test_ui.MakeI18nLabel(
      'Fixture is checking if video is displayed on {display}?',
      display=display)


def _GetMsgDisconnectTest(display):
  return i18n_test_ui.MakeI18nLabel('Disconnect external display: {display}',
                                    display=display)


def _GetMsgPromptPassKey(key):
  return i18n_test_ui.MakeI18nLabel(
      'Press <span id="pass_key">{key}</span> to pass the test.', key=key)


class ExtDisplayTask(test_task.InteractiveTestTask):
  """Base class of tasks for external display test.

  Args:
    args: a ExtDisplayTaskArg object.
    title: task title showed on the upper-left corner of the test area.
    instruction: task instruction showed on the center of the test area.
    pass_key: True to bind Enter key to pass the task.
  """
  # pylint: disable=abstract-method

  def __init__(self, args, title, instruction):
    super(ExtDisplayTask, self).__init__(args.ui)
    self._args = args
    self._ui = args.ui
    self._template = args.template
    self._title = title
    self._instruction = instruction

  def _SetInstruction(self):
    """Sets title and instruction.

    Shows task title on the upper left corner and instruction at the center
    of the test area.
    """
    self._template.SetInstruction(self._title)
    self._ui.SetHTML(
        '%s<br>%s' % (self._instruction, test_ui.FAIL_KEY_LABEL),
        id='instruction-center')

  def InitUI(self, fail_later=True):
    """Initializes UI.

    Sets task title and instruction. Binds pass/fail keys.
    Should be called in the beginning of Run().

    Args:
      fail_later: True to fail later when fail key is pressed.
    """
    self._SetInstruction()
    self.BindPassFailKeys(pass_key=False, fail_later=fail_later)


class WaitDisplayThread(threading.Thread):
  """A thread to wait for display connection state.

  When expected connection state is observed, it calls on_success and stop.
  Or the calling thread can stop it using Stop().
  It probes display state every _CONNECTION_CHECK_PERIOD_SECS seconds.

  Args:
    display_id: target display ID.
    connect: DetectDisplayTask.CONNECT or DetectDisplayTask.DISCONNECT
    on_success: callback for success.
    usbpd_port: The USB PD Port number for status verification
    dut: A DUT instance for accessing device under test.
  """

  def __init__(self, display_id, connect, on_success, usbpd_port, dut_obj):
    threading.Thread.__init__(self, name='WaitDisplayThread')
    self._display_id = display_id
    self._done = threading.Event()
    self._connect = connect == DetectDisplayTask.CONNECT
    self._on_success = on_success
    self._usbpd_port = usbpd_port
    self._dut = dut_obj

  def run(self):
    while not self._done.is_set():
      # Check USBPD status before display info
      if self._usbpd_port is not None:
        if not self.VerifyUSBPD(self._usbpd_port):
          continue

      port_info = self._dut.display.GetPortInfo()
      if port_info[self._display_id].connected == self._connect:
        display_info = state.get_instance().DeviceGetDisplayInfo()
        # In the case of connecting an external display, make sure there
        # is an item in display_info with 'isInternal' False.
        # On the other hand, in the case of disconnecting an external display,
        # we can not check display info has no display with 'isInternal' False
        # because any display for chromebox has 'isInternal' False.
        if ((self._connect and
             any(x['isInternal'] is False for x in display_info)) or
            not self._connect):
          logging.info('Get display info %r', display_info)
          self._on_success()
          self.Stop()

      self._done.wait(_CONNECTION_CHECK_PERIOD_SECS)

  def Stop(self):
    """Stops the thread."""
    self._done.set()

  def VerifyUSBPD(self, port):
    """ Verifies the USB PD port Status.

    Returns:
      True for verifying OK,
      False for verifying Fail.
    """
    port_status = self._dut.usb_c.GetPDStatus(port)
    return self._connect == port_status['connected']


class DetectDisplayTask(ExtDisplayTask):
  """Task to wait for connecting / disconnecting a external display.

  A base class of ConnectTask and DisconnectTask.

  Args:
    args: refer base class.
    title: refer base class.
    instruction: refer base class.
    display_label: target display's human readable name.
    display_id: target display's id in xrandr/modeprint.
    connect: (CONNECT/DISCONNECT) checks for connect/disconnect.
  """
  CONNECT = 'connected'
  DISCONNECT = 'disconnected'

  def __init__(self, args, title, instruction, connect):
    super(DetectDisplayTask, self).__init__(args, title, instruction)
    self._wait_display = WaitDisplayThread(args.display_id, connect,
                                           self.PostSuccessEvent,
                                           args.usbpd_port,
                                           args.dut)
    self._pass_event = str(uuid.uuid4())  # used to bind a post event.
    self._fixture = args.fixture
    self._connect = connect == self.CONNECT

    # Whether or not to send a BFT command.
    self._bft_command = self._fixture is not None
    if self._connect and args.already_connect:
      self._bft_command = False

  def PostSuccessEvent(self):
    """Posts an event to trigger self.Pass().

    It is called by another thread. It ensures that self.Pass() is called
    via event queue to prevent race condition.
    """
    self._ui.PostEvent(event.Event(event.Event.Type.TEST_UI_EVENT,
                                   subtype=self._pass_event))

  def Prepare(self):
    """Called before running display detection loop."""
    pass

  def Run(self):
    # If the display is unable to detect, it should not perform the remaining
    # tasks.
    self.InitUI(fail_later=False)
    self.Prepare()
    self._ui.AddEventHandler(self._pass_event, lambda _: self.Pass())
    self._wait_display.start()

    if self._bft_command:
      try:
        self._fixture.SetDeviceEngaged(
            bft_fixture.BFTFixture.Device.EXT_DISPLAY, self._connect)
      except bft_fixture.BFTFixtureException as e:
        self.Fail('Detect display failed: %s' % e)

  def Cleanup(self):
    self._wait_display.Stop()


class ConnectTask(DetectDisplayTask):
  """Task to wait for a external display to connect.

  Args:
    args: refer base class.
  """

  def __init__(self, args):
    super(ConnectTask, self).__init__(
        args,
        _GetTitleConnectTest(args.display_label),
        _GetMsgConnectTest(args.display_label),
        DetectDisplayTask.CONNECT)


class DisconnectTask(DetectDisplayTask):
  """Task to wait for a external display to disconnect.

  Args:
    args: refer base class.
  """

  def __init__(self, args):
    super(DisconnectTask, self).__init__(
        args,
        _GetTitleDisconnectTest(args.display_label),
        _GetMsgDisconnectTest(args.display_label),
        DetectDisplayTask.DISCONNECT)


class FixtureCheckDisplayThread(threading.Thread):
  """A thread to use fixture to check display.

  When expected connection state is observed, it calls on_success and stop.
  Or the calling thread can stop it using Stop().
  It probes display state every _CONNECTION_CHECK_PERIOD_SECS seconds.

  Args:
    fixture: BFTFixture instance.
    check_interval_secs: Interval between checks in seconds.
    retry_times: Number of retries before fail.
    on_success: callback for success.
    on_failure: callback for failure.
  """

  def __init__(self, fixture, check_interval_secs, retry_times, on_success,
               on_failure):
    threading.Thread.__init__(self, name='FixtureCheckDisplayThread')
    self._done = threading.Event()
    self._fixture = fixture
    self._check_interval = check_interval_secs
    self._retry_times = retry_times
    self._on_success = on_success
    self._on_failure = on_failure

  def run(self):
    num_tries = 0
    while not self._done.is_set():
      try:
        self._fixture.CheckExtDisplay()
        self._on_success()
        self.Stop()
        return
      except bft_fixture.BFTFixtureException:
        num_tries += 1
        if num_tries < self._retry_times:
          logging.info(
              'Cannot see screen on external display. Wait for %.1f seconds.',
              self._check_interval)
          self._done.wait(self._check_interval)
        else:
          logging.error(
              'Failed to see screen on external display after %d retries.',
              self._retry_times)
          self._on_failure()
          self.Stop()

  def Stop(self):
    """Stops the thread."""
    self._done.set()


class VideoTask(ExtDisplayTask):
  """Task to show screen on external display only.

  The task is passed only after an operator press a random digit which
  is promoted on the external display.

  Args:
    args: refer base class.
  """

  def __init__(self, args):
    self._fixture = args.fixture
    self._manual = not self._fixture
    self._ui = args.ui
    self._original_primary_display = self._GetDisplayId(is_primary=True)

    # Bind a random key (0-9) to pass the task.
    if self._manual:
      self._pass_digit = random.randint(0, 9)
      instruction = '%s<br>%s' % (
          _GetMsgVideoTest(args.display_label),
          _GetMsgPromptPassKey(self._pass_digit))

    if self._fixture:
      instruction = _GetMsgFixtureVideoTest(args.display_label)
      self._check_display = FixtureCheckDisplayThread(self._fixture, 1, 10,
                                                      self.PostSuccessEvent,
                                                      self.PostFailureEvent)
      self._pass_event = str(uuid.uuid4())  # used to bind a post event.
      self._fail_event = str(uuid.uuid4())  # used to bind a post event.
      self._ui.AddEventHandler(self._pass_event, lambda _: self.Pass())
      self._ui.AddEventHandler(
          self._fail_event,
          lambda _: self.Fail('Fail to check screen on external display'))

    super(VideoTask, self).__init__(args,
                                    _GetTitleVideoTest(args.display_label),
                                    instruction)

  def _GetDisplayId(self, is_primary=True):
    for info in state.get_instance().DeviceGetDisplayInfo():
      if bool(info['isPrimary']) == is_primary:
        return info['id']
    self.Fail('Fail to get display ID')

  def SetMainDisplay(self, recover_original=True):
    """Sets the main display.

    If there are two displays, this method can switch main display based on
    recover_original. If there is only one display, it returns if the only
    display is an external display (e.g. on a chromebox).

    Args:
      recover_original: True to set the original display as main;  False to
          set the other (external) display as main.
    """
    display_info = state.get_instance().DeviceGetDisplayInfo()
    if len(display_info) == 1:
      # Fail the test if we see only one display and it's the internal one.
      if display_info[0]['isInternal']:
        self.Fail('Fail to detect external display')
      else:
        return

    # Try to switch main display for at most 5 times.
    tries_left = 5
    while tries_left:
      if not (recover_original ^ (self._GetDisplayId(is_primary=True) ==
                                  self._original_primary_display)):
        # Stop the loop if these two conditions are either both True or
        # both False.
        break
      evdev_utils.SendKeys([evdev.ecodes.KEY_LEFTALT, evdev.ecodes.KEY_F4])
      tries_left -= 1
      time.sleep(2)

    if tries_left == 0:
      self.Fail('Fail to switch main display')

  def PostSuccessEvent(self):
    """Posts an event to trigger self.Pass().

    It is called by another thread. It ensures that self.Pass() is called
    via event queue to prevent race condition.
    """
    self._ui.PostEvent(event.Event(event.Event.Type.TEST_UI_EVENT,
                                   subtype=self._pass_event))

  def PostFailureEvent(self):
    """Posts an event to trigger self.Fail().

    It is called by another thread. It ensures that self.Fail() is called
    via event queue to prevent race condition.
    """
    self._ui.PostEvent(event.Event(event.Event.Type.TEST_UI_EVENT,
                                   subtype=self._fail_event))

  def Run(self):
    self.SetMainDisplay(recover_original=False)
    self.InitUI()

    if self._fixture:
      # Show light green background for Fixture's light sensor checking.
      self._ui.RunJS(
          'window.template.classList.add("green-background")')

    if self._manual:
      self.BindDigitKeys(self._pass_digit)

    if self._fixture:
      self._check_display.start()

  def Cleanup(self):
    self.SetMainDisplay(recover_original=True)
    if self._manual:
      self.UnbindDigitKeys()
    if self._fixture:
      self._check_display.Stop()


class AudioSetupTask(test_task.TestTask):
  """A task to setup audio initial configuration.

  Args:
    dut: A DUT instance for accessing device under test.
    init_actions are list of [card_name, actions] (list).
  """

  def __init__(self, _dut, init_actions):
    super(AudioSetupTask, self).__init__()
    self._dut = _dut
    self._init_actions = init_actions

  def Run(self):
    for card, action in self._init_actions:
      card = self._dut.audio.GetCardIndexByName(card)
      self._dut.audio.ApplyAudioConfig(action, card)
    self.Pass()


class ExtDisplayTaskArg(object):
  """Contains args needed by ExtDisplayTask."""

  def __init__(self, _dut):
    self.main_display_id = None
    self.display_label = None
    self.display_id = None
    self.audio_card = None
    self.audio_device = None
    self.init_actions = None
    self.ui = None
    self.template = None
    self.fixture = None
    self.usbpd_port = None
    self.dut = _dut

    # This is for a reboot hack which tells DetectDisplayTask
    # whether to send a display plug command or not.
    self.already_connect = False

  def ParseDisplayInfo(self, info):
    """Parses lists from args.display_info.

    Args:
      info: a list in args.display_info. Refer display_info definition.

    Raises:
      ValueError if parse error.
    """
    # Sanity check
    if len(info) not in [2, 3, 4]:
      raise ValueError('ERROR: invalid display_info item: ' + str(info))

    self.display_label, self.display_id = info[:2]
    if len(info) >= 3 and info[2] is not None:
      if (not isinstance(info[2], list) or
          not isinstance(info[2][2], list)):
        raise ValueError('ERROR: invalid display_info item: ' + str(info))
      self.audio_card = self.dut.audio.GetCardIndexByName(info[2][0])
      self.audio_device = info[2][1]
      self.init_actions = info[2][2]

    if len(info) == 4:
      if not isinstance(info[3], int):
        raise ValueError('USB PD Port should be an integer')
      self.usbpd_port = info[3]


class ExtDisplayTest(unittest.TestCase):
  """Main class for external display test."""
  ARGS = [
      Arg('main_display', str,
          "xrandr/modeprint ID for ChromeBook's main display."),
      Arg('display_info', list,
          'A list of tuples (display_label, display_id, audio_info, '
          'usbpd_port) represents an external port to test.'),
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP,
          default=None),
      Arg('connect_only', bool,
          'Just detect ext display connection. This is for a hack that DUT '
          'needs reboot after connect to prevent X crash.',
          default=False),
      Arg('start_output_only', bool,
          'Only start output of external display. This is for bringing up '
          'the external display for other tests that need it.',
          default=False),
      Arg('stop_output_only', bool,
          'Only stop output of external display. This is for bringing down '
          'the external display that other tests have finished using.',
          default=False),
      Arg('already_connect', bool,
          'Also for the reboot hack with fixture. With it set to True, DUT '
          'does not issue plug ext display command.',
          default=False)
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._ui = test_ui.UI()
    self._template = ui_templates.TwoSections(self._ui)
    self._task_manager = None
    self._fixture = None
    if self.args.bft_fixture:
      self._fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)

  def InitUI(self):
    """Initializes UI.

    Sets test title and draw progress bar.
    """
    self._template.SetState(_DIV_CENTER_INSTRUCTION)
    self._template.DrawProgressBar()
    self._ui.AppendCSS(_CSS)

  def ComposeTasks(self):
    """Composes tasks acoording to display_info dargs.

    Returns:
      A list of tasks derived from ExtDisplayTask.

    Raises:
      ValueError if args.display_info is invalid.
    """
    tasks = []
    for info in self.args.display_info:
      args = ExtDisplayTaskArg(self._dut)
      args.ParseDisplayInfo(info)
      args.main_display_id = self.args.main_display
      args.ui = self._ui
      args.template = self._template
      args.fixture = self._fixture
      args.already_connect = self.args.already_connect
      args.dut = self._dut

      if not self.args.stop_output_only:
        tasks.append(ConnectTask(args))
        if not self.args.connect_only:
          tasks.append(VideoTask(args))
          if args.audio_card:
            tasks.append(AudioSetupTask(self._dut, args.init_actions))
            audio_label = i18n_test_ui.MakeI18nLabel(
                '{display_label} Audio', display_label=args.display_label)
            tasks.append(audio.AudioDigitPlaybackTask(
                self._dut, self._ui, audio_label, 'instruction',
                'instruction-center', card=args.audio_card,
                device=args.audio_device))
          if not self.args.start_output_only:
            tasks.append(DisconnectTask(args))
      else:
        tasks.append(DisconnectTask(args))

      return tasks

  def runTest(self):
    self.InitUI()
    self._task_manager = test_task.TestTaskManager(
        self._ui, self.ComposeTasks(),
        update_progress=self._template.SetProgressBarValue)
    self._task_manager.Run()
