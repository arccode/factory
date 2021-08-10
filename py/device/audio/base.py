# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is audio control utility base module """

import abc
import logging

from cros.factory.device.audio import config_manager
from cros.factory.device import device_types
from cros.factory.utils import process_utils


# The bytes of the WAV header
WAV_HEADER_SIZE = 44


MicJackType = config_manager.MicJackType
InputDevices = config_manager.InputDevices
OutputDevices = config_manager.OutputDevices
AudioDeviceType = config_manager.AudioDeviceType

DEFAULT_HEADPHONE_JACK_NAMES = ['Headphone Jack', 'Headset Jack']
# The input device event may be on Headphone Jack
DEFAULT_MIC_JACK_NAMES = ['Mic Jack'] + DEFAULT_HEADPHONE_JACK_NAMES


class BaseMixerController(metaclass=abc.ABCMeta):
  def __init__(self, device):
    self._device = device
    self._restore_mixer_control_stack = []

  @abc.abstractmethod
  def GetMixerControls(self, name, card='0'):
    """Gets the value for mixer control.

    Args:
      name: The name of mixer control
      card: The index of audio card
    """
    raise NotImplementedError

  @abc.abstractmethod
  def SetMixerControls(self, mixer_settings, card='0', store=True):
    """Sets all mixer controls listed in the mixer settings on card.

    Args:
      mixer_settings: A dict of mixer settings to set.
      card: The index of audio card
      store: Store the current value so it can be restored later using
        RestoreMixerControls.

    Raises:
      Raise CalledProcessError if failed to apply mixer commands.
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


class BaseAudioControl(device_types.DeviceComponent):
  """An abstract class for different target audio utils"""

  def __init__(self, dut, config_name, mixer_controller):
    super(BaseAudioControl, self).__init__(dut)
    self._playback_thread = None
    self.mixer_controller = mixer_controller
    self.LoadConfig(config_name)

  def Initialize(self, *args, **kwargs):
    return self.config_mgr.Initialize(*args, **kwargs)

  def _CreateAudioConfigManager(self, config_name):
    return config_manager.JSONAudioConfigManager(
        self.mixer_controller, config_name)

  def LoadConfig(self, config_name):
    """Load and replace `self.config_mgr`

    In most of the case, you only need to override `_CreateAudioConfigManager`
    to overwrite logic to select config.

    Args:
      config_name: a string to find the config file, can be None to load default
        config.
    """
    self.config_mgr = self._CreateAudioConfigManager(config_name)
    if isinstance(self.config_mgr, config_manager.UCMConfigManager):
      self.ucm_config_mgr = self.config_mgr
    else:
      self.ucm_config_mgr = config_manager.UCMConfigManager(
          self._device, self.mixer_controller, self.ucm_card_map,
          self.ucm_device_map, self.ucm_verb)

  def GetCardIndexByName(self, card_name):
    """See BaseMixerController.GetCardIndexByName."""
    return self.mixer_controller.GetCardIndexByName(card_name)

  def GetHeadphoneJackStatus(self, card='0'):
    """Gets the plug/unplug status of headphone jack.

    Args:
      card: The index of audio card.

    Returns:
      True if headphone jack is plugged, False otherwise.
    """
    try:
      return self.config_mgr.GetHeadphoneJackStatus(card)
    except Exception:
      pass

    try:
      possible_names = self.config_mgr.GetHeadphoneJackPossibleNames(card)
    except Exception:
      possible_names = DEFAULT_HEADPHONE_JACK_NAMES

    status = self._QueryJackStatus(
        card, possible_names, 'EV_SW', 'SW_HEADPHONE_INSERT')

    logging.info('Getting headphone jack status %s', status)
    if status is None:
      raise ValueError('No method can get headphone jack status')

    return status

  def GetMicJackStatus(self, card='0'):
    """Gets the plug/unplug status of mic jack.

    Args:
      card: The index of audio card.

    Returns:
      True if mic jack is plugged, False otherwise.
    """
    try:
      return self.config_mgr.GetMicJackStatus(card)
    except Exception:
      pass

    try:
      possible_names = self.config_mgr.GetMicJackPossibleNames(card)
    except Exception:
      possible_names = DEFAULT_MIC_JACK_NAMES

    status = self._QueryJackStatus(
        card, possible_names, 'EV_SW', 'SW_MICROPHONE_INSERT')

    logging.info('Getting microphone jack status %s', status)
    if status is None:
      raise ValueError('No methods to get microphone jack status')

    return status

  def GetMicJackType(self, card='0'):
    return self.config_mgr.GetMicJackType(card)

  def ApplyAudioConfig(self, action, card='0', is_script=False):
    return self.config_mgr.ApplyAudioConfig(action, card, is_script)

  def RestoreMixerControls(self):
    return self.mixer_controller.RestoreMixerControls()

  def EnableDevice(self, device, card='0'):
    self.config_mgr.EnableDevice(device, card)

  def MuteLeftDevice(self, device, card='0'):
    self.config_mgr.MuteLeftDevice(device, card)

  def MuteRightDevice(self, device, card='0'):
    self.config_mgr.MuteRightDevice(device, card)

  def DisableDevice(self, device, card='0'):
    self.config_mgr.DisableDevice(device, card)

  def EnableSpeaker(self, card='0'):
    self.EnableDevice(config_manager.AudioDeviceType.Speaker, card)

  def MuteLeftSpeaker(self, card='0'):
    self.MuteLeftDevice(config_manager.AudioDeviceType.Speaker, card)

  def MuteRightSpeaker(self, card='0'):
    self.MuteRightDevice(config_manager.AudioDeviceType.Speaker, card)

  def DisableSpeaker(self, card='0'):
    self.DisableDevice(config_manager.AudioDeviceType.Speaker, card)

  def EnableHeadphone(self, card='0'):
    self.EnableDevice(config_manager.AudioDeviceType.Headphone, card)

  def MuteLeftHeadphone(self, card='0'):
    self.MuteLeftDevice(config_manager.AudioDeviceType.Headphone, card)

  def MuteRightHeadphone(self, card='0'):
    self.MuteRightDevice(config_manager.AudioDeviceType.Headphone, card)

  def DisableHeadphone(self, card='0'):
    self.DisableDevice(config_manager.AudioDeviceType.Headphone, card)

  def EnableDmic(self, card='0'):
    self.EnableDevice(config_manager.AudioDeviceType.Dmic, card)

  def MuteLeftDmic(self, card='0'):
    self.MuteLeftDevice(config_manager.AudioDeviceType.Dmic, card)

  def MuteRightDmic(self, card='0'):
    self.MuteRightDevice(config_manager.AudioDeviceType.Dmic, card)

  def DisableDmic(self, card='0'):
    self.DisableDevice(config_manager.AudioDeviceType.Dmic, card)

  def EnableDmic2(self, card='0'):
    self.EnableDevice(config_manager.AudioDeviceType.Dmic2, card)

  def MuteLeftDmic2(self, card='0'):
    self.MuteLeftDevice(config_manager.AudioDeviceType.Dmic2, card)

  def MuteRightDmic2(self, card='0'):
    self.MuteRightDevice(config_manager.AudioDeviceType.Dmic2, card)

  def DisableDmic2(self, card='0'):
    self.DisableDevice(config_manager.AudioDeviceType.Dmic2, card)

  def EnableMLBDmic(self, card='0'):
    self.EnableDevice(config_manager.AudioDeviceType.MLBDmic, card)

  def MuteLeftMLBDmic(self, card='0'):
    self.MuteLeftDevice(config_manager.AudioDeviceType.MLBDmic, card)

  def MuteRightMLBDmic(self, card='0'):
    self.MuteRightDevice(config_manager.AudioDeviceType.MLBDmic, card)

  def DisableMLBDmic(self, card='0'):
    self.DisableDevice(config_manager.AudioDeviceType.MLBDmic, card)

  def EnableExtmic(self, card='0'):
    self.EnableDevice(config_manager.AudioDeviceType.Extmic, card)

  def MuteLeftExtmic(self, card='0'):
    self.MuteLeftDevice(config_manager.AudioDeviceType.Extmic, card)

  def MuteRightExtmic(self, card='0'):
    self.MuteRightDevice(config_manager.AudioDeviceType.Extmic, card)

  def DisableExtmic(self, card='0'):
    self.DisableDevice(config_manager.AudioDeviceType.Extmic, card)

  def SetSpeakerVolume(self, volume=0, card='0'):
    self.config_mgr.SetSpeakerVolume(volume, card)

  def SetHeadphoneVolume(self, volume=0, card='0'):
    self.config_mgr.SetHeadphoneVolume(volume, card)

  def DisableAllAudioInputs(self, card):
    """Disable all audio inputs"""
    for audio_dev in config_manager.InputDevices:
      try:
        self.DisableDevice(audio_dev, card)
      except Exception:
        pass  # Not all types of input devices are present

  def DisableAllAudioOutputs(self, card):
    """Disable all audio outputs"""
    for audio_dev in config_manager.OutputDevices:
      try:
        self.DisableDevice(audio_dev, card)
      except Exception:
        pass  # Not all types of output devices are present

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
      self._playback_thread = process_utils.StartDaemonThread(
          target=lambda: self._PlaybackWavFile(path, card, device))

  def _StopPlaybackWavFile(self):
    """Stop Playback process if we have one in system
    The function is a protected method, user can't use it directly, user must
    use StopPlaybackWavFile.
    """
    raise NotImplementedError

  def StopPlaybackWavFile(self):
    """Stop Playback process if we have one in system"""
    self._StopPlaybackWavFile()
    if self._playback_thread:
      self._playback_thread.join()
      self._playback_thread = None

  def RecordWavFile(self, path, card, device, duration, channels, rate):
    """Record audio to a .wav file.

    It's a blocking Call. User can get their record result after this function
    returns.
    The sample format is signed 16 bits little-endian.

    Args:
      path: The record result file.
      card: The index of audio card.
      device: The index of the device.
      duration: (seconds) Record duration.
      channels: number of channels, auto detected if it is 0.
      rate: Sampling rate.
    """
    raise NotImplementedError

  def RecordRawFile(self, path, card, device, duration, channels, rate):
    """Record audio to a raw format.

    Just like RecordWavFile but we remove wav header for the raw format.
    User can overwrite it with their fast implementation.

    The sample format is signed 16 bits little-endian.

    Args:
      path: The record result file.
      card: The index of audio card.
      device: The index of the device.
      duration: (seconds) Record duration.
      channels: number of channels.
      rate: Sampling rate.
    """
    with self._device.temp.TempFile() as wav_path:
      self.RecordWavFile(wav_path, card, device, duration, channels, rate)
      self._device.CheckCall(
          ['dd', 'skip=%d' % WAV_HEADER_SIZE, 'if=%s' % wav_path, 'of=%s' %
           path, 'bs=1'])

  def _GetPIDByName(self, name):
    """Used to get process ID"""
    output = self._device.CallOutput(['toybox', 'pidof', name])
    pids = output.strip().split() if output else []
    # we sholud only have one PID.
    if len(pids) > 1:
      raise RuntimeError('Find more than one PID(%r) of %s!' % (pids, name))
    if not pids:
      logging.info('Find no PID of %s', name)
    return pids[0] if pids else None

  def _QueryJackStatus(self, card, possible_names, ev_type, ev_val):
    # Loops through possible names. Uses mixer control or evtest
    # to query jack status.
    for jack_name in possible_names:
      values = self.mixer_controller.GetMixerControls(jack_name, card)
      if values:
        return values == 'on'

      evdev = self._FindEventDeviceByName(jack_name)
      if evdev:
        command = ['evtest', '--query', evdev, ev_type, ev_val]
        returncode = self._device.Call(command)
        return returncode != 0

    return None

  def _FindEventDeviceByName(self, name):
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
