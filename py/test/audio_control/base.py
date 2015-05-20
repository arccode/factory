#!/usr/bin/python

# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is audio control utility base module """

import logging
import os
import yaml

import factory_common  # pylint: disable=W0611
from glob import glob
from cros.factory.test.utils import Enum
from cros.factory.utils.process_utils import Spawn

_DEFAULT_CONFIG_PATH = '/usr/local/factory/py/test/audio.conf'

# Strings for key in audio.conf
HP_JACK_NAME = 'headphone_jack'
MIC_JACK_NAME = 'mic_jack'
HP_JACK_DETECT = 'headphone_jack_detect'
MIC_JACK_DETECT = 'mic_jack_detect'
MIC_JACK_TYPE_DETECT = 'mic_jack_type_detect'

DEFAULT_HEADPHONE_JACK_NAMES = ['Headphone Jack', 'Headset Jack']
# The input device event may be on Headphone Jack
DEFAULT_MIC_JACK_NAMES = ['Mic Jack'] + DEFAULT_HEADPHONE_JACK_NAMES

MicJackType = Enum(['none', 'lrgm', 'lrmg'])
# Used for external command return value
MIC_JACK_TYPE_RETURN_LRGM = '1'
MIC_JACK_TYPE_RETURN_LRMG = '2'


class BaseAudioControl(object):
  """An abstract class for different target audio utils"""

  def __init__(self, dut=None, config_path=_DEFAULT_CONFIG_PATH):
    # used for audio config logging.
    self._audio_config_sn = 0
    self._restore_mixer_control_stack = []
    self._dut = dut
    if os.path.exists(config_path):
      with open(config_path, 'r') as config_file:
        self.audio_config = yaml.load(config_file)
      for index in self.audio_config.keys():
        if index.isdigit() is False:
          new_index = self.GetCardIndexByName(index)
          self.audio_config[new_index] = self.audio_config[index]
    else:
      self.audio_config = {}
      logging.info('Cannot find configuration file.')

  def CheckOutput(self, command):
    """
    Execute command by current dut status.
    If we have dut instance, we will use dut to execute command.
    Otherwise we use original way to execute command.
    Args:
      command: the command to be executed
        It is a list of whole command.
        e.g. ['cmd', 'option1', 'option2']
    Returns:
        standard output
    """
    if not self._dut:
      query = Spawn(command, read_stdout=True, log=True)
      return query.stdout_data
    # Use dut wrapper to execute command
    return self._dut.CheckOutput(command)

  def CheckCall(self, command):
    """
    Execute command by current dut status.
    If we have dut instance, we will use dut to execute command.
    Otherwise we use original way to execute command.
    Args:
      command: the command to be executed
        It is a list of whole command.
        e.g. ['cmd', 'option1', 'option2']
    Returns:
        return code
    """
    if not self._dut:
      query = Spawn(command, read_stdout=True, log=True)
      return query.returncode
    # Use dut wrapper to execute command
    return self._dut.CheckCall(command)

  def GetCardIndexByName(self, card_name):
    """Get audio card index by card name.

    Args:
      card_name: Audio card name.

    Returns:
      Card index of the card name.

    Raises:
      ValueError when card name does not exist.
    """
    raise NotImplementedError

  def GetMixerControls(self, name, card='0'):
    """Gets the value for mixer control.

    Args:
      name: The name of mixer control
      card: The index of audio card
    """
    raise NotImplementedError

  def SetMixerControls(self, mixer_settings, card='0', store=True):
    """Sets all mixer controls listed in the mixer settings on card.

    Args:
      mixer_settings: A dict of mixer settings to set.
      card: The index of audio card
      store: Store the current value so it can be restored later using
        RestoreMixerControls.
    """
    raise NotImplementedError

  def RestoreMixerControls(self):
    """Restores the mixer controls stored in _restore_mixer_control_stack.

    Also, clear _restore_mixer_control_stack.
    """
    while self._restore_mixer_control_stack:
      mixer_settings, card = self._restore_mixer_control_stack.pop()
      self.SetMixerControls(mixer_settings, card, False)
    self._restore_mixer_control_stack = []

  def FindEventDeviceByName(self, name):
    """Finds the event device by matching name.

    Args:
      name: The name to look up event device by substring matching.

    Returns:
      The full name of the found event device of form /dev/input/event*
    """
    for evdev in glob('/dev/input/event*'):
      f = open(os.path.join('/sys/class/input/',
                            os.path.basename(evdev),
                            'device/name'),
               'r')
      evdev_name = f.read()
      if evdev_name.find(name) != -1:
        logging.info('Find %s Event Device %s', name, evdev)
        return evdev
    return None

  def GetHeadphoneJackStatus(self, card='0'):
    """Gets the plug/unplug status of headphone jack.

    Args:
      card: The index of audio card.

    Returns:
      True if headphone jack is plugged, False otherwise.
    """
    status = None

    if card in self.audio_config and HP_JACK_DETECT in self.audio_config[card]:
      command = self.audio_config[card][HP_JACK_DETECT]
      logging.info('Getting headphone jack status by %s', command)
      stdout_data = self.CheckOutput(command)
      jack_status = stdout_data.strip()
      status = True if jack_status == '1' else False
      logging.info('headphone jack status %s', status)
      return status

    possible_names = []
    if card in self.audio_config and HP_JACK_NAME in self.audio_config[card]:
      possible_names = [self.audio_config[card][HP_JACK_NAME]]
    else:
      possible_names = DEFAULT_HEADPHONE_JACK_NAMES

    # Loops through possible names. Uses mixer control or evtest
    # to query jack status.
    for hp_jack_name in possible_names:
      values = self.GetMixerControls(hp_jack_name, card)
      if values:
        status = True if values == 'on' else False
        break

      # Check input device for headphone
      evdev = self.FindEventDeviceByName(hp_jack_name)
      if evdev:
        command = ['evtest', '--query', evdev, 'EV_SW', 'SW_HEADPHONE_INSERT']
        returncode = self.CheckCall(command)
        status = (returncode != 0)
        break

    logging.info('Getting headphone jack status %s', status)
    if status is None:
      raise ValueError('No methods to get headphone jack status')

    return status

  def GetMicJackStatus(self, card='0'):
    """Gets the plug/unplug status of mic jack.

    Args:
      card: The index of audio card.

    Returns:
      True if mic jack is plugged, False otherwise.
    """
    status = None

    if card in self.audio_config and MIC_JACK_DETECT in self.audio_config[card]:
      command = self.audio_config[card][MIC_JACK_DETECT]
      logging.info('Getting microphone jack status by %s', command)
      stdout_data = self.CheckOutput(command)
      jack_status = stdout_data.strip()
      status = True if jack_status == '1' else False
      logging.info('microphone jack status %s', status)
      return status

    possible_names = []
    if card in self.audio_config and MIC_JACK_NAME in self.audio_config[card]:
      possible_names = [self.audio_config[card][MIC_JACK_NAME]]
    else:
      possible_names = DEFAULT_MIC_JACK_NAMES

    # Loops through possible names. Uses mixer control or evtest
    # to query jack status.
    for jack_name in possible_names:
      values = self.GetMixerControls(jack_name, card)
      if values:
        status = True if values == 'on' else False
        break

      evdev = self.FindEventDeviceByName(jack_name)
      if evdev:
        command = ['evtest', '--query', evdev, 'EV_SW', 'SW_MICROPHONE_INSERT']
        returncode = self.CheckCall(command)
        status = (returncode != 0)
        break

    logging.info('Getting microphone jack status %s', status)
    if status is None:
      raise ValueError('No methods to get microphone jack status')

    return status

  def GetMicJackType(self, card='0'):
    """Gets the mic jack type.

    Args:
      card: The index of audio card.

    Returns:
      MicJackType enum value to indicate the mic jack type.
    """
    mictype = None
    if (card in self.audio_config and
        MIC_JACK_TYPE_DETECT in self.audio_config[card]):
      command = self.audio_config[card][MIC_JACK_TYPE_DETECT]
      logging.info('Getting mic jack type by %s', command)
      stdout_data = self.CheckOutput(command)
      type_status = stdout_data.strip()
      if type_status == MIC_JACK_TYPE_RETURN_LRGM:
        mictype = MicJackType.lrgm
      elif type_status == MIC_JACK_TYPE_RETURN_LRMG:
        mictype = MicJackType.lrmg
      else:
        mictype = MicJackType.none

    logging.info('Getting mic jack type %s', mictype)
    if mictype is None:
      raise ValueError('No methods to get mic jack type')

    return mictype

  def ApplyAudioConfig(self, action, card='0'):
    if card in self.audio_config:
      if action in self.audio_config[card]:
        logging.info('\nvvv-- Do(%d) \'%s\' on card %s Start --vvv',
                     self._audio_config_sn, action, card)
        self.SetMixerControls(self.audio_config[card][action], card)
        logging.info('\n^^^-- Do(%d) \'%s\' on card %s End   --^^^',
                     self._audio_config_sn, action, card)
        self._audio_config_sn += 1
      else:
        logging.info('Action %s cannot be found in card %s', action, card)
    else:
      logging.info('Card %s does not exist', card)

  def InitialSetting(self, card='0'):
    self.ApplyAudioConfig('initial', card)

  def EnableSpeaker(self, card='0'):
    self.ApplyAudioConfig('enable_speaker', card)

  def MuteLeftSpeaker(self, card='0'):
    self.ApplyAudioConfig('mute_left_speaker', card)

  def MuteRightSpeaker(self, card='0'):
    self.ApplyAudioConfig('mute_right_speaker', card)

  def DisableSpeaker(self, card='0'):
    self.ApplyAudioConfig('disable_speaker', card)

  def EnableHeadphone(self, card='0'):
    self.ApplyAudioConfig('enable_headphone', card)

  def MuteLeftHeadphone(self, card='0'):
    self.ApplyAudioConfig('mute_left_headphone', card)

  def MuteRightHeadphone(self, card='0'):
    self.ApplyAudioConfig('mute_right_headphone', card)

  def DisableHeadphone(self, card='0'):
    self.ApplyAudioConfig('disable_headphone', card)

  def EnableDmic(self, card='0'):
    self.ApplyAudioConfig('enable_dmic', card)

  def MuteLeftDmic(self, card='0'):
    self.ApplyAudioConfig('mute_left_dmic', card)

  def MuteRightDmic(self, card='0'):
    self.ApplyAudioConfig('mute_right_dmic', card)

  def DisableDmic(self, card='0'):
    self.ApplyAudioConfig('disable_dmic', card)

  def EnableDmic2(self, card='0'):
    self.ApplyAudioConfig('enable_dmic2', card)

  def MuteLeftDmic2(self, card='0'):
    self.ApplyAudioConfig('mute_left_dmic2', card)

  def MuteRightDmic2(self, card='0'):
    self.ApplyAudioConfig('mute_right_dmic2', card)

  def DisableDmic2(self, card='0'):
    self.ApplyAudioConfig('disable_dmic2', card)

  def EnableMLBDmic(self, card='0'):
    self.ApplyAudioConfig('enable_mlb_dmic', card)

  def MuteLeftMLBDmic(self, card='0'):
    self.ApplyAudioConfig('mute_left_mlb_dmic', card)

  def MuteRightMLBDmic(self, card='0'):
    self.ApplyAudioConfig('mute_right_mlb_dmic', card)

  def DisableMLBDmic(self, card='0'):
    self.ApplyAudioConfig('disable_mlb_dmic', card)

  def EnableExtmic(self, card='0'):
    self.ApplyAudioConfig('enable_extmic', card)

  def MuteLeftExtmic(self, card='0'):
    self.ApplyAudioConfig('mute_left_extmic', card)

  def MuteRightExtmic(self, card='0'):
    self.ApplyAudioConfig('mute_right_extmic', card)

  def DisableExtmic(self, card='0'):
    self.ApplyAudioConfig('disable_extmic', card)

  def SetSpeakerVolume(self, volume=0, card='0'):
    if not isinstance(volume, int) or volume < 0:
      raise ValueError('Volume should be positive integer.')
    if card in self.audio_config:
      if 'set_speaker_volume' in self.audio_config[card]:
        for name in self.audio_config[card]['set_speaker_volume'].keys():
          if 'Volume' in name:
            self.audio_config[card]['set_speaker_volume'][name] = str(volume)
            self.SetMixerControls(
                self.audio_config[card]['set_speaker_volume'], card)
            break

  def SetHeadphoneVolume(self, volume=0, card='0'):
    if not isinstance(volume, int) or volume < 0:
      raise ValueError('Volume should be positive integer.')
    if card in self.audio_config:
      if 'set_headphone_volume' in self.audio_config[card]:
        for name in self.audio_config[card]['set_headphone_volume'].keys():
          if 'Volume' in name:
            self.audio_config[card]['set_headphone_volume'][name] = str(volume)
            self.SetMixerControls(
                self.audio_config[card]['set_headphone_volume'], card)
            break
