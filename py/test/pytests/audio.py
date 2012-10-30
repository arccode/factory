# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests audio playback and record."""

import random
import unittest

from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import FactoryTaskManager
from cros.factory.test.factory_task import InteractiveFactoryTask
from cros.factory.utils.process_utils import Spawn

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


class AudioDigitPlaybackTask(InteractiveFactoryTask):
  """Task to verify audio playback function.

  It randomly picks a digit to play and checks if the operator presses the
  correct digit. It also prevents key-swiping cheating.

  Args:
    ui: cros.factory.test.test_ui object.
    port_label: Label name of audio port to output. It should be generated
        using test_ui.MakeLabel to have English/Chinese version.
    port_id: ID of audio port to output (w/o "Playback Switch" postfix).
    title_id: HTML id for placing testing title.
    instruction_id: HTML id for placing instruction.
    volume: Playback volume in [0,100]; default 100.
    channel: target channel. Value of 'left', 'right', 'all'. Default 'all'.
  """

  def __init__(self, ui, port_label, port_id, title_id, instruction_id,
               volume=100, channel='all'):
    super(AudioDigitPlaybackTask, self).__init__(ui)
    self._pass_digit = random.randint(0, 9)
    self._port_switch = ['amixer', '-c', '0', 'cset',
                         'name="%s Playback Switch"' % port_id]
    self._port_volume = ['amixer', '-c', '0', 'cset',
                         'name="%s Playback Volume"' % port_id]
    self._port_id = port_id
    self._port_label = port_label
    self._title_id = title_id
    self._instruction_id = instruction_id
    self._channel = channel

    if channel == 'all':
      self._port_volume.append('%d%%,%d%%' % (volume, volume))
    elif channel == 'left':
      self._port_volume.append('%d%%,%d%%' % (volume, 0))
      self._port_label += test_ui.MakeLabel(' (Left Channel)', u'(左声道)')
    elif channel == 'right':
      self._port_volume.append('%d%%,%d%%' % (0, volume))
      self._port_label += test_ui.MakeLabel(' (Right Channel)', u'(右声道)')

  def _InitUI(self):
    self._ui.SetHTML(self._port_label, id=self._title_id)
    self._ui.SetHTML(
      '%s<br>%s' % (_INSTRUCTION_AUDIO_RANDOM_TEST(self._port_label, 'r'),
                    test_ui.MakePassFailKeyLabel(pass_key=False)),
      id=self._instruction_id)
    self.BindPassFailKeys(pass_key=False)

  def Run(self):
    def _HasPlaybackVolume(port_id):
      volumn_name = '%s Playback Volume' % port_id
      if volumn_name in Spawn(['amixer', '-c', '0','controls'],
                              read_stdout=True).stdout_data:
        return True
      return False

    self._InitUI()
    self.RunCommand(self._port_switch + ['on,on'], 'Fail to enable audio.')
    if _HasPlaybackVolume(self._port_id):
      self.RunCommand(self._port_volume, 'Fail to set playback volume.')

    def _PlayVoice(num):
      lang = self._ui.GetUILanguage()
      self._ui.PlayAudioFile('%d_%s.ogg' % (num, lang))

    self.BindDigitKeys(self._pass_digit)
    for k in 'rR':
      self._ui.BindKey(k, lambda _: _PlayVoice(self._pass_digit))
    _PlayVoice(self._pass_digit)

  def Cleanup(self):
    self.UnbindDigitKeys()
    self.RunCommand(self._port_switch + ['off,off'], 'Fail to disable audio.')


class AudioTest(unittest.TestCase):
  """Tests audio playback via both internal and external devices.

  It randomly picks a digit to play and checks if the operator presses the
  correct digit. It also prevents key-swiping cheating.
  """
  ARGS = [
    Arg('internal_port_id', str,
        ('amixer name for internal audio (w/o "Playback Switch" postfix).\n'
         'Use empty string to skip internal audio test.'),
        default='Speaker'),
    Arg('internal_port_label', tuple, 'Label of internal audio (en, zh).',
        default=('Internal Speaker', u'内建喇叭')),
    Arg('internal_volume', int, 'Internal playback volume, default 100%.',
        default=100),
    Arg('external_port_id', str,
        ('amixer name for external audio (w/o "Playback Switch" postfix).\n'
         'Use empty string to skip external audio test.'),
        default='Headphone'),
    Arg('external_port_label', tuple, 'Label of external audio (en, zh).',
        default=('External Headphone', u'外接耳机')),
    Arg('external_volume', int, 'External playback volume, default 100%.',
        default=100),
    Arg('test_left_right', bool, 'Test left and right channel.', default=True)
  ]

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.TwoSections(self._ui)
    self._task_manager = None

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
    if self.args.internal_port_id:
      args = (self._ui, test_ui.MakeLabel(*self.args.internal_port_label),
              self.args.internal_port_id, _TITLE_ID, _INSTRUCTION_ID,
              self.args.internal_volume)
      _ComposeLeftRightTasks(tasks, args)

    if self.args.external_port_id:
      args = (self._ui, test_ui.MakeLabel(*self.args.external_port_label),
              self.args.external_port_id, _TITLE_ID, _INSTRUCTION_ID,
              self.args.external_volume)
      _ComposeLeftRightTasks(tasks, args)

    return tasks

  def runTest(self):
    self.InitUI()
    self._task_manager = FactoryTaskManager(
      self._ui, self.ComposeTasks(),
      update_progress=self._template.SetProgressBarValue)
    self._task_manager.Run()
