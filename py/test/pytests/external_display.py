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

import collections
import logging
import random

from six.moves import xrange

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test.pytests import audio
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg


# Interval (seconds) of probing connection state.
_CONNECTION_CHECK_PERIOD_SECS = 1


ExtDisplayTaskArg = collections.namedtuple('ExtDisplayTaskArg', [
    'display_label', 'display_id', 'audio_card', 'audio_device', 'init_actions',
    'usbpd_port'
])


class ExtDisplayTest(test_case.TestCase):
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
    self._fixture = None
    if self.args.bft_fixture:
      self._fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)

    self.assertLessEqual(
        [self.args.start_output_only, self.args.connect_only,
         self.args.stop_output_only].count(True),
        1,
        'Only one of start_output_only, connect_only '
        'and stop_output_only can be true.')

    self.do_connect, self.do_output, self.do_disconnect = False, False, False

    if self.args.start_output_only:
      self.do_connect = True
      self.do_output = True
    elif self.args.connect_only:
      self.do_connect = True
    elif self.args.stop_output_only:
      self.do_disconnect = True
    else:
      self.do_connect = True
      self.do_output = True
      self.do_disconnect = True

    self._toggle_timestamp = 0

    # Setup tasks
    for info in self.args.display_info:
      args = self.ParseDisplayInfo(info)

      if self.do_connect:
        self.AddTask(self.WaitConnect, args)

      if self.do_output:
        self.AddTask(self.CheckVideo, args)
        if args.audio_card:
          self.AddTask(self.SetupAudio, args)
          audio_label = _(
              '{display_label} Audio', display_label=args.display_label)
          self.AddTask(
              audio.TestAudioDigitPlayback, self.ui, self._dut, audio_label,
              card=args.audio_card, device=args.audio_device)

      if self.do_disconnect:
        self.AddTask(self.WaitDisconnect, args)

  def ParseDisplayInfo(self, info):
    """Parses lists from args.display_info.

    Args:
      info: a list in args.display_info. Refer display_info definition.

    Returns:
      Parsed ExtDisplayTaskArg.

    Raises:
      ValueError if parse error.
    """
    # Sanity check
    if len(info) not in [2, 3, 4]:
      raise ValueError('ERROR: invalid display_info item: ' + str(info))

    display_label, display_id = info[:2]
    audio_card, audio_device, init_actions, usbpd_port = None, None, None, None
    if len(info) >= 3 and info[2] is not None:
      if (not isinstance(info[2], list) or
          not isinstance(info[2][2], list)):
        raise ValueError('ERROR: invalid display_info item: ' + str(info))
      audio_card = self._dut.audio.GetCardIndexByName(info[2][0])
      audio_device = info[2][1]
      init_actions = info[2][2]

    if len(info) == 4:
      if not isinstance(info[3], int):
        raise ValueError('USB PD Port should be an integer')
      usbpd_port = info[3]

    return ExtDisplayTaskArg(
        display_label=display_label,
        display_id=display_id,
        audio_card=audio_card,
        audio_device=audio_device,
        init_actions=init_actions,
        usbpd_port=usbpd_port)

  def CheckVideo(self, args):
    self.ui.BindStandardFailKeys()
    original, target = self.VerifyDisplayConfig()
    self.SetMainDisplay(target)
    try:
      if self._fixture:
        self.CheckVideoFixture(args)
      else:
        self.CheckVideoManual(args)
    finally:
      self.SetMainDisplay(original)

  def CheckVideoManual(self, args):
    pass_digit = random.randrange(10)
    self.ui.SetState([
        _('Do you see video on {display}?', display=args.display_label),
        _('Press {key} to pass the test.',
          key=('<span id="pass_key">%s</span>' % pass_digit))
    ])

    key = int(self.ui.WaitKeysOnce([str(i) for i in xrange(10)]))
    if key != pass_digit:
      self.FailTask('Wrong key pressed. pressed: %d, correct: %d' %
                    (key, pass_digit))

  def CheckVideoFixture(self, args):
    """Use fixture to check display.

    When expected connection state is observed, it pass the task.
    It probes display state every second.

    Args:
      args: ExtDisplayTaskArg instance.
    """
    check_interval_secs = 1
    retry_times = 10
    # Show light green background for Fixture's light sensor checking.
    self.ui.RunJS(
        'window.template.classList.add("green-background")')
    self.ui.SetState(
        _('Fixture is checking if video is displayed on {display}?',
          display=args.display_label))
    for num_tries in xrange(1, retry_times + 1):
      try:
        self._fixture.CheckExtDisplay()
        self.PassTask()
      except bft_fixture.BFTFixtureException:
        if num_tries < retry_times:
          logging.info(
              'Cannot see screen on external display. Wait for %.1f seconds.',
              check_interval_secs)
          self.Sleep(check_interval_secs)
        else:
          self.FailTask(
              'Failed to see screen on external display after %d retries.' %
              retry_times)

  def VerifyDisplayConfig(self):
    """Check display configuration.

    Verifies that the currently connected external displays is a valid
    configuration. We may have:
    - 1 internal, 1 external (e.g. chromebook)
    - 1 external (e.g. chromebox)
    - 2 external (e.g. chromebox)

    Returns:
      (current, target): current and target display ids.
    """
    display_info = state.GetInstance().DeviceGetDisplayInfo()

    # Sort the current displays
    primary = []
    other = []
    internal = []
    external = []
    for info in display_info:
      if info['isInternal']:
        internal.append(info)
      else:
        external.append(info)

      if info['isPrimary']:
        primary.append(info)
      else:
        other.append(info)

    self.assertEqual(len(primary), 1, "invalid number of primary displays")
    current = primary[0]['id']

    # Test for a valid configuration
    config = (len(internal), len(external))
    if config == (1, 1):
      target = external[0]['id']
    elif config == (0, 1):
      target = external[0]['id']
    elif config == (0, 2):
      # Select non-primary display
      target = other[0]['id']
    else:
      self.FailTask('Invalid display count: %d internal %d external' % config)

    return (current, target)

  def SetMainDisplay(self, display_id):
    """Sets the main display.

    Args:
      target_id: id of target display.
    """

    err = state.GetInstance().DeviceSetDisplayProperties(display_id,
                                                         {'isPrimary': True})
    self.assertIsNone(err, 'Failed to set the main display: %s' % err)

  def SetupAudio(self, args):
    for card, action in args.init_actions:
      card = self._dut.audio.GetCardIndexByName(card)
      self._dut.audio.ApplyAudioConfig(action, card)

  def WaitConnect(self, args):
    self.ui.BindStandardFailKeys()
    self.ui.SetState(_('Connect external display: {display} and wait until '
                       'it becomes primary.',
                       display=args.display_label))

    self._WaitDisplayConnection(args, True)

  def WaitDisconnect(self, args):
    self.ui.BindStandardFailKeys()
    self.ui.SetState(
        _('Disconnect external display: {display}', display=args.display_label))
    self._WaitDisplayConnection(args, False)

  def _WaitDisplayConnection(self, args, connect):
    if self._fixture and not (connect and self.args.already_connect):
      try:
        self._fixture.SetDeviceEngaged(
            bft_fixture.BFTFixture.Device.EXT_DISPLAY, connect)
      except bft_fixture.BFTFixtureException as e:
        self.FailTask('Detect display failed: %s' % e)

    while True:
      # Check USBPD status before display info
      if (args.usbpd_port is None or
          self._dut.usb_c.GetPDStatus(args.usbpd_port)['connected'] == connect):
        port_info = self._dut.display.GetPortInfo()
        if port_info[args.display_id].connected == connect:
          display_info = state.GetInstance().DeviceGetDisplayInfo()
          # In the case of connecting an external display, make sure there
          # is an item in display_info with 'isInternal' False.  If no such
          # display_info item, we assume the device's default mode is mirror
          # mode and try to turn off mirror mode.
          # On the other hand, in the case of disconnecting an external display,
          # we can not check display info has no display with 'isInternal' False
          # because any display for chromebox has 'isInternal' False.
          if connect and all(x['isInternal'] for x in display_info):
            err = state.GetInstance().DeviceSetDisplayMirrorMode(
                {'mode': 'off'})
            if err is not None:
              logging.warning('Failed to turn off the mirror mode: %s', err)
          else:
            logging.info('Get display info %r', display_info)
            break
      self.Sleep(_CONNECTION_CHECK_PERIOD_SECS)
