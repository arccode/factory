# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module to load audio-related configurations."""

import abc
import logging
import os

import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.utils import config_utils
from cros.factory.utils import type_utils


# Strings for key in audio.conf
HP_JACK_NAME = 'headphone_jack'
MIC_JACK_NAME = 'mic_jack'
HP_JACK_DETECT = 'headphone_jack_detect'
MIC_JACK_DETECT = 'mic_jack_detect'
MIC_JACK_TYPE_DETECT = 'mic_jack_type_detect'

# Virtual Card Index for script.
_SCRIPT_CARD_INDEX = '999'

DEFAULT_YAML_CONFIG_PATH = '/usr/local/factory/py/test/audio.conf'
DEFAULT_JSON_CONFIG_NAME = 'audio'

MicJackType = type_utils.Enum(['none', 'lrgm', 'lrmg'])
# Used for external command return value
MIC_JACK_TYPE_RETURN_LRGM = '1'
MIC_JACK_TYPE_RETURN_LRMG = '2'

DEFAULT_HEADPHONE_JACK_NAMES = ['Headphone Jack', 'Headset Jack']
# The input device event may be on Headphone Jack
DEFAULT_MIC_JACK_NAMES = ['Mic Jack'] + DEFAULT_HEADPHONE_JACK_NAMES

InputDevices = type_utils.Enum(['Dmic', 'Dmic2', 'MLBDmic', 'Extmic'])
OutputDevices = type_utils.Enum(['Speaker', 'Headphone'])
AudioDeviceType = type_utils.Enum(
    list(InputDevices) + list(OutputDevices))


class BaseConfigManager:
  __metaclass__ = abc.ABCMeta

  def __init__(self):
    pass

  @abc.abstractmethod
  def Initialize(self, card='0'):
    """Initialize card device.

    Args:
      card: The index of audio card.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def EnableDevice(self, device, card='0'):
    """Enable the specified audio device.

    Args:
      device: Audio device to control. Should be of type AudioDeviceType.
      card: The index of audio card.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def MuteLeftDevice(self, device, card='0'):
    """Mute left the specified audio device.

    Args:
      device: Audio device to control. Should be of type AudioDeviceType.
      card: The index of audio card.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def MuteRightDevice(self, device, card='0'):
    """Mute left the specified audio device.

    Args:
      device: Audio device to control. Should be of type AudioDeviceType.
      card: The index of audio card.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def DisableDevice(self, device, card='0'):
    """Mute left the specified audio device.

    Args:
      device: Audio device to control. Should be of type AudioDeviceType.
      card: The index of audio card.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def ApplyConfig(self, config_name):
    """Loads system config for audio cards.

    Args:
      config_name: The config name argument required by derived class.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def ApplyAudioConfig(self, action, card='0', is_script=False):
    """Apply audio configuration to dut.

    Args:
      action: action key in audio configuration file
      card: The index of audio card.
        If is_script=True The card argument is not used.
      is_script: True for shell script. False for mixer controls

    Returns:
      True if the operation is supported; False if not.

    Raises:
      Raise CalledProcessError if failed to apply config.
    """
    raise NotImplementedError

  @abc.abstractmethod
  def SetSpeakerVolume(self, volume=0, card='0'):
    raise NotImplementedError

  @abc.abstractmethod
  def SetHeadphoneVolume(self, volume=0, card='0'):
    raise NotImplementedError

  def GetHeadphoneJackStatus(self, card='0'):
    """Gets the plug/unplug status of headphone jack.

    Args:
      card: The index of audio card.

    Returns:
      True if headphone jack is plugged; False if unplugged;
    """
    raise NotImplementedError

  def GetHeadphoneJackPossibleNames(self, card='0'):
    try:
      return self._GetHeadphoneJackPossibleNames(card)
    except Exception:
      return DEFAULT_HEADPHONE_JACK_NAMES

  def _GetHeadphoneJackPossibleNames(self, card='0'):
    raise NotImplementedError

  def GetMicJackStatus(self, card='0'):
    """Gets the plug/unplug status of mic jack.

    Args:
      card: The index of audio card.

    Returns:
      True if headphone jack is plugged; False if unplugged;
    """
    raise NotImplementedError

  def GetMicJackPossibleNames(self, card='0'):
    try:
      return self._GetMicJackPossibleNames(card)
    except Exception:
      return DEFAULT_MIC_JACK_NAMES

  def GetMicJackType(self, card='0'):
    """Gets the mic jack type.

    Args:
      card: The index of audio card.

    Returns:
      MicJackType enum value to indicate the mic jack type.
    """
    raise NotImplementedError


class AudioConfigManager(BaseConfigManager):
  """Loads config files which are defined by our factory toolkit."""

  def __init__(self, mixer_controller, config_name=None):
    super(AudioConfigManager, self).__init__()
    self._audio_config_sn = 0 # used for audio config logging.
    self._mixer_controller = mixer_controller
    self.audio_config = None
    self.ApplyConfig(config_name)

  @abc.abstractmethod
  def ApplyConfig(self, config_path):
    """Loads system config for audio cards.

    The config may come from JSON config (config_utils) or legacy YAML files.
    If config_path is a string that ends with ".conf", it will be evaluated as
    YAML; otherwise it will be used as the config name for config_utils.

    Args:
      config_path: A string for YAML config file path or JSON config name.
    """
    raise NotImplementedError()

  def Initialize(self, card='0'):
    """Initialize sound card.

    Returns:
      A boolean value indicating if the operation succeeded or not.
    """
    return self.ApplyAudioConfig('initial', card)

  def _GetConfigPostfix(self, device):
    switcher = {
        AudioDeviceType.Speaker: "speaker",
        AudioDeviceType.Headphone: "headphone",
        AudioDeviceType.Dmic: "dmic",
        AudioDeviceType.Dmic2: "dmic2",
        AudioDeviceType.MLBDmic: "mlb_dmic",
        AudioDeviceType.Extmic: "extmic"}
    return switcher[device]

  def EnableDevice(self, device, card='0'):
    """Enable the specified audio device.

    Args:
      device: Audio device to control. Should be of type AudioDeviceType.

    Returns:
      A boolean value indicating if the operation succeeded or not.
    """
    return self.ApplyAudioConfig(
        "enable_" + self._GetConfigPostfix(device), card)

  def MuteLeftDevice(self, device, card='0'):
    """Mute left the specified audio device.

    Args:
      device: Audio device to control. Should be of type AudioDeviceType.

    Returns:
      A boolean value indicating if the operation succeeded or not.
    """
    return self.ApplyAudioConfig(
        "mute_left_" + self._GetConfigPostfix(device), card)

  def MuteRightDevice(self, device, card='0'):
    """Mute left the specified audio device.

    Args:
      device: Audio device to control. Should be of type AudioDeviceType.

    Returns:
      A boolean value indicating if the operation succeeded or not.
    """
    return self.ApplyAudioConfig(
        "mute_right_" + self._GetConfigPostfix(device), card)

  def DisableDevice(self, device, card='0'):
    """Mute left the specified audio device.

    Args:
      device: Audio device to control. Should be of type AudioDeviceType.

    Returns:
      A boolean value indicating if the operation succeeded or not.
    """
    return self.ApplyAudioConfig(
        "disable_" + self._GetConfigPostfix(device), card)

  def ApplyAudioConfig(self, action, card='0', is_script=False):
    """BaseConfigManager.ApplyAudioConfig."""
    if is_script:
      card = _SCRIPT_CARD_INDEX

    if card in self.audio_config:
      if action in self.audio_config[card]:
        if is_script:
          script = self.audio_config[card][action]
          logging.info('Execute \'%s\'', script)
          self._device.CheckCall(script)
        else:
          logging.info('\nvvv-- Do(%d) \'%s\' on card %s Start --vvv',
                       self._audio_config_sn, action, card)
          self._mixer_controller.SetMixerControls(
              self.audio_config[card][action], card)
          logging.info('\n^^^-- Do(%d) \'%s\' on card %s End   --^^^',
                       self._audio_config_sn, action, card)
          self._audio_config_sn += 1
        return True
      else:
        logging.info('Action %s cannot be found in card %s', action, card)
        return False
    else:
      logging.info('Card %s does not exist', card)
      return False

  def SetSpeakerVolume(self, volume=0, card='0'):
    if not isinstance(volume, int) or volume < 0:
      raise ValueError('Volume should be positive integer.')
    if card in self.audio_config:
      if 'set_speaker_volume' in self.audio_config[card]:
        for name in self.audio_config[card]['set_speaker_volume'].keys():
          if 'Volume' in name:
            self.audio_config[card]['set_speaker_volume'][name] = str(volume)
            self._mixer_controller.SetMixerControls(
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
            self._mixer_controller.SetMixerControls(
                self.audio_config[card]['set_headphone_volume'], card)
            break

  def GetHeadphoneJackStatus(self, card='0'):
    if card in self.audio_config and HP_JACK_DETECT in self.audio_config[card]:
      command = self.audio_config[card][HP_JACK_DETECT]
      logging.info('Getting headphone jack status by %s', command)
      jack_status = self._device.CallOutput(command).strip()
      status = True if jack_status == '1' else False
      logging.info('headphone jack status %s', status)
      return status
    raise NotImplementedError # cannot determined by config file

  def _GetHeadphoneJackPossibleNames(self, card='0'):
    if card in self.audio_config and HP_JACK_NAME in self.audio_config[card]:
      return [self.audio_config[card][HP_JACK_NAME]]
    raise NotImplementedError # cannot determined by config file

  def GetMicJackStatus(self, card='0'):
    if card in self.audio_config and MIC_JACK_DETECT in self.audio_config[card]:
      command = self.audio_config[card][MIC_JACK_DETECT]
      logging.info('Getting microphone jack status by %s', command)
      jack_status = self._device.CallOutput(command).strip()
      status = True if jack_status == '1' else False
      logging.info('microphone jack status %s', status)
      return status

  def _GetMicJackPossibleNames(self, card='0'):
    if card in self.audio_config and MIC_JACK_NAME in self.audio_config[card]:
      return [self.audio_config[card][MIC_JACK_NAME]]
    raise NotImplementedError # cannot determined by config file

  def GetMicJackType(self, card='0'):
    mictype = None
    if (card in self.audio_config and
        MIC_JACK_TYPE_DETECT in self.audio_config[card]):
      command = self.audio_config[card][MIC_JACK_TYPE_DETECT]
      logging.info('Getting mic jack type by %s', command)
      type_status = self._device.CallOutput(command).strip()
      if type_status == MIC_JACK_TYPE_RETURN_LRGM:
        mictype = MicJackType.lrgm
      elif type_status == MIC_JACK_TYPE_RETURN_LRMG:
        mictype = MicJackType.lrmg
      else:
        mictype = MicJackType.none

    if mictype is None:
      raise ValueError('No methods to get mic jack type')

    logging.info('Getting mic jack type %s', mictype)
    return mictype


class JSONAudioConfigManager(AudioConfigManager):
  """Load JSON audio configs."""

  def LoadConfig(self, config_path):
    config = config_utils.LoadConfig(config_path)

    # Convert names to indexes.
    card_names = [name for name in config if not name.isdigit()]
    for name in card_names:
      index = self._mixer_controller.GetCardIndexByName(name)
      config[index] = config[name]

    if not config:
      logging.info('audio: No configuration file (%s).', config_path)
    self.audio_config = config


class YAMLAudioConfigManager(AudioConfigManager):
  """Load YAML audio configs."""

  def LoadConfig(self, config_path):
    with open(config_path, 'r') as config_file:
      config = yaml.load(config_file)

    # Convert names to indexes.
    card_names = [name for name in config if not name.isdigit()]
    for name in card_names:
      index = self._mixer_controller.GetCardIndexByName(name)
      config[index] = config[name]

    if not config:
      logging.info('audio: No configuration file (%s).', config_path)
    self.audio_config = config


def CreateAudioConfigManager(mixer_controller, config_path):
  if config_path is None:
    # Use YAML file if that exists.
    config_path = DEFAULT_YAML_CONFIG_PATH
    if not os.path.exists(config_path):
      config_path = DEFAULT_JSON_CONFIG_NAME

  if config_path.endswith('.conf'):
    return YAMLAudioConfigManager(mixer_controller, config_path)
  else:
    return JSONAudioConfigManager(mixer_controller, config_path)
