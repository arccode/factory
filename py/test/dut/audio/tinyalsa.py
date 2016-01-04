#!/usr/bin/python

# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
This is audio utility module to setup tinymix related options.
"""

from __future__ import print_function

import copy
import logging
import os
import re
import tempfile
import time
from multiprocessing import Process

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut.audio import base

# Configuration file is put under overlay directory and it can be customized
# for each board.
# Configuration file is using YAML nested collections format.
#
# Structure of this configuration file:
# card_index:
#   action:
#     "tinymix configuration name": "value"
#
# =============== Configuration Example ===================
# 0:
#   enable_dmic:
#     "DIGMICL Switch": "on"
#     "DIGMICR Switch": "on"
#   disable_dmic:
#     "DIGMICL Switch": "off"
#     "DIGMICR Switch": "off"
# =========================================================


class TinyalsaAudioControl(base.BaseAudioControl):
  """This class is used for setting audio related configuration.
  It reads audio.conf initially to decide how to enable/disable each
  component by tinymixer.
  """

  _RE_CARD_INDEX = re.compile(r'.*(\d+).*?\[(.+?)\]')

  def __init__(self, dut, config_path=base.DEFAULT_CONFIG_PATH,
               remote_directory='/data'):
    super(TinyalsaAudioControl, self).__init__(dut, config_path)
    self._remote_directory = remote_directory

  def GetCardIndexByName(self, card_name):
    """See BaseAudioControl.GetCardIndexByName"""
    if card_name.isdigit():
      return card_name
    output = self._dut.CallOutput(['cat', '/proc/asound/cards'])
    for line in output.splitlines():
      m = self._RE_CARD_INDEX.match(line)
      if m and m.group(2) == card_name:
        return m.group(1)
    raise ValueError('device name %s is incorrect' % card_name)

  def _GetMixerControlsByLines(self, name, lines):
    """Get Mixer control value by the tinymix results"""
    # Try Enum value
    m = re.search(r'.*%s:.*\t>.*' % name, lines, re.MULTILINE)
    if m:
      values = m.group(0).split('\t')
      # Find the value start with '>', and return value
      for s in values:
        if s.startswith('>'):
          return s[1:]
    # Try Int value
    m = re.search(r'.*%s: (.*) \(range.*' % name, lines, re.MULTILINE)
    if m:
      value = m.group(1)
      return value
    # Try Bool value
    m = re.search(r'.*%s: (On|Off).*' % name, lines, re.MULTILINE)
    if m:
      value = m.group(1)
      # translate value to the control usage.
      # tinymix can't accept On/Off for SetMixer
      if value == 'Off':
        value = '0'
      elif value == 'On':
        value = '1'
      return value

    logging.info('Unable to get value for mixer control \'%s\'', name)
    return None

  def GetMixerControls(self, name, card='0'):
    """See BaseAudioControl.GetMixerControls """
    command = ['tinymix', '-D', card, name]
    lines = self._dut.CheckOutput(command)
    return self._GetMixerControlsByLines(name, lines)

  def _PushAndExecute(self, push_path, pull_path=None):
    """Push file to dut and execute it and then get result file back
    The function will not leave the files on the dut.
    So it will remove them after execution and pull.

    Args:
      push_path: The file path to be pushed in Fixture
      pull_path: The file path to be pulled in Fixture
    """
    filename = os.path.basename(push_path)
    remote_path = os.path.join(self._remote_directory, filename)
    self._dut.link.Push(push_path, remote_path)
    self._dut.Call(['chmod', '777', remote_path])
    self._dut.Call(remote_path)
    self._dut.Call(['rm', '-f', remote_path])
    if pull_path:
      filename = os.path.basename(pull_path)
      remote_path = os.path.join(self._remote_directory, filename)
      self._dut.link.Pull(remote_path, pull_path)
      self._dut.Call(['rm', '-f', remote_path])

  def _GenerateGetOldValueShellScript(self, open_file, output_file,
                                      mixer_settings, card):
    """Generate a bash file to get tinymix old value"""
    result_file = os.path.basename(output_file.name)
    result_path = os.path.join(self._remote_directory, result_file)
    for name in mixer_settings:
      open_file.write('tinymix -D %s \'%s\' >> %s\n' % (card, name,
                                                        result_path))

  def _GenerateSetValueShellScript(self, open_file, mixer_settings, card):
    """Generate a bash file to get tinymix old value"""
    for name, value in mixer_settings.items():
      logging.info('Set \'%s\' to \'%s\' on card %s', name, value, card)
      open_file.write('tinymix -D %s \'%s\' \'%s\'\n' % (card, name, value))

  def _GetMixerSettingsNotInStack(self, mixer_settings, card):
    """Gets mixer settings not yet stored in the stack.

    Args:
      mixer_settings: A dict of mixer settings to set.
      card: The index of audio card
    """
    new_settings = copy.deepcopy(mixer_settings)
    for store_settings, store_card in self._restore_mixer_control_stack:
      if card != store_card:
        continue
      for name in new_settings.keys():
        if name in store_settings:
          del new_settings[name]
      if not new_settings:
        break

    return new_settings

  def SetMixerControls(self, mixer_settings, card='0', store=True):
    """Sets all mixer controls listed in the mixer settings on card.
    ADB is too slow to execute command one by one.
    So we will do batch execution

    Args:
      mixer_settings: A dict of mixer settings to set.
      card: The index of audio card
      store: Store the current value so it can be restored later using
        RestoreMixerControls.
    """
    logging.info('Setting mixer control values on card %s, store %s',
                 card, store)
    restore_mixer_settings = dict()
    if store:
      new_mixer_settings_to_store = \
          self._GetMixerSettingsNotInStack(mixer_settings, card)
      if new_mixer_settings_to_store:
        with tempfile.NamedTemporaryFile() as get_sh_file:
          with tempfile.NamedTemporaryFile() as output:
            self._GenerateGetOldValueShellScript(get_sh_file, output,
                                                 new_mixer_settings_to_store,
                                                 card)
            get_sh_file.flush()
            self._PushAndExecute(get_sh_file.name, output.name)
            lines = open(output.name).read()
            for name in new_mixer_settings_to_store:
              old_value = self._GetMixerControlsByLines(name, lines)
              restore_mixer_settings[name] = old_value
              logging.info('Save \'%s\' with value \'%s\' on card %s',
                           name, old_value, card)
            self._restore_mixer_control_stack.append((restore_mixer_settings,
                                                      card))
    # Set Mixer controls
    with tempfile.NamedTemporaryFile() as set_sh_file:
      self._GenerateSetValueShellScript(set_sh_file, mixer_settings, card)
      set_sh_file.flush()
      self._PushAndExecute(set_sh_file.name)

  def _GetPIDByName(self, name):
    """Used to get process ID"""
    lines = self._dut.CallOutput(['ps', name])
    m = re.search(r'\w+\s+(\d+).*%s' % name, lines, re.MULTILINE)
    if m:
      pid = m.group(1)
      return pid
    else:
      return None

  def CreateAudioLoop(self, in_card, in_dev, out_card, out_dev):
    """Create an audio loop by tinyloop.
    Currently, we only support one audio loop a time
    It will put the tinyloop thread to background to prevent block current
    thread.
    Use DestroyAudioLoop to destroy the audio loop

    Args:
      in_card: input card
      in_dev: input device
      out_card: output card
      out_dev: output device
    """
    # Make sure we only have on audio loop.
    self.DestroyAudioLoop()

    # TODO(mojahsu): try to figure out why CheckCall will be hang.
    # We can workaround it by Spawn with ['adb', 'shell'].
    # It will have problem is the dut is not android device
    command = 'loopback.sh'
    self._dut.CheckCall(command)
    pid = self._GetPIDByName('tinycap_stdout')

    logging.info('Create tinyloop pid %s for input %s,%s output %s,%s',
                 pid, in_card, in_dev, out_card, out_dev)

  def DestroyAudioLoop(self):
    pid = self._GetPIDByName('tinycap_stdout')
    if pid:
      logging.info('Destroy audio loop with pid %s', pid)
      command = ['kill', pid]
      self._dut.CheckCall(command)
    else:
      logging.info('Destroy audio loop - not found tinycap_stdout pid')

  def _PlaybackWavFile(self, path, card, device):
    """See BaseAudioControl._PlaybackWavFile"""
    self._dut.Call(['tinyplay', path, '-D', card, '-d', device])

  def _StopPlaybackWavFile(self):
    """See BaseAudioControl._StopPlaybackWavFile"""
    pid = self._GetPIDByName('tinyplay')
    if pid:
      self._dut.Call(['kill', pid])

  def RecordWavFile(self, path, card, device, duration, channels, rate):
    """See BaseAudioControl.RecordWavFile
    Since there is no duration parameter in the tinycap. We use a thread to
    simulate it. We will use a thread to execute tinycap for recording and after
    the specified duration, we will send a Ctrl-C singal to the tinycap process
    to let it know it should stop recording and save to .wav file.
    """
    record_process = Process(target=lambda:
                             self._dut.Call(['tinycap', path, '-D', card, '-d',
                                             device, '-c', str(channels), '-r',
                                             str(rate)]))
    record_process.start()
    pid = self._GetPIDByName('tinycap')
    logging.info('tinycap pid %s, record duratrion %d seconds', pid, duration)
    time.sleep(duration)
    logging.info('Try to send Ctrl-C singnal to pid %s', pid)
    if not pid:
      raise RuntimeError('Can\'t find tinycap process!')

    self._dut.Call(['kill', '-SIGINT', pid])
    record_process.join()
