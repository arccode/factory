# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests audio playback and record."""

from __future__ import print_function

import logging
import os
import random
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import dut
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import FactoryTaskManager
from cros.factory.test.factory_task import InteractiveFactoryTask
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.sync_utils import PollForCondition

_TEST_TITLE = test_ui.MakeLabel('Audio Test',
                                u'音讯测试')
_DIV_CENTER_INSTRUCTION = """
<div id='instruction-center' class='template-instruction'></div>"""
_CSS = '#pass_key {font-size:36px; font-weight:bold;}'

_INSTRUCTION_AUDIO_RANDOM_TEST = lambda d, k: test_ui.MakeLabel(
    '</br>'.join(['Press the number you hear from %s to pass the test.' % d,
                  'Press "%s" to replay.' % k]),
    '</br>'.join([u'请按你从 %s 输出所听到的数字' % d,
                  u'按 %s 重播语音' % k]))

_SOUND_DIRECTORY = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), '..', '..', 'goofy',
    'static', 'sounds')


class AudioDigitPlaybackTask(InteractiveFactoryTask):
  """Task to verify audio playback function.

  It randomly picks a digit to play and checks if the operator presses the
  correct digit. It also prevents key-swiping cheating.
  Note: ext_display.py uses this class to test HDMI audio.

  Args:
    _dut: dut instance
    ui: cros.factory.test.test_ui object.
    port_label: Label name of audio port to output. It should be generated
        using test_ui.MakeLabel to have English/Chinese version.
    title_id: HTML id for placing testing title.
    instruction_id: HTML id for placing instruction.
    card: audio card to output.
    device: audio device to output.
    channel: target channel. Value of 'left', 'right', 'all'. Default 'all'.
  """

  def __init__(self, _dut, ui, port_label, title_id, instruction_id, card,
               device, channel='all'):
    super(AudioDigitPlaybackTask, self).__init__(ui)
    self._dut = _dut
    self._pass_digit = random.randint(0, 9)
    self._out_card = card
    self._out_device = device
    self._port_label = port_label
    self._title_id = title_id
    self._instruction_id = instruction_id
    self._channel = channel

    if channel == 'left':
      self._port_label += test_ui.MakeLabel(' (Left Channel)', u'(左声道)')
    elif channel == 'right':
      self._port_label += test_ui.MakeLabel(' (Right Channel)', u'(右声道)')

  def _InitUI(self):
    self._ui.SetHTML(self._port_label, id=self._title_id)
    self._ui.SetHTML(
        '%s<br>%s' % (_INSTRUCTION_AUDIO_RANDOM_TEST(self._port_label, 'r'),
                      test_ui.MakePassFailKeyLabel(pass_key=False)),
        id=self._instruction_id)
    self.BindPassFailKeys(pass_key=False)

  def Run(self):
    def _PlayDigit(num, channel):
      """Plays digit sound with language from UI.

      Args:
        num: digit number to play.
      """
      lang = self._ui.GetUILanguage()
      base_name = '%d_%s.ogg' % (num, lang)
      with file_utils.UnopenedTemporaryFile(suffix='.wav') as wav_path:
        # Prepare played .wav file
        with file_utils.UnopenedTemporaryFile(suffix='.wav') as temp_wav_path:
          # We genereate stereo sound by default. and mute one channel by sox
          # if needed.
          Spawn(['sox', os.path.join(_SOUND_DIRECTORY, base_name), '-c2',
                 temp_wav_path], log=True, check_call=True)
          if channel == 'left':
            Spawn(['sox', temp_wav_path, wav_path, 'remix', '1', '0'],
                  log=True, check_call=True)
          elif channel == 'right':
            Spawn(['sox', temp_wav_path, wav_path, 'remix', '0', '1'],
                  log=True, check_call=True)
          else:
            Spawn(['mv', temp_wav_path, wav_path],
                  log=True, check_call=True)

        with self._dut.temp.TempFile() as dut_wav_path:
          self._dut.link.Push(wav_path, dut_wav_path)
          self._dut.audio.PlaybackWavFile(dut_wav_path, self._out_card,
                                          self._out_device)

    self._InitUI()

    self.BindDigitKeys(self._pass_digit)
    for k in 'rR':
      self._ui.BindKey(k, lambda _: _PlayDigit(self._pass_digit,
                                               self._channel))
    _PlayDigit(self._pass_digit, self._channel)

  def Cleanup(self):
    self.UnbindDigitKeys()


class DetectHeadphoneTask(InteractiveFactoryTask):
  """Task to wait for headphone connect/disconnect.

  Args:
    _dut: dut instance
    card: output audio card
    ui: cros.factory.test.test_ui object.
    wait_for_connect: True to wait for headphone connect. Otherwise,
        wait for disconnect.
    title_id: HTML id for placing testing title.
    instruction_id: HTML id for placing instruction.
  """

  def __init__(self, _dut, card, ui, wait_for_connect,
               title_id, instruction_id):
    super(DetectHeadphoneTask, self).__init__(ui)
    self._dut = _dut
    self._out_card = card
    self._title_id = title_id
    self._instruction_id = instruction_id
    self._wait_for_connect = wait_for_connect
    if wait_for_connect:
      self._title = test_ui.MakeLabel('Connect Headphone', u'连接耳机')
      self._instruction = test_ui.MakeLabel('Please plug headphone in.',
                                            u'请接上耳机')
    else:
      self._title = test_ui.MakeLabel('Discnnect Headphone', u'移除耳机')
      self._instruction = test_ui.MakeLabel('Please unplug headphone.',
                                            u'请拔下耳机')

  def _InitUI(self):
    self._ui.SetHTML(self._title, id=self._title_id)
    self._ui.SetHTML(
        '%s<br>%s' % (self._instruction,
                      test_ui.MakePassFailKeyLabel(pass_key=False)),
        id=self._instruction_id)
    self.BindPassFailKeys(pass_key=False, fail_later=False)

  def _CheckHeadphone(self):
    headphone_status = self._dut.audio.GetHeadphoneJackStatus(self._out_card)
    logging.info('Headphone status %s, Requre Headphone %s', headphone_status,
                 self._wait_for_connect)
    return headphone_status == self._wait_for_connect

  def Run(self):
    self._InitUI()
    PollForCondition(poll_method=self._CheckHeadphone, poll_interval_secs=0.5,
                     condition_name='CheckHeadphone', timeout_secs=10)
    self.Pass()


class AudioTest(unittest.TestCase):
  """Tests audio playback

  It randomly picks a digit to play and checks if the operator presses the
  correct digit. It also prevents key-swiping cheating.
  """
  ARGS = [
      Arg('audio_conf', str, 'Audio config file path', optional=True),
      Arg('initial_actions', list, 'List of tuple (card_name, actions)', []),
      Arg('output_dev', tuple,
          'Onput ALSA device. (card_name, sub_device).'
          'For example: ("audio_card", "0").', ('0', '0')),
      Arg('port_label', tuple, 'Label of audio (en, zh).',
          default=('Internal Speaker', u'内建喇叭')),
      Arg('test_left_right', bool, 'Test left and right channel.',
          default=True),
      Arg('require_headphone', bool, 'Require headphone option', False),
      Arg('check_headphone', bool,
          'Check headphone status whether match require_headphone', False),
  ]

  def setUp(self):
    self._dut = dut.Create()
    if self.args.audio_conf:
      self._dut.audio.ApplyConfig(self.args.audio_conf)
    # Tansfer output device format
    self._out_card = self._dut.audio.GetCardIndexByName(self.args.output_dev[0])
    self._out_device = self.args.output_dev[1]

    self._ui = test_ui.UI()
    self._template = ui_templates.TwoSections(self._ui)
    self._task_manager = None

    for card, action in self.args.initial_actions:
      card = self._dut.audio.GetCardIndexByName(card)
      self._dut.audio.ApplyAudioConfig(action, card)

  def InitUI(self):
    """Initializes UI.

    Sets test title and draw progress bar.
    """
    self._template.SetTitle(_TEST_TITLE)
    self._template.SetState(_DIV_CENTER_INSTRUCTION)
    self._template.DrawProgressBar()
    self._ui.AppendCSS(_CSS)

  def ComposeTasks(self):
    """Composes subtasks based on dargs.

    Returns:
      A list of AudioDigitPlaybackTask.
    """
    def _ComposeLeftRightTasks(tasks, args):
      if self.args.test_left_right:
        tasks.append(AudioDigitPlaybackTask(*args, **{'channel': 'left'}))
        tasks.append(AudioDigitPlaybackTask(*args, **{'channel': 'right'}))
      else:
        tasks.append(AudioDigitPlaybackTask(*args))

    _TITLE_ID = 'instruction'
    _INSTRUCTION_ID = 'instruction-center'

    tasks = []
    if self.args.check_headphone:
      tasks.append(DetectHeadphoneTask(self._dut, self._out_card, self._ui,
                                       self.args.require_headphone, _TITLE_ID,
                                       _INSTRUCTION_ID))
    args = (self._dut, self._ui, test_ui.MakeLabel(*self.args.port_label),
            _TITLE_ID, _INSTRUCTION_ID, self._out_card, self._out_device)
    _ComposeLeftRightTasks(tasks, args)

    return tasks

  def tearDown(self):
    self._dut.audio.RestoreMixerControls()

  def runTest(self):
    self.InitUI()
    self._task_manager = FactoryTaskManager(
        self._ui, self.ComposeTasks(),
        update_progress=self._template.SetProgressBarValue)
    self._task_manager.Run()
