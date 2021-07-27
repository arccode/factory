# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test basic audio record and playback.

Description
-----------
This test check both record and playback for headset and built-in audio by
recording audio, play it back and ask operator for confirmation. An additional
pre-recorded sample is played to confirm speakers operate independently. Each
channel of input and output would be tested.

Test Procedure
--------------
1. Instruction is shown on screen to ask operator to press either 'P' or 'R'.
2. After operator press 'P', a pre-recorded sample is played back.
3. After operator press 'R', 3 seconds of audio would be recorded and played
   back.
4. Operator press space key to confirm both 2. and 3. step completes without
   problem, and the audio played back sounds correct.

Dependency
----------
- External program `sox <http://sox.sourceforge.net/>`_.
- Device API ``cros.factory.device.audio``.

Examples
--------
To check that audio can be recorded and played, add this into test list::

  {
    "pytest_name": "audio_basic",
    "args": {
      "input_dev": ["device", "1"],
      "output_dev": ["device", "0"]
    }
  }
"""


import logging
import os

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils


_RECORD_SEC = 3
_RECORD_RATE = 48000
_SOUND_DIRECTORY = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'goofy',
    'static', 'sounds')


class AudioBasicTest(test_case.TestCase):
  ARGS = [
      i18n_arg_utils.I18nArg('audio_title', 'Label Title of audio test',
                             default=_('Headset')),
      Arg('audio_conf', str, 'Audio config file path', default=None),
      Arg(
          'initial_actions', list,
          'List of [card, actions]. If actions is None, the Initialize method '
          'will be invoked.', default=None),
      Arg(
          'input_dev', list, 'Input ALSA device. [card_name, sub_device].'
          'For example: ["audio_card", "0"].', ['0', '0']),
      Arg(
          'output_dev', list, 'Output ALSA device. [card_name, sub_device].'
          'For example: ["audio_card", "0"].', ['0', '0']),
      Arg('output_channels', int, 'number of output channels.', 2),
      Arg('input_channels', int, 'number of input channels.', 2),
      Arg('require_headphone', bool, 'Require headphone option', default=False),
      Arg('timeout_secs', int,
          'The timeout in seconds that the test waits for the headphone.',
          default=30),
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    if self.args.audio_conf:
      self._dut.audio.LoadConfig(self.args.audio_conf)

    self.assertEqual(2, len(self.args.input_dev))
    self.assertEqual(2, len(self.args.output_dev))

    # Transform input and output device format
    self._in_card = self._dut.audio.GetCardIndexByName(self.args.input_dev[0])
    self._in_device = self.args.input_dev[1]
    self._out_card = self._dut.audio.GetCardIndexByName(self.args.output_dev[0])
    self._out_device = self.args.output_dev[1]

    # Init audio card before show html
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

    self.ui.ToggleTemplateClass('font-large', True)
    self.ui.SetInstruction(self.args.audio_title)

    self.done_tests = set()

  def TestRecord(self):
    logging.info('start record')
    self.ui.SetState(_('Start recording'))

    dut_record_file_path = self._dut.temp.mktemp(False)
    self._dut.audio.RecordWavFile(dut_record_file_path, self._in_card,
                                  self._in_device, _RECORD_SEC,
                                  self.args.input_channels, _RECORD_RATE)

    logging.info('stop record and start playback')
    # playback the record file by each channel.
    with file_utils.UnopenedTemporaryFile(suffix='.wav') as full_wav_path:
      self._dut.link.Pull(dut_record_file_path, full_wav_path)
      for channel_idx in range(1, self.args.input_channels + 1):
        with file_utils.UnopenedTemporaryFile(suffix='.wav') as wav_path:
          # Get channel channel_idx from full_wav_path to a stereo wav_path
          # Since most devices support 2 channels.
          remix_option = ['0'] * self.args.output_channels
          remix_option[channel_idx - 1] = str(channel_idx)
          process_utils.Spawn(
              ['sox', full_wav_path, wav_path, 'remix'] + remix_option,
              log=True, check_call=True)
          with self._dut.temp.TempFile() as dut_path:
            self._dut.link.Push(wav_path, dut_path)
            self.ui.SetState(
                _('Playback sound (Mic channel {channel})',
                  channel=channel_idx))
            self._dut.audio.PlaybackWavFile(dut_path, self._out_card,
                                            self._out_device)
    self._dut.CheckCall(['rm', '-f', dut_record_file_path])

  def TestPlay(self):
    logging.info('start play sample')
    locale = self.ui.GetUILocale()
    for channel_idx in range(1, self.args.output_channels + 1):
      ogg_path = os.path.join(_SOUND_DIRECTORY, locale, '%d.ogg' % channel_idx)
      number_wav_path = '%s.wav' % ogg_path
      process_utils.Spawn(
          ['sox', ogg_path, '-c1', number_wav_path], check_call=True)
      with file_utils.UnopenedTemporaryFile(suffix='.wav') as wav_path:
        # we will only keep channel_idx channel and mute others.
        # We use number sound to indicate which channel to be played.
        # Create .wav file with n channels but only has one channel data.
        remix_option = ['0'] * self.args.output_channels
        remix_option[channel_idx - 1] = '1'
        process_utils.Spawn(
            ['sox', number_wav_path, wav_path, 'remix'] + remix_option,
            log=True, check_call=True)
        with self._dut.temp.TempFile() as dut_path:
          self._dut.link.Push(wav_path, dut_path)
          self.ui.SetState(
              _('Playback sound to channel {channel}', channel=channel_idx))
          self._dut.audio.PlaybackWavFile(dut_path, self._out_card,
                                          self._out_device)
      os.unlink(number_wav_path)
    logging.info('stop play sample')

  def runTest(self):
    if self.args.require_headphone:
      self.ui.SetState(_("Please plug headphone in."))
      sync_utils.PollForCondition(
          poll_method=self._dut.audio.GetHeadphoneJackStatus,
          poll_interval_secs=1, condition_name=True,
          timeout_secs=self.args.timeout_secs)
    while True:
      self.ui.SetState(
          _("Press 'P' to first play a sample for each channel to ensure "
            'audio output works.<br>'
            "Press 'R' to record {record_sec} seconds, Playback will "
            'follow.<br>'
            'Press space to mark pass.',
            record_sec=_RECORD_SEC))
      key_pressed = self.ui.WaitKeysOnce(['P', 'R', test_ui.SPACE_KEY])
      if key_pressed == 'P':
        self.TestPlay()
        self.done_tests.add('P')
      elif key_pressed == 'R':
        self.TestRecord()
        self.done_tests.add('R')
      else:
        # prevent operator from pressing space directly,
        # make sure they press P and R.
        if self.done_tests == set(['P', 'R']):
          break
