# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


# DESCRIPTION :
#
# This is a factory test to test the audio.  Operator will test both record and
# playback for headset and built-in audio.  Recordings are played back for
# confirmation.  An additional pre-recorded sample is played to confirm speakers
# operate independently


import logging
import os
import unittest

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.process_utils import Spawn, TerminateOrKillProcess

_CMD_PLAY_AUDIO = ['aplay', '-D', 'hw:0,0']
_CMD_RECORD_AUDIO = ['arecord', '-D', 'hw:0,0', '-f', 'dat', '-t', 'wav']
_CMD_CONFIG_AUDIO = ['amixer', '-c', '0', 'cset']
_SAMPLE_FILE = 'fhorn.wav'

_MSG_AUDIO_INFO = test_ui.MakeLabel(
    'Press & hold \'R\' to record, Playback will follow<br>'
    'Press & hold \'P\' to play sample<br>'
    'Press space to mark pass',
    zh='压住 \'R\' 键开始录音，之后会重播录到的声音<br>'
    '压住 \'P\' 键播放范例<br>'
    '压下空白表示成功',
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

_JS_AUDIO = """
window.onkeydown = function(event) {
  if (event.keyCode == 82) { // 'R'
    test.sendTestEvent("HandleRecordEvent", 'start');
  } else if (event.keyCode == 80) { // 'P'
    test.sendTestEvent("HandleSampleEvent", 'start');
  } else if (event.keyCode == 32) { // space
    test.sendTestEvent("MarkPass", '');
  }
}

window.onkeyup = function(event) {
  if (event.keyCode == 82) { // 'R'
    test.sendTestEvent("HandleRecordEvent", 'stop');
  } else if (event.keyCode == 80) { // 'P'
    test.sendTestEvent("HandleSampleEvent", 'stop');
  }
}
"""

class AudioBasicTest(unittest.TestCase):
  ARGS = [
    Arg('audio_title', str, 'Title of audio test', 'Headset Audio Test'),
    Arg('amixer_init_config', list, 'Initial config of amixer', None,
        optional=True)
  ]

  def setUp(self):
    # Initialize frontend presentation
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_CSS_AUDIO)
    self.template.SetState(_HTML_AUDIO)
    self.ui.RunJS(_JS_AUDIO)
    msg_audio_title = test_ui.MakeLabel(
        self.args.audio_title,
        css_class='audio-test-info')
    self.ui.SetHTML(msg_audio_title, id='audio_title')
    self.ui.SetHTML(_MSG_AUDIO_INFO, id='audio_info')
    self.current_process = None
    self.key_press = None
    base = os.path.dirname(os.path.realpath(__file__))
    self.file_path = os.path.join(base, '..', '..', 'goofy', 'static', 'sounds',
        _SAMPLE_FILE)

    if self.args.amixer_init_config:
      self.ConfigAmixerSetting(self.args.amixer_init_config)

    self.ui.AddEventHandler('HandleRecordEvent', self.HandleRecordEvent)
    self.ui.AddEventHandler('HandleSampleEvent', self.HandleSampleEvent)
    self.ui.AddEventHandler('MarkPass', self.MarkPass)

  def ConfigAmixerSetting(self, config_list):
    for config in config_list:
      command = _CMD_CONFIG_AUDIO + ["name='%s'" % config['name'],
          config['value']]
      Spawn(command, check_call=True)

  def HandleRecordEvent(self, event):
    if event.data == 'start' and not self.key_press:
      self.key_press = 'R'
      logging.info('start record')
      self.current_process = Spawn(_CMD_RECORD_AUDIO + ['/tmp/rec.wav'])
    elif event.data == 'stop' and self.key_press == 'R':
      TerminateOrKillProcess(self.current_process)
      logging.info('stop record and start playback')
      Spawn(_CMD_PLAY_AUDIO + ['/tmp/rec.wav'], check_call=True)
      self.key_press = None

  def HandleSampleEvent(self, event):
    if event.data == 'start' and not self.key_press:
      self.key_press = 'P'
      logging.info('start play sample')
      self.current_process = Spawn(_CMD_PLAY_AUDIO + [self.file_path])
    elif event.data == 'stop' and self.key_press == 'P':
      TerminateOrKillProcess(self.current_process)
      logging.info('stop play sample')
      self.key_press = None

  def MarkPass(self, event): # pylint: disable=W0613
    self.ui.Pass()

  def runTest(self):
    self.ui.Run()
