# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


# DESCRIPTION :
#
# This is a factory test to test the audio.  Operator will test both record and
# playback for headset and built-in audio.  Recordings are played back for
# confirmation.  An additional pre-recorded sample is played to confirm speakers
# operate independently.
# We will test each channel of input and output.


import logging
import os
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.device import device_utils
from cros.factory.test import test_ui
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils import file_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.process_utils import Spawn

_RECORD_SEC = 3
_RECORD_RATE = 48000
_SOUND_DIRECTORY = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'goofy',
    'static', 'sounds')


_MSG_AUDIO_INFO = test_ui.MakeLabel(
    'Press \'P\' to first play a sample for each channel to ensure audio '
    'output works.<br>'
    'Press \'R\' to record %d seconds, Playback will follow<br>'
    'Press space to mark pass' % _RECORD_SEC,
    zh='按 \'P\' 键播放范例<br>'
    '按 \'R\' 键开始录音%d秒，之后会重播录到的声音<br>'
    '压下空白表示成功' % _RECORD_SEC,
    css_class='audio-test-info')
_MSG_RECORD_INFO = test_ui.MakeLabel('Start recording', u'开始录音',
                                     css_class='audio-test-info')
_HTML_AUDIO = """
<table style="width: 70%%; margin: auto;">
  <tr>
    <td align="center"><div id="audio_title"></div></td>
  </tr>
  <tr>
    <td><hr></td>
  </tr>
  <tr>
    <td><div id="audio_info"></div></td>
  </tr>
  <tr>
    <td><hr></td>
  </tr>
</table>
"""

_CSS_AUDIO = """
  .audio-test-title { font-size: 2em; }
  .audio-test-info { font-size: 2em; }
"""

PLAY_SAMPLE_VALUE = (1 << 0)
RECORD_VALUE = (1 << 1)
PASS_VALUE = (PLAY_SAMPLE_VALUE | RECORD_VALUE)


def GetPlaybackRecordLabel(channel):
  return test_ui.MakeLabel('Playback sound (Mic channel %d)' % channel,
                           u'重播录到的声音(麦克风通道%d)' % channel,
                           css_class='audio-test-info')


def GetPlaybackLabel(channel):
  return test_ui.MakeLabel('Playback sound to channel %d' % channel,
                           u'播放范例到通道%d)' % channel,
                           css_class='audio-test-info')


class AudioBasicTest(unittest.TestCase):
  ARGS = [
      Arg('audio_title', tuple, 'Label Title of audio test (en, zh)',
          ('Headset', u'外接耳机')),
      Arg('audio_conf', str, 'Audio config file path', optional=True),
      Arg('initial_actions', list, 'List of tuple (card, actions)', []),
      Arg(
          'input_dev', tuple,
          'Input ALSA device. (card_name, sub_device).'
          'For example: ("audio_card", "0").', ('0', '0')),
      Arg(
          'output_dev', tuple,
          'Output ALSA device. (card_name, sub_device).'
          'For example: ("audio_card", "0").', ('0', '0')),
      Arg('output_channels', int, 'number of output channels.', 2),
      Arg('input_channels', int, 'number of input channels.', 2),
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    if self.args.audio_conf:
      self._dut.audio.ApplyConfig(self.args.audio_conf)

    # Tansfer input and output device format
    self._in_card = self._dut.audio.GetCardIndexByName(self.args.input_dev[0])
    self._in_device = self.args.input_dev[1]
    self._out_card = self._dut.audio.GetCardIndexByName(self.args.output_dev[0])
    self._out_device = self.args.output_dev[1]

    # Init audio card before show html
    for card, action in self.args.initial_actions:
      card = self._dut.audio.GetCardIndexByName(card)
      self._dut.audio.ApplyAudioConfig(action, card)

    # Initialize frontend presentation
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_CSS_AUDIO)
    self.template.SetState(_HTML_AUDIO)
    self.ui.BindKey('R', self.HandleRecordEvent)
    self.ui.BindKey('P', self.HandleSampleEvent)
    self.ui.BindKey(test_ui.SPACE_KEY, self.MarkPass)

    msg_audio_title = test_ui.MakeLabel(
        self.args.audio_title[0], self.args.audio_title[1],
        css_class='audio-test-info')
    self.ui.SetHTML(msg_audio_title, id='audio_title')
    self.ui.SetHTML(_MSG_AUDIO_INFO, id='audio_info')
    self.current_process = None
    self.key_press = None
    # prevent operator from pressing space directly,
    # make sure he presses P and R.
    self.event_value = 0

  def HandleRecordEvent(self, event):
    del event  # Unused.
    if not self.key_press:
      self.key_press = 'R'
      logging.info('start record')
      self.ui.SetHTML(_MSG_RECORD_INFO, id='audio_info')
      dut_record_file_path = self._dut.temp.mktemp(False)
      self._dut.audio.RecordWavFile(dut_record_file_path, self._in_card,
                                    self._in_device, _RECORD_SEC,
                                    self.args.input_channels, _RECORD_RATE)
      logging.info('stop record and start playback')
      # playback the record file by each channel.
      with file_utils.UnopenedTemporaryFile(suffix='.wav') as full_wav_path:
        self._dut.link.Pull(dut_record_file_path, full_wav_path)
        for i in xrange(self.args.input_channels):
          with file_utils.UnopenedTemporaryFile(suffix='.wav') as wav_path:
            # Get channel i from full_wav_path to a stereo wav_path
            # Since most devices support 2 channels.
            Spawn(['sox', full_wav_path, wav_path, 'remix', str(i + 1),
                   str(i + 1)], log=True, check_call=True)
            with self._dut.temp.TempFile() as dut_path:
              self._dut.link.Push(wav_path, dut_path)
              self.ui.SetHTML(GetPlaybackRecordLabel(i + 1), id='audio_info')
              self._dut.audio.PlaybackWavFile(dut_path, self._out_card,
                                              self._out_device)
      self._dut.CheckCall(['rm', '-f', dut_record_file_path])
      self.ui.SetHTML(_MSG_AUDIO_INFO, id='audio_info')
      self.key_press = None
      self.event_value |= RECORD_VALUE

  def HandleSampleEvent(self, event):
    del event  # Unused.
    if not self.key_press:
      self.key_press = 'P'
      logging.info('start play sample')
      lang = self.ui.GetUILanguage()
      for i in xrange(self.args.output_channels):
        ogg_path = os.path.join(_SOUND_DIRECTORY, '%d_%s.ogg' % (i + 1, lang))
        number_wav_path = '%s.wav' % ogg_path
        Spawn(['sox', ogg_path, '-c1', number_wav_path], check_call=True)
        with file_utils.UnopenedTemporaryFile(suffix='.wav') as wav_path:
          # we will only keep (i + 1) channel and mute others.
          # We use number sound to indicate which channel to be played.
          # Create .wav file with n channels but ony has one channel data.
          remix_option = ['0'] * self.args.output_channels
          remix_option[i] = '1'
          Spawn(['sox', number_wav_path, wav_path, 'remix'] + remix_option,
                log=True, check_call=True)
          with self._dut.temp.TempFile() as dut_path:
            self._dut.link.Push(wav_path, dut_path)
            self.ui.SetHTML(GetPlaybackLabel(i + 1), id='audio_info')
            self._dut.audio.PlaybackWavFile(dut_path, self._out_card,
                                            self._out_device)
        os.unlink(number_wav_path)
      logging.info('stop play sample')
      self.ui.SetHTML(_MSG_AUDIO_INFO, id='audio_info')
      self.key_press = None
      self.event_value |= PLAY_SAMPLE_VALUE

  def MarkPass(self, event):
    del event  # Unused.
    if self.event_value == PASS_VALUE:
      self.ui.Pass()

  def runTest(self):
    self.ui.Run()
