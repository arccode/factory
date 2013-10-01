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

def GetPlaySineArgs(channel, odev='default', freq=1000, duration_secs=10,
                       sample_size=16):
  """Gets the command args to generate a sine wav to play to odev.

  Args:
    channel: 0 for left, 1 for right; otherwize, mono.
    odev: ALSA output device.
    freq: frequency of the generated sine tone.
    duration_secs: duration of the generated sine tone.
    sample_size: output audio sample size. Default to 16.
  """
  cmdargs = [SOX_PATH, '-b', str(sample_size), '-n', '-t', 'alsa',
             odev, 'synth', str(duration_secs)]
  if channel == 0:
    cmdargs += ['sine', str(freq), 'sine', '0']
  elif channel == 1:
    cmdargs += ['sine', '0', 'sine', str(freq)]
  else:
    cmdargs += ['sine', str(freq)]
  return cmdargs


class AudioUtil(object):
  """This class is used for setting audio related configuration.
  It reads audio.conf initially to decide how to enable/disable each
  component by amixer.
  """
  def __init__(self):
    if os.path.exists(_DEFAULT_CONFIG_PATH_):
      with open(_DEFAULT_CONFIG_PATH_, 'r') as config_file:
        self.audio_config = yaml.load(config_file)
    else:
      self.audio_config = {}
      logging.info('Cannot find configuration file.')

  def SetMixerControls(self, mixer_settings, card='0'):
    """Sets all mixer controls listed in the mixer settings on card.

    Args:
      mixer_settings: A dict of mixer settings to set.
      card: Index of audio card to set mixer settings for.
    """
    logging.info('Setting mixer control values on %s', card)
    for name, value in mixer_settings.items():
      logging.info('Setting %s to %s on card %s', name, value, card)
      command = ['amixer', '-c', card, 'cset', "name='%s'" % name, value]
      Spawn(command, check_call=True)

  def ApplyAudioConfig(self, attribute_name):
    if attribute_name in self.audio_config:
      self.SetMixerControls(self.audio_config[attribute_name])

  def InitialSetting(self):
    self.ApplyAudioConfig('initial')

  def EnableSpeaker(self):
    self.ApplyAudioConfig('enable_speaker')

  def MuteLeftSpeaker(self):
    self.ApplyAudioConfig('mute_left_speaker')

  def MuteRightSpeaker(self):
    self.ApplyAudioConfig('mute_right_speaker')

  def DisableSpeaker(self):
    self.ApplyAudioConfig('disable_speaker')

  def EnableHeadphone(self):
    self.ApplyAudioConfig('enable_headphone')

  def MuteLeftHeadphone(self):
    self.ApplyAudioConfig('mute_left_headphone')

  def MuteRightHeadphone(self):
    self.ApplyAudioConfig('mute_right_headphone')

  def DisableHeadphone(self):
    self.ApplyAudioConfig('disable_headphone')

  def EnableDmic(self):
    self.ApplyAudioConfig('enable_dmic')

  def MuteLeftDmic(self):
    self.ApplyAudioConfig('mute_left_dmic')

  def MuteRightDmic(self):
    self.ApplyAudioConfig('mute_right_dmic')

  def DisableDmic(self):
    self.ApplyAudioConfig('disable_dmic')

  def EnableExtmic(self):
    self.ApplyAudioConfig('enable_extmic')

  def MuteLeftExtmic(self):
    self.ApplyAudioConfig('mute_left_extmic')

  def MuteRightExtmic(self):
    self.ApplyAudioConfig('mute_right_extmic')

  def DisableExtmic(self):
    self.ApplyAudioConfig('disable_extmic')
