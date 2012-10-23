# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests audio playback and record."""

import random
from cros.factory.test import test_ui
from cros.factory.test.factory_task import InteractiveFactoryTask

_MSG_AUDIO_RANDOM_TEST = lambda d, k: test_ui.MakeLabel(
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
    self._ui.SetHTML(test_ui.MakeLabel('%s Audio' % self._port_label,
                                       u'%s 音讯' % self._port_label),
                     id=self._title_id)
    self._ui.SetHTML(
      '%s<br>%s' % (_MSG_AUDIO_RANDOM_TEST(self._port_label, 'r'),
                    test_ui.MakePassFailKeyLabel(pass_key=False)),
      id=self._instruction_id)
    self.BindPassFailKeys(pass_key=False)

  def Run(self):
    self._InitUI()
    self.RunCommand(self._audio_mixer + ['on'], 'Fail to enable audio.')

    def _PlayVoice(num):
      lang = self._ui.GetUILanguage()
      self._ui.PlayAudioFile('%d_%s.ogg' % (num, lang))

    self.BindDigitKeys(self._pass_digit)
    for k in 'rR':
      self._ui.BindKey(k, lambda _: _PlayVoice(self._pass_digit))
    _PlayVoice(self._pass_digit)

  def Cleanup(self):
    self.UnbindDigitKeys()
    self.RunCommand(self._audio_mixer + ['off'], 'Fail to disable audio.')
