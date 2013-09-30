#!/usr/bin/python

# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import yaml

from cros.factory.utils.process_utils import Spawn

_DEFAULT_CONFIG_PATH_ = '/usr/local/factory/py/test/audio.conf'

# Tools from platform/audiotest
AUDIOFUNTEST_PATH = 'audiofuntest'
AUDIOLOOP_PATH = 'looptest'
LOOPBACK_LATENCY_PATH = 'loopback_latency'
SOX_PATH = 'sox'
TEST_TONES_PATH = 'test_tones'

def GetPlaySineArgs(channel, odev='default', freq=1000, duration=10,
                       sample_size=16):
  '''Gets the command args to generate a sine wav to play to odev.

  Args:
    channel: 0 for left, 1 for right; otherwize, mono.
    odev: alsa output device.
    freq: frequency of the generated sine tone.
    duration: duration of the generated sine tone.
    sample_size: output audio sample size. Default to 16.
  '''
  cmdargs = [SOX_PATH, '-b', str(sample_size), '-n', '-t', 'alsa',
             odev, 'synth', str(duration)]
  if channel == 0:
    cmdargs += ['sine', str(freq), 'sine', '0']
  elif channel == 1:
    cmdargs += ['sine', '0', 'sine', str(freq)]
  else:
    cmdargs += ['sine', str(freq)]
  return cmdargs

class AudioUtil(object):

  def __init__(self):
    if os.path.exists(_DEFAULT_CONFIG_PATH_):
      with open(_DEFAULT_CONFIG_PATH_, 'r') as config_file:
        self.audio_config = yaml.load(config_file)
    else:
      self.audio_config = {}
      logging.info('cannot find configuration file.')

  def SetMixerControls(self, mixer_settings=None, card='0'):
    '''Sets all mixer controls listed in the mixer settings on card.

    Args:
      mixer_settings: Mixer settings to set.
      card: Index of audio card to set mixer settings for.
    '''
    logging.info('Setting mixer control values on %s', card)
    for name, value in mixer_settings.items():
      logging.info('Setting %s to %s on card %s', name, value, card)
      command = ['amixer', '-c', card, 'cset', "name='%s'" % name, value]
      Spawn(command, check_call=True)

  def InitialSetting(self):
    self.SetMixerControls(self.audio_config['initial'])

  def EnableSpeaker(self):
    if 'enable_speaker' in self.audio_config:
      self.SetMixerControls(self.audio_config['enable_speaker'])

  def MuteLeftSpeaker(self):
    if 'mute_left_speaker' in self.audio_config:
      self.SetMixerControls(self.audio_config['mute_left_speaker'])

  def MuteRightSpeaker(self):
    if 'mute_right_speaker' in self.audio_config:
      self.SetMixerControls(self.audio_config['mute_right_speaker'])

  def DisableSpeaker(self):
    if 'disable_speaker' in self.audio_config:
      self.SetMixerControls(self.audio_config['disable_speaker'])

  def EnableHeadphone(self):
    if 'enable_headphone' in self.audio_config:
      self.SetMixerControls(self.audio_config['enable_headphone'])

  def MuteLeftHeadphone(self):
    if 'mute_left_headphone' in self.audio_config:
      self.SetMixerControls(self.audio_config['mute_left_headphone'])

  def MuteRightHeadphone(self):
    if 'mute_right_headphone' in self.audio_config:
      self.SetMixerControls(self.audio_config['mute_right_headphone'])

  def DisableHeadphone(self):
    if 'disable_headphone' in self.audio_config:
      self.SetMixerControls(self.audio_config['disable_headphone'])

  def EnableDmic(self):
    if 'enable_dmic' in self.audio_config:
      self.SetMixerControls(self.audio_config['enable_dmic'])

  def MuteLeftDmic(self):
    if 'mute_left_dmic' in self.audio_config:
      self.SetMixerControls(self.audio_config['mute_left_dmic'])

  def MuteRightDmic(self):
    if 'mute_right_dmic' in self.audio_config:
      self.SetMixerControls(self.audio_config['mute_right_dmic'])

  def DisableDmic(self):
    if 'disable_dmic' in self.audio_config:
      self.SetMixerControls(self.audio_config['disable_dmic'])

  def EnableExtmic(self):
    if 'enable_extmic' in self.audio_config:
      self.SetMixerControls(self.audio_config['enable_extmic'])

  def MuteLeftExtmic(self):
    if 'mute_left_extmic' in self.audio_config:
      self.SetMixerControls(self.audio_config['mute_left_extmic'])

  def MuteRightExtmic(self):
    if 'mute_right_extmic' in self.audio_config:
      self.SetMixerControls(self.audio_config['mute_right_extmic'])

  def DisableExtmic(self):
    if 'disable_extmic' in self.audio_config:
      self.SetMixerControls(self.audio_config['disable_extmic'])

