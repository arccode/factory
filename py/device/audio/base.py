# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is audio control utility base module """

import logging
import os
from multiprocessing import Process

import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.device import types
from cros.factory.utils import config_utils
from cros.factory.utils import type_utils


DEFAULT_YAML_CONFIG_PATH = '/usr/local/factory/py/test/audio.conf'
DEFAULT_JSON_CONFIG_NAME = 'audio'

# Strings for key in audio.conf
HP_JACK_NAME = 'headphone_jack'
MIC_JACK_NAME = 'mic_jack'
HP_JACK_DETECT = 'headphone_jack_detect'
MIC_JACK_DETECT = 'mic_jack_detect'
MIC_JACK_TYPE_DETECT = 'mic_jack_type_detect'

DEFAULT_HEADPHONE_JACK_NAMES = ['Headphone Jack', 'Headset Jack']
# The input device event may be on Headphone Jack
DEFAULT_MIC_JACK_NAMES = ['Mic Jack'] + DEFAULT_HEADPHONE_JACK_NAMES

InputDevices = type_utils.Enum(['Dmic', 'Dmic2', 'MLBDmic', 'Extmic'])
OutputDevices = type_utils.Enum(['Speaker', 'Headphone'])
AudioDeviceType = type_utils.Enum(
    list(InputDevices) + list(OutputDevices))

MicJackType = type_utils.Enum(['none', 'lrgm', 'lrmg'])
# Used for external command return value
MIC_JACK_TYPE_RETURN_LRGM = '1'
MIC_JACK_TYPE_RETURN_LRMG = '2'

# Virtual Card Index for script.
script_card_index = '999'

# The bytes of the WAV header
WAV_HEADER_SIZE = 44


class BaseAudioControl(types.DeviceComponent):
  """An abstract class for different target audio utils"""

  def __init__(self, dut, config_path=None):
    super(BaseAudioControl, self).__init__(dut)
    # used for audio config logging.
    self._playback_process = None
    self._audio_config_sn = 0
    self._restore_mixer_control_stack = []
    self.audio_config = None
    self.ApplyConfig(config_path)

  def _GetPIDByName(self, name):
    """Used to get process ID"""
    pids = self._device.CallOutput(['toybox', 'pidof', name]).strip().split()
    # we sholud only have one PID.
    if len(pids) > 1:
      raise RuntimeError('Find more than one PID(%r) of %s!' % (pids, name))
    return pids[0] if pids else None

  def ApplyConfig(self, config_path):
    """Loads system config for audio cards.

    The config may come from JSON config (config_utils) or legacy YAML files.
    If config_path is a string that ends with ".conf", it will be evaluated as
    YAML; otherwise it will be used as the config name for config_utils.

    Args:
      config_path: A string for YAML config file path or JSON config name.
    """

    if config_path is None:
      # Use YAML file if that exists.
      config_path = DEFAULT_YAML_CONFIG_PATH
      if not os.path.exists(config_path):
        config_path = DEFAULT_JSON_CONFIG_NAME

    if config_path.endswith('.conf'):
      with open(config_path, 'r') as config_file:
        config = yaml.load(config_file)
    else:
      config = config_utils.LoadConfig(config_path)

    # Convert names to indexes.
    card_names = [name for name in config if not name.isdigit()]
    for name in card_names:
      index = self.GetCardIndexByName(name)
      config[index] = config[name]

    if not config:
      logging.info('audio: No configuration file (%s).', config_path)
    self.audio_config = config

  def GetCardIndexByName(self, card_name):
    """Get audio card index by card name. If the card_name is already an index,
    the function will just return it.

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
    # Merge all restore command sets to one set
    final_settings = {}
    while self._restore_mixer_control_stack:
      mixer_settings, card = self._restore_mixer_control_stack.pop()
      if card in final_settings:
        final_settings[card].update(mixer_settings)
      else:
        final_settings[card] = mixer_settings
    self._restore_mixer_control_stack = []
    for card, mixer_settings in final_settings.items():
      self.SetMixerControls(mixer_settings, card, False)

  def FindEventDeviceByName(self, name):
    """Finds the event device by matching name.

    Args:
      name: The name to look up event device by substring matching.

    Returns:
      The full name of the found event device of form /dev/input/event*
    """
    for evdev in self._device.Glob('/dev/input/event*'):
      evdev_name = self._device.ReadFile(
          self._device.path.join(
              '/sys/class/input/', self._device.path.basename(evdev),
              'device/name'))
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
      jack_status = self._device.CallOutput(command).strip()
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
        returncode = self._device.Call(command)
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
      jack_status = self._device.CallOutput(command).strip()
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
        returncode = self._device.Call(command)
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
      type_status = self._device.CallOutput(command).strip()
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

  def ApplyAudioConfig(self, action, card='0', is_script=False):
    """Apply audio configuration to dut.

    Args:
      action: action key in audio configuration file
      card: The index of audio card.
        If is_script=True The card argument is not used.
      is_script: True for shell script. False for mixer controls

    Returns:
      True for applying to dut. False for not.
    """
    if is_script:
      card = script_card_index

    if card in self.audio_config:
      if action in self.audio_config[card]:
        if is_script:
          script = self.audio_config[card][action]
          logging.info('Execute \'%s\'', script)
          self._device.CheckCall(script)
        else:
          logging.info('\nvvv-- Do(%d) \'%s\' on card %s Start --vvv',
                       self._audio_config_sn, action, card)
          self.SetMixerControls(self.audio_config[card][action], card)
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

  def InitialSetting(self, card='0'):
    self.ApplyAudioConfig('initial', card)

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
    """
    self.ApplyAudioConfig("enable_" + self._GetConfigPostfix(device), card)

  def MuteLeftDevice(self, device, card='0'):
    """Mute left the specified audio device.

    Args:
      device: Audio device to control. Should be of type AudioDeviceType.
    """
    self.ApplyAudioConfig("mute_left_" + self._GetConfigPostfix(device), card)

  def MuteRightDevice(self, device, card='0'):
    """Mute left the specified audio device.

    Args:
      device: Audio device to control. Should be of type AudioDeviceType.
    """
    self.ApplyAudioConfig("mute_right_" + self._GetConfigPostfix(device), card)

  def DisableDevice(self, device, card='0'):
    """Mute left the specified audio device.

    Args:
      device: Audio device to control. Should be of type AudioDeviceType.
    """
    self.ApplyAudioConfig("disable_" + self._GetConfigPostfix(device), card)

  def EnableSpeaker(self, card='0'):
    self.EnableDevice(AudioDeviceType.Speaker, card)

  def MuteLeftSpeaker(self, card='0'):
    self.MuteLeftDevice(AudioDeviceType.Speaker, card)

  def MuteRightSpeaker(self, card='0'):
    self.MuteRightDevice(AudioDeviceType.Speaker, card)

  def DisableSpeaker(self, card='0'):
    self.DisableDevice(AudioDeviceType.Speaker, card)

  def EnableHeadphone(self, card='0'):
    self.EnableDevice(AudioDeviceType.Headphone, card)

  def MuteLeftHeadphone(self, card='0'):
    self.MuteLeftDevice(AudioDeviceType.Headphone, card)

  def MuteRightHeadphone(self, card='0'):
    self.MuteRightDevice(AudioDeviceType.Headphone, card)

  def DisableHeadphone(self, card='0'):
    self.DisableDevice(AudioDeviceType.Headphone, card)

  def EnableDmic(self, card='0'):
    self.EnableDevice(AudioDeviceType.Dmic, card)

  def MuteLeftDmic(self, card='0'):
    self.MuteLeftDevice(AudioDeviceType.Dmic, card)

  def MuteRightDmic(self, card='0'):
    self.MuteRightDevice(AudioDeviceType.Dmic, card)

  def DisableDmic(self, card='0'):
    self.DisableDevice(AudioDeviceType.Dmic, card)

  def EnableDmic2(self, card='0'):
    self.EnableDevice(AudioDeviceType.Dmic2, card)

  def MuteLeftDmic2(self, card='0'):
    self.MuteLeftDevice(AudioDeviceType.Dmic2, card)

  def MuteRightDmic2(self, card='0'):
    self.MuteRightDevice(AudioDeviceType.Dmic2, card)

  def DisableDmic2(self, card='0'):
    self.DisableDevice(AudioDeviceType.Dmic2, card)

  def EnableMLBDmic(self, card='0'):
    self.EnableDevice(AudioDeviceType.MLBDmic, card)

  def MuteLeftMLBDmic(self, card='0'):
    self.MuteLeftDevice(AudioDeviceType.MLBDmic, card)

  def MuteRightMLBDmic(self, card='0'):
    self.MuteRightDevice(AudioDeviceType.MLBDmic, card)

  def DisableMLBDmic(self, card='0'):
    self.DisableDevice(AudioDeviceType.MLBDmic, card)

  def EnableExtmic(self, card='0'):
    self.EnableDevice(AudioDeviceType.Extmic, card)

  def MuteLeftExtmic(self, card='0'):
    self.MuteLeftDevice(AudioDeviceType.Extmic, card)

  def MuteRightExtmic(self, card='0'):
    self.MuteRightDevice(AudioDeviceType.Extmic, card)

  def DisableExtmic(self, card='0'):
    self.DisableDevice(AudioDeviceType.Extmic, card)

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

  def DisableAllAudioInputs(self, card):
    """Disable all audio inputs"""
    for audio_dev in InputDevices:
      self.DisableDevice(audio_dev, card)

  def DisableAllAudioOutputs(self, card):
    """Disable all audio outputs"""
    for audio_dev in OutputDevices:
      self.DisableDevice(audio_dev, card)

  def _PlaybackWavFile(self, path, card, device):
    """Playback .wav file.
    The function is a protected method, user can't use it directly, user must
    use PlaybackWavFile.

    Args:
      path: The .wav file path for playback
      card: The index of audio card
      device: The index of the device
    """
    raise NotImplementedError

  def PlaybackWavFile(self, path, card, device, blocking=True):
    """Playback .wav file.

    Args:
      path: The .wav file path for playback
      card: The index of audio card
      device: The index of the device
      blocking: True if playback in the same thread.
                False for creating a dedicated playback thread. For False case,
                user need to call StopPlaybackWavFile
    """
    if blocking:
      self._PlaybackWavFile(path, card, device)
    else:
      self._playback_process = Process(target=lambda:
                                       self._PlaybackWavFile(path, card,
                                                             device))
      self._playback_process.start()

  def _StopPlaybackWavFile(self):
    """Stop Playback process if we have one in system
    The function is a protected method, user can't use it directly, user must
    use StopPlaybackWavFile.
    """
    raise NotImplementedError

  def StopPlaybackWavFile(self):
    """Stop Playback process if we have one in system"""
    self._StopPlaybackWavFile()
    if self._playback_process:
      self._playback_process.join()
      self._playback_process = None

  def RecordWavFile(self, path, card, device, duration, channels, rate):
    """Record audio to a .wav file.
    It's a blocking Call. User can get their record result after this function
    returns.
    We use 16 bits little-endian as default sample format.

    Args:
      path: The record result file.
      card: The index of audio card.
      device: The index of the device.
      duration: (seconds) Record duration.
      channels: number of channels
      rate: Sampling rate
    """
    raise NotImplementedError

  def RecordRawFile(self, path, card, device, duration, channels, rate):
    """Record audio to a raw format.
    Just like RecordWavFile but we remove wav header for the raw format.
    User can overwrite it with their fast implementation.

    Args:
      path: The record result file.
      card: The index of audio card.
      device: The index of the device.
      duration: (seconds) Record duration.
      channels: number of channels
      rate: Sampling rate
    """
    with self._device.temp.TempFile() as wav_path:
      self.RecordWavFile(wav_path, card, device, duration, channels, rate)
      self._device.CheckCall(
          ['dd', 'skip=%d' % WAV_HEADER_SIZE, 'if=%s' % wav_path, 'of=%s' %
           path, 'bs=1'])
