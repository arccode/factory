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

_TEST_TITLE = test_ui.MakeLabel('Audio Test',
                                u'音讯测试')
_DIV_CENTER_INSTRUCTION = """
<div id='instruction-center' class='template-instruction'></div>"""
_CSS = '#pass_key {font-size:36px; font-weight:bold;}'

_TITLE_AUDIO_RANDOM_TEST = lambda l: test_ui.MakeLabel('%s Audio' % l,
                                                       u'%s音讯' % l)
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
    port_label: Label name of audio port to output.
    port_id: ID of audio port to output.
    title_id: HTML id for placing testing title.
    instruction_id: HTML id for placing instruction.
  """

  def __init__(self, ui, port_label, port_id, title_id, instruction_id):
    super(AudioDigitPlaybackTask, self).__init__(ui)
    self._pass_digit = random.randint(0, 9)
    self._audio_mixer = ['amixer', '-c', '0', 'cset', 'name="%s"' % port_id]
    self._port_label = port_label
    self._title_id = title_id
    self._instruction_id = instruction_id

  def _InitUI(self):
    self._ui.SetHTML(_TITLE_AUDIO_RANDOM_TEST(self._port_label),
                     id=self._title_id)
    self._ui.SetHTML(
      '%s<br>%s' % (_INSTRUCTION_AUDIO_RANDOM_TEST(self._port_label, 'r'),
                    test_ui.MakePassFailKeyLabel(pass_key=False)),
      id=self._instruction_id)
    self.BindPassFailKeys(pass_key=False)

  def Run(self):
    self._InitUI()
    self.RunCommand(self._audio_mixer + ['on,on'], 'Fail to enable audio.')

    def _PlayVoice(num):
      lang = self._ui.GetUILanguage()
      self._ui.PlayAudioFile('%d_%s.ogg' % (num, lang))

    self.BindDigitKeys(self._pass_digit)
    for k in 'rR':
      self._ui.BindKey(k, lambda _: _PlayVoice(self._pass_digit))
    _PlayVoice(self._pass_digit)

  def Cleanup(self):
    self.UnbindDigitKeys()
    self.RunCommand(self._audio_mixer + ['off,off'], 'Fail to disable audio.')


class AudioTest(unittest.TestCase):
  """Tests audio playback via both internal and external devices.

  It randomly picks a digit to play and checks if the operator presses the
  correct digit. It also prevents key-swiping cheating.
  """
  ARGS = [
    Arg('internal_port_id', str, 'amixer ID for internal audio.',
        optional=True),
    Arg('external_port_id', str, 'amixer ID for external audio.',
        optional=True),
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
    tasks = []
    if self.args.internal_port_id:
      tasks.append(AudioDigitPlaybackTask(
          self._ui, 'Internal', self.args.internal_port_id,
          'instruction', 'instruction-center'))
    if self.args.external_port_id:
      tasks.append(AudioDigitPlaybackTask(
          self._ui, 'External', self.args.external_port_id,
          'instruction', 'instruction-center'))
    return tasks

  def runTest(self):
    self.InitUI()
    self._task_manager = FactoryTaskManager(
      self._ui, self.ComposeTasks(),
      update_progress=self._template.SetProgressBarValue)
    self._task_manager.Run()
