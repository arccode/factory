# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module to load audio-related configurations."""

import abc
import logging
import re
import subprocess

from cros.factory.device import device_types
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

DEFAULT_JSON_CONFIG_NAME = 'audio'

MicJackType = type_utils.Enum(['none', 'lrgm', 'lrmg'])
PCMType = type_utils.Enum(['PlaybackPCM', 'CapturePCM'])
DEVICE_STATE = type_utils.Enum(['Enabled', 'Disabled', 'Initial'])
# Used for external command return value
MIC_JACK_TYPE_RETURN_LRGM = '1'
MIC_JACK_TYPE_RETURN_LRMG = '2'

InputDevices = type_utils.Enum(['Dmic', 'Dmic2', 'MLBDmic', 'Extmic'])
OutputDevices = type_utils.Enum(['Speaker', 'Headphone'])
AudioDeviceType = type_utils.Enum(
    list(InputDevices) + list(OutputDevices))

INPUT_SENSITIVITY_NAME = 'IntrinsicSensitivity'
DEFAULT_CAPTURE_VOLUME_DBFS = -600


class BaseConfigManager(metaclass=abc.ABCMeta):
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
  def LoadConfig(self, config_name):
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
    del card  # unused
    raise Exception("No customized method to detect jack.")

  def GetHeadphoneJackPossibleNames(self, card='0'):
    del card  # unused
    raise Exception("No customized jack names.")

  def GetMicJackStatus(self, card='0'):
    """Gets the plug/unplug status of mic jack.

    Args:
      card: The index of audio card.

    Returns:
      True if headphone jack is plugged; False if unplugged;
    """
    del card  # unused
    raise Exception("No customized method to detect jack.")

  def GetMicJackPossibleNames(self, card='0'):
    del card  # unused
    raise Exception("No customized jack names.")

  @abc.abstractmethod
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
    self._audio_config_sn = 0  # used for audio config logging.
    self._mixer_controller = mixer_controller
    self.audio_config = None
    self._device = None
    self.LoadConfig(config_name)

  @abc.abstractmethod
  def LoadConfig(self, config_name):
    """Loads system config for audio cards.

    Args:
      config_name: a JSON config name, or None to load default config.
    """
    raise NotImplementedError

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

    if card not in self.audio_config:
      logging.info('Card %s does not exist', card)
      return False

    if action not in self.audio_config[card]:
      logging.info('Action %s cannot be found in card %s', action, card)
      return False

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

  def SetSpeakerVolume(self, volume=0, card='0'):
    if not isinstance(volume, int) or volume < 0:
      raise ValueError('Volume should be positive integer.')
    if card in self.audio_config:
      if 'set_speaker_volume' in self.audio_config[card]:
        for name in list(self.audio_config[card]['set_speaker_volume']):
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
        for name in list(self.audio_config[card]['set_headphone_volume']):
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
      status = jack_status == '1'
      logging.info('headphone jack status %s', status)
      return status
    raise NotImplementedError  # cannot determined by config file

  def GetHeadphoneJackPossibleNames(self, card='0'):
    if card in self.audio_config and HP_JACK_NAME in self.audio_config[card]:
      return [self.audio_config[card][HP_JACK_NAME]]
    raise NotImplementedError  # cannot determined by config file

  def GetMicJackStatus(self, card='0'):
    if card in self.audio_config and MIC_JACK_DETECT in self.audio_config[card]:
      command = self.audio_config[card][MIC_JACK_DETECT]
      logging.info('Getting microphone jack status by %s', command)
      jack_status = self._device.CallOutput(command).strip()
      status = jack_status == '1'
      logging.info('microphone jack status %s', status)
      return status
    raise NotImplementedError  # cannot determined by config file

  def GetMicJackPossibleNames(self, card='0'):
    if card in self.audio_config and MIC_JACK_NAME in self.audio_config[card]:
      return [self.audio_config[card][MIC_JACK_NAME]]
    raise NotImplementedError  # cannot determined by config file

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

  def LoadConfig(self, config_name):
    if config_name is None:
      config_name = DEFAULT_JSON_CONFIG_NAME

    config = config_utils.LoadConfig(config_name, 'audio')

    if not config:
      raise Exception("No valid audio config exists.")

    # Convert names to indexes.
    card_names = [name for name in config if not name.isdigit()]
    for name in card_names:
      index = self._mixer_controller.GetCardIndexByName(name)
      config[index] = config[name]

    if not config:
      logging.info('audio: No configuration file (%s).', config_name)
    self.audio_config = config


class UCMConfigManager(BaseConfigManager):
  """A UCM config manager which deals with UCM configs."""
  _AlsaUCMPath = '/usr/share/alsa/ucm'
  _InvertedDeviceMap = {
      'Speaker': AudioDeviceType.Speaker,
      'Headphone': AudioDeviceType.Headphone,
      'Internal Mic': AudioDeviceType.Dmic,
      'Mic': AudioDeviceType.Extmic,
      'Front Mic': AudioDeviceType.Dmic,
      'Rear Mic': AudioDeviceType.Dmic2}
  _DefaultVerb = 'HiFi'
  _RE_CARD_NAME = re.compile(r'^card (\d+):.*?\[(.+?)\]')

  def __init__(self, device, mixer_controller,
               card_map=None, card_device_map=None, verb=None):
    """Construct from a UCM config.

    This helps to control sound cards via the UCM config files.
    The Alsa UCM config files are typically stored under the
    folder /usr/share/alsa/ucm/, and the binary 'alsaucm' is
    used to parse/apply UCM config files.

    A UCM config only supports operations like initialize-card,
    enable-speaker, disable-mic, etc. It does not support operations
    like 'mute', 'adjust volume', or other customized amixer commands.
    To support these operations, please prepare the audio config, and
    use JSONAudioConfigManager instead.

    If a customized UCM config should be used, the UCM config
    files should be placed under /usr/share/alsa/ucm beforehand.
    For example, if 'factory_test' is chosen to be the UCM config
    name, the config files should be placed at
    /usr/share/alsa/ucm/factory_test/factory_test.conf and
    /usr/share/alsa/ucm/factory_test/HiFi.conf. Then, pass
    'factory_test' to the argument 'card_map'.

    Args:
      device: The device interface.

      mixer_controller: The alsa mixer controller.

      card_map: A dict to map index to card name with UCM suffix.
        Key: index of the card. See /proc/asound/cards.
        Value: A string stands for the card name. This should be the
               folder name listed under /usr/share/alsa/ucm/
               One can also pass a card name, which will be mapped to '0'.
        Default: Use 'aplay -l' to guess the card name.
                 See _GetCardNameMap for more details.

      card_device_map: Specify the device name of cards.
        Key: An index of the card. See /proc/asound/cards.
        Value: A device_map described below.

      device_map: Specify the device name.
        Key: A string defined in AudioDeviceType (e.g., 'Speaker').
        Value: The corresponding device string for UCM. Take a look at the
               UCM config file (e.g., HiFi.conf), one can find all available
               devices after the prefix 'SectionDevice'.

      verb: The verb string for UCM (e.g., 'HiFi')
    """
    super(UCMConfigManager, self).__init__()

    self._device = device
    self._mixer_controller = mixer_controller

    self._card_map = self._PrepareCardNameMap(card_map)

    self._verb = verb
    if self._verb is None:
      self._verb = self._DefaultVerb

    self._card_device_map = card_device_map or {}
    for card, device_map in self._card_device_map.items():
      # Assert that card is defined in self._card_map.
      self._GetCardName(card)
      invalid_devices = set(device_map) - set(AudioDeviceType)
      if invalid_devices:
        raise KeyError(
            "Invalid device: '%r' in card '%s'" % (invalid_devices, card))

    for card in set(self._card_map) - set(self._card_device_map):
      # Get the device map from HiFi.conf.
      output = self._InvokeCardCommands(
          card, 'set _verb %s' % self._verb, 'list _devices')
      device_map = {}
      for match in re.finditer(r'^.*: (.*)$', output, re.MULTILINE):
        value = match.group(1).strip()
        key = self._InvertedDeviceMap.get(value)
        if key is not None:
          device_map[key] = value
      self._card_device_map[card] = device_map

    self._card_device_state = {
        card: dict.fromkeys(device_map, DEVICE_STATE.Initial)
        for card, device_map in self._card_device_map.items()}

  def _GetCardNameMap(self):
    """Get card name with UCM suffix from aplay and cros_config."""
    def _GetUCMConfigDir(card_name):
      # The new directory is named as "<card-name>.<ucm-suffix>".
      ucm_suffix = self._device.CallOutput(
          ['cros_config', '/audio/main', 'ucm-suffix'])
      if ucm_suffix:
        ucm_dir = '%s.%s' % (card_name, ucm_suffix)
        ucm_path = self._device.path.join(self._AlsaUCMPath, ucm_dir)
        if self._device.path.isdir(ucm_path):
          return ucm_dir

      # The legacy directory is named as "<card-name>".
      legacy_ucm_path = self._device.path.join(self._AlsaUCMPath, card_name)
      if self._device.path.isdir(legacy_ucm_path):
        return card_name
      return None

    output = self._device.CallOutput(['aplay', '-l'])
    card_map = {}
    for line in output.splitlines():
      m = self._RE_CARD_NAME.match(line)
      if m is not None:
        card = m.group(1)
        card_name = m.group(2)
        ucm_config_dir = _GetUCMConfigDir(card_name)
        # pylint: disable=dict-values-not-iterating
        if ucm_config_dir and ucm_config_dir not in card_map.values():
          card_map[card] = ucm_config_dir
    return card_map

  def _PrepareCardNameMap(self, card_map):
    if card_map is None:
      card_map = self._GetCardNameMap()

    if not isinstance(card_map, dict) or not card_map:
      raise Exception("No valid card name can be found.")

    return card_map

  def _GetCardName(self, card):
    """Get card name of the card index with UCM suffix."""
    try:
      return self._card_map[card]
    except KeyError:
      raise KeyError('%s is not in %r' % (card, self._card_map))

  def _GetDeviceName(self, card, device):
    """Get device name of the card index."""
    # Assert that card is defined in self._card_map.
    self._GetCardName(card)
    try:
      return self._card_device_map[card][device]
    except Exception:
      logging.error('You should specify the device mapping for %s',
                    device)
      raise

  def _InvokeAlsaUCM(self, *commands):
    """Execute an command via alsaucm.

    After entering alsaucm in interaction mode (option -i), one can do:

    List all UCM configs:
      > listcards

    Assume we are dealing with card 'kblrt5514rt5663max'

    List all verbs:
      > open kblrt5514rt5663max
      > list _verbs

    List all devices under a verb 'HiFi':
      > open kblrt5514rt5663max
      > set _verb HiFi
      > list _devices
    All devices under the verb will be listed. For example:
      0: Speaker
      1: Headphone
      2: Internal Mic
      3: Mic
      4: HDMI1
      5: HDMI2
      6: HDMI3

    Enable the device 'Speaker':
      > open kblrt5514rt5663max
      > set _verb HiFi
      > set _enadev Speaker

    Reset sound card to default state:
      > open kblrt5514rt5663max
      > reset

    Get playback PCM for device 'Speaker':
      > open kblrt5514rt5663max
      > set _verb HiFi
      > get PlaybackPCM/Speaker
    Output looks like: PlaybackPCM/Speaker=hw:kblrt5514rt5663,0

    Get capture PCM for device 'Mic':
      > open kblrt5514rt5663max
      > set _verb HiFi
      > get CapturePCM/Mic
    Output looks like: CapturePCM/Mic=hw:kblrt5514rt5663,1

    Jack name of device 'Mic' can also be fetched:
      > open kblrt5514rt5663max
      > set _verb HiFi
      > get JackName/Mic
    Output looks like: JackName/Mic=kblrt5514rt5663max Headset Jack

    And for its jack type:
      > open kblrt5514rt5663max
      > set _verb HiFi
      > get JackType/Mic
    Output looks like: JackType/Mic=gpio

    The playback/capture PCM should be of form:
      hw:card-name,<num>
    The <num> is the device index, which can be used for aplay/arecord.

    Also refer to third_party/adhd/cras/src/server/cras_alsa_ucm.c for usages.
    The interface 'ucm_get_sections' demonstrates how UCM configs are used.
    """
    process = self._device.Popen(
        ['alsaucm', '-n', '-b', '-'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    out_msg, err_msg = process.communicate('\n'.join(commands))

    process.wait()
    rc = process.returncode

    if rc != 0:
      logging.error(
          'Failed to run alsaucm. Commands: [%s] Output: [%s] Error: [%s]',
          commands, out_msg, err_msg)
      raise device_types.CalledProcessError(
          returncode=rc, cmd=str(commands), output=str(out_msg))
    return out_msg

  def _InvokeCardCommands(self, card, *commands):
    return self._InvokeAlsaUCM('open "%s"' % self._GetCardName(card), *commands)

  def _InvokeDeviceCommands(self, card, *suffix_commands):
    commands = ['reset', 'set _verb %s' % self._verb]
    # 'set _verb' resets devices state to initial state for some sound card but
    # we can not 'set _enadev' without 'set _verb' first. So we just reset all
    # devices here.
    for device, state in self._card_device_state[card].items():
      if state == DEVICE_STATE.Initial:
        continue
      device_name = self._GetDeviceName(card, device)
      # The ucm config expects enable before disable so we always enable it
      # after reset. The quotes are used to pass device name with space, such as
      # "Internal Mic".
      commands.append('set _enadev "%s"' % device_name)
      if state == DEVICE_STATE.Disabled:
        commands.append('set _disdev "%s"' % device_name)
    return self._InvokeCardCommands(card, *commands, *suffix_commands)

  def Initialize(self, card='0'):
    """Initialize the sound card."""
    # Assert that card is defined in self._card_map.
    self._GetCardName(card)
    self._card_device_state[card] = dict.fromkeys(
        self._card_device_map[card], DEVICE_STATE.Initial)
    self._InvokeDeviceCommands(card)

  def EnableDevice(self, device, card='0'):
    """Enable a certain device on sound card."""
    # Assert that card is defined in self._card_map and device is defined in
    # device map.
    self._GetDeviceName(card, device)
    self._card_device_state[card][device] = DEVICE_STATE.Enabled
    self._InvokeDeviceCommands(card)

  def DisableDevice(self, device, card='0'):
    """Disable a certain device on sound card."""
    # device not present may be disable with DisableAllAudioInputs and
    # DisableAllAudioOutputs.
    # Assert that card is defined in self._card_map and device is defined in
    # device map.
    self._GetDeviceName(card, device)
    self._card_device_state[card][device] = DEVICE_STATE.Disabled
    self._InvokeDeviceCommands(card)

  def GetPCMId(self, category, device, card):
    """Return the card index and device index of a device."""
    if category not in PCMType:
      raise ValueError('category must in one of %r' % PCMType)
    card_name = self._GetCardName(card)
    device_name = self._GetDeviceName(card, device)
    identity = '%s/%s' % (category, device_name)
    output = self._InvokeDeviceCommands(card, 'get "%s"' % identity)
    match = re.search(r'^(.+)=hw:.+,(\d+)$', output, re.MULTILINE)
    if match and match.group(1).strip() == identity:
      return match.group(2)
    raise ValueError(
        'Wrong output format. output:%r card_name:%r' % (output, card_name))

  def GetChannelMap(self, device, card):
    """Return the channels of a input device.

    Args:
      device: One of InputDevices.
      card: The audio card index.
    Returns:
      A list of integer(s) represents the channels in use. None if it does not
      exist in the UCM config.
    Raises:
      ValueError if output format of alsaucm is wrong.
    """
    card_name = self._GetCardName(card)
    device_name = self._GetDeviceName(card, device)
    identity = 'CaptureChannelMap/%s' % device_name
    try:
      output = self._InvokeDeviceCommands(card, 'get "%s"' % identity)
    except device_types.CalledProcessError:
      return None
    match = re.search(r'^(.+)=(.+)$', output, re.MULTILINE)
    if match and match.group(1).strip() == identity:
      result = list(map(int, match.group(2).split()))
      while result and result[-1] == -1:
        result.pop()
      if result:
        return result
      raise ValueError(
          'There must be at least one channel. output:%r card_name:%r' %
          (output, card_name))
    raise ValueError(
        'Wrong output format. output:%r card_name:%r' % (output, card_name))

  def GetDefaultInputGain(self, card):
    """Return the default input gain of a device."""
    device_name = self._GetDeviceName(card, AudioDeviceType.Dmic)
    identity = '%s/%s' % (INPUT_SENSITIVITY_NAME, device_name)
    try:
      output = self._InvokeDeviceCommands(card, 'get "%s"' % identity)
      sensitivity = re.search(r'^(.+)=(.+)$', output, re.MULTILINE).group(2)
      input_gain = (DEFAULT_CAPTURE_VOLUME_DBFS - int(sensitivity)) / 100
      return input_gain
    except Exception:
      return 0

  def LoadConfig(self, config_name):
    raise Exception('UCM config does not support LaodConfig operation.')

  def ApplyAudioConfig(self, action, card='0', is_script=False):
    logging.info('UCM config cannot apply customized actions.')
    return False

  def MuteLeftDevice(self, device, card='0'):
    logging.info('UCM config does not support mute operations.')
    return False

  def MuteRightDevice(self, device, card='0'):
    logging.info('UCM config does not support mute operations.')
    return False

  def SetSpeakerVolume(self, volume=0, card='0'):
    logging.info('UCM config does not support SetSpeakerVolume operation.')
    return False

  def SetHeadphoneVolume(self, volume=0, card='0'):
    logging.info('UCM config does not support SetHeadphoneVolume operation.')
    return False

  def GetMicJackType(self, card='0'):
    raise Exception('UCM config does not support GetMicJackType operation.')
