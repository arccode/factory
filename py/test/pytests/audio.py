# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests audio playback.

Description
-----------
The test plays a random digit from speaker, and checks if the operator presses
the correct key.

If ``test_left_right`` is set, left and right output channels are tested
separately.

If ``check_headphone`` is set, before the digit is played, the test would check
if the headphone status is same as ``require_headphone`` , and ask the operator
to plug in / disconnect the headphone otherwise.

A valid ``output_dev`` should be specified, which is in the form of
``(card_name, sub_device)``. Both value can be obtained from output of
``aplay -l`` on DUT.

Also, you may need to set ``initial_actions`` for audio to work correctly.
Refer to the audio.json config file on what actions should be set as
``initial_actions``.

Test Procedure
--------------
1. If ``check_headphone`` is set, operator will be prompted to plug in or
   disconnect to headphone.
2. A digit would be played.
3. Operator presses the key corresponds to the digit played. Test fail if the
   operator presses the wrong key.
4. If ``test_left_right``, repeat 2. and 3. on another channel.

Dependency
----------
- External program `sox <http://sox.sourceforge.net/>`_.
- Device API ``cros.factory.device.audio``.

Examples
--------
To check if the audio can be played, add this in test list::

  {
    "pytest_name": "audio",
    "args": {
      "output_dev": ["device", "0"]
    }
  }

To check that headphone is plugged in before audio is played, add this in test
list::

  {
    "pytest_name": "audio",
    "args": {
      "check_headphone": true,
      "output_dev": ["device", "0"],
      "require_headphone": true
    }
  }
"""

import logging
import os
import random

from cros.factory.device import device_utils
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


_SOUND_DIRECTORY = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'goofy',
    'static', 'sounds')


def _PlayAudioFile(dut, audio_file, card, device, channel, sample_rate):
  """Plays an audio file on DUT with specified channel and sample rate."""
  with file_utils.UnopenedTemporaryFile(suffix='.wav') as wav_path:
    # Prepare played .wav file
    with file_utils.UnopenedTemporaryFile(suffix='.wav') as temp_wav_path:
      # We generate stereo sound by default. and mute one channel by sox
      # if needed.
      cmd = ['sox', audio_file, '-c2']
      if sample_rate is not None:
        cmd += ['-r', '%d' % sample_rate]
      cmd += [temp_wav_path]
      process_utils.Spawn(cmd, log=True, check_call=True)
      if channel == 'left':
        process_utils.Spawn(
            ['sox', temp_wav_path, wav_path, 'remix', '1', '0'],
            log=True, check_call=True)
      elif channel == 'right':
        process_utils.Spawn(
            ['sox', temp_wav_path, wav_path, 'remix', '0', '1'],
            log=True, check_call=True)
      else:
        process_utils.Spawn(['mv', temp_wav_path, wav_path],
                            log=True, check_call=True)

    with dut.temp.TempFile() as dut_wav_path:
      dut.link.Push(wav_path, dut_wav_path)
      dut.audio.PlaybackWavFile(dut_wav_path, card, device)


def TestAudioDigitPlayback(ui, dut, port_name, card, device, channel='all',
                           sample_rate=None):
  """Test to verify audio playback function.

  It randomly picks a digit to play and checks if the operator presses the
  correct digit. It also prevents key-swiping cheating.
  Note: external_display.py uses this function to test HDMI audio.

  Args:
    ui: cros.factory.test.test_ui.StandardUI object.
    dut: dut instance
    port_name: Name of audio port to output.
    card: audio card to output.
    device: audio device to output.
    channel: target channel. Value of 'left', 'right', 'all'. Default 'all'.
    sample_rate: sample rate of the playing sound, None for no change.

  Raise:
    TestFailure if the test fails.
  """
  pass_digit = random.randint(0, 9)

  channel_name = {
      'left': _('Left Channel'),
      'right': _('Right Channel')
  }

  if channel in channel_name:
    device = i18n.StringFormat(
        '{port_name} ({channel_name})',
        port_name=port_name,
        channel_name=channel_name[channel])
  else:
    device = port_name

  all_keys = [test_ui.ESCAPE_KEY, 'R'] + [str(num) for num in range(10)]
  while True:
    ui.SetState(
        _('Please wait for the {device} playback to finish.',
          device=device))

    locale = ui.GetUILocale()
    audio_file = os.path.join(_SOUND_DIRECTORY, locale, '%d.ogg' % pass_digit)
    _PlayAudioFile(dut, audio_file, card, device, channel, sample_rate)

    ui.SetState([
        _('Press the number you hear from {device} to pass the test.<br>'
          'Press "R" to replay.',
          device=device), test_ui.FAIL_KEY_LABEL
    ])

    key = ui.WaitKeysOnce(all_keys)
    if key == test_ui.ESCAPE_KEY:
      raise type_utils.TestFailure('Operator marked test fail.')
    if key == 'R':
      continue

    pressed_num = int(key)
    if pressed_num != pass_digit:
      raise type_utils.TestFailure('Wrong key pressed.')
    break


class AudioTest(test_case.TestCase):
  """Tests audio playback

  It randomly picks a digit to play and checks if the operator presses the
  correct digit. It also prevents key-swiping cheating.
  """
  ARGS = [
      Arg('audio_conf', str, 'Audio config file path', default=None),
      Arg('initial_actions', list,
          'List of [card, actions]. If actions is None, the Initialize method '
          'will be invoked.',
          default=None),
      Arg('output_dev', list,
          'Onput ALSA device. [card_name, sub_device].'
          'For example: ["audio_card", "0"].', default=['0', '0']),
      i18n_arg_utils.I18nArg(
          'port_label', 'Label of audio.', default=_('Internal Speaker')),
      Arg('test_left_right', bool, 'Test left and right channel.',
          default=True),
      Arg('require_headphone', bool, 'Require headphone option', default=False),
      Arg('check_headphone', bool,
          'Check headphone status whether match require_headphone',
          default=False),
      Arg('sample_rate', int,
          'Required sample rate to be played by the device.',
          default=None)
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    if self.args.audio_conf:
      self._dut.audio.LoadConfig(self.args.audio_conf)
    # Tansfer output device format
    self._out_card = self._dut.audio.GetCardIndexByName(self.args.output_dev[0])
    self._out_device = self.args.output_dev[1]

    if self.args.initial_actions is None:
      self._dut.audio.Initialize()
    else:
      for card, action in self.args.initial_actions:
        if not card.isdigit():
          card = self._dut.audio.GetCardIndexByName(card)
        if action is None:
          self._dut.audio.Initialize(card)
        else:
          self._dut.audio.ApplyAudioConfig(action, card)

  def tearDown(self):
    self._dut.audio.RestoreMixerControls()

  def runTest(self):
    if self.args.check_headphone:
      self.DetectHeadphone()

    args = (self.ui, self._dut, self.args.port_label, self._out_card,
            self._out_device)
    kwargs = {}

    if self.args.sample_rate is not None:
      kwargs['sample_rate'] = self.args.sample_rate

    if self.args.test_left_right:
      for c in ['left', 'right']:
        TestAudioDigitPlayback(*args, channel=c, **kwargs)
    else:
      TestAudioDigitPlayback(*args, **kwargs)

  def DetectHeadphone(self):
    if self.args.require_headphone:
      instruction = _('Please plug headphone in.')
    else:
      instruction = _('Please unplug headphone.')

    self.ui.SetState(instruction)
    sync_utils.PollForCondition(
        poll_method=self._CheckHeadphone, poll_interval_secs=0.5,
        condition_name='CheckHeadphone', timeout_secs=10)

  def _CheckHeadphone(self):
    headphone_status = self._dut.audio.GetHeadphoneJackStatus(self._out_card)
    logging.info('Headphone status %s, Require Headphone %s', headphone_status,
                 self.args.require_headphone)
    return headphone_status == self.args.require_headphone
