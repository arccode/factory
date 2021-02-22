# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is audio utility module to setup amixer related options."""

import logging
import re

from cros.factory.device.audio import base
from cros.factory.device.audio import config_manager
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils

# Configuration file is put under overlay directory and it can be customized
# for each board.
# Configuration file is using YAML nested collections format.
#
# Structure of this configuration file:
# card_index:
#   action:
#     "amixer configuration name": "value"
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


class AlsaMixerController(base.BaseMixerController):
  """Mixer controller for alsa."""
  _CONTROL_RE_STR = r'numid=(\d+).*?name=\'%s\''
  _RE_CARD_INDEX = re.compile(r'^card (\d+):.*?\[(.+?)\]')

  def GetMixerControls(self, name, card='0'):
    """See BaseMixerController.GetMixerControls"""
    list_controls = self._device.CallOutput(
        ['amixer', '-c%d' % int(card), 'controls'])
    re_control = re.compile(self._CONTROL_RE_STR % name)
    numid = 0
    for ctl in list_controls.splitlines():
      m = re_control.match(ctl)
      if m:
        numid = int(m.group(1))
        break
    else:
      logging.info('Unable to find mixer control \'%s\'', name)
      return None

    lines = self._device.CallOutput(
        ['amixer', '-c%d' % int(card), 'cget', 'numid=%d' % numid])
    logging.debug('lines: %s', lines)
    m = re.search(r'^.*: values=(.*)$', lines, re.MULTILINE)
    if m:
      return m.group(1)
    logging.info('Unable to get value for mixer control \'%s\', numid=%d',
                 name, numid)
    return None

  def SetMixerControls(self, mixer_settings, card='0', store=True):
    """See BaseMixerController.SetMixerControls"""
    logging.debug('Setting mixer control values on card %s', card)
    restore_mixer_settings = dict()
    for name, value in mixer_settings.items():
      if store:
        old_value = self.GetMixerControls(name, card)
        restore_mixer_settings[name] = old_value
        logging.debug('Saving \'%s\' with value %s on card %s',
                      name, old_value, card)
      logging.debug('Setting \'%s\' to %s on card %s', name, value, card)
      command = ['amixer', '-c', card, 'cset', 'name=%r' % name, value]
      self._device.CheckCall(command)
    if store:
      self._restore_mixer_control_stack.append((restore_mixer_settings, card))

  def GetCardIndexByName(self, card_name):
    """See BaseMixerController.GetCardIndexByName"""
    if not isinstance(card_name, str):
      raise ValueError('card_name %r is not a str' % card_name)
    if card_name.isdigit():
      return card_name
    output = self._device.CallOutput(['aplay', '-l'])
    for line in output.splitlines():
      m = self._RE_CARD_INDEX.match(line)
      if m is not None and m.group(2) == card_name:
        return m.group(1)
    raise ValueError('device name %s is incorrect' % card_name)


class AlsaAudioControl(base.BaseAudioControl):
  """This class is used for setting audio related configuration.
  It reads ALSA UCM configs to control the hardware components.
  If an audio.conf exists, the operations defined in that config
  file will override the behavior.
  """
  # Just list all supported options. But we only use wav and raw types.
  RecordType = type_utils.Enum(['voc', 'wav', 'raw', 'au'])

  def __init__(self, dut, config_name=None, ucm_card_map=None,
               ucm_device_map=None, ucm_verb=None):
    mixer_controller = AlsaMixerController(dut)
    self.ucm_card_map = ucm_card_map
    self.ucm_device_map = ucm_device_map
    self.ucm_verb = ucm_verb
    super(AlsaAudioControl, self).__init__(dut, config_name, mixer_controller)

  def _CreateAudioConfigManager(self, config_name):
    try:
      # If a factory audio config is there, use it.
      config_mgr = config_manager.JSONAudioConfigManager(
          self.mixer_controller, config_name)
      # Ignore if the config is empty.
      if config_mgr.audio_config:
        return config_mgr
    except Exception:
      logging.exception('config %s is not valid', config_name)

    # Factory audio config does not exist. Use UCM config manager.
    return config_manager.UCMConfigManager(
        self._device,
        self.mixer_controller,
        self.ucm_card_map,
        self.ucm_device_map,
        self.ucm_verb)

  def _PlaybackWavFile(self, path, card, device):
    """See BaseAudioControl._PlaybackWavFile"""
    self._device.Call(
        ['aplay', '-t', 'wav', '-D', 'plughw:%s,%s' % (card, device), path])

  def _StopPlaybackWavFile(self):
    """See BaseAudioControl._StopPlaybackWavFile"""
    pid = self._GetPIDByName('aplay')
    if pid:
      self._device.Call(['kill', pid])

  def _GetSupportedRecordArgs(self, card, device, orig_channel, orig_rate):
    """Get the supported arguments for `arecord`.

    Use `alsa_conformance_test` to get supported arguments. For each argument,
    the original value is checked. It is returned if it is supported. Otherwise,
    the last element of the supported value is used.

    If the original value is used we may be able to avoid unnecessary
    conversion. If not, we should try to use the highest value as possible.

    For the format, currently, only S16_LE and S32_LE are supported.

    Args:
      card: The index of audio card.
      device: The index of the device.
      orig_channel: The original number of channels.
      orig_rate: The original sampling rate.

    Returns:
      (channel, data_format, rate) the supported arguments.

    Raises:
      RuntimeError if no supported arguments.
    """
    # Some formats may not be supported by sox. Only list the formats we used.
    SOX_SUPPORTED_FORMATS = ['S16_LE', 'S32_LE']

    output = self._device.CheckOutput([
        'alsa_conformance_test', '--dev_info_only', '-C', f'hw:{card},{device}'
    ])

    def GetElementFromList(arr, ele):
      """Try to return `ele` or return the last element of list."""
      if not arr:
        return None
      if ele in arr:
        return ele
      return arr[-1]

    channel = None
    data_format = None
    rate = None
    for line in output.splitlines():
      tokens = [x.strip() for x in line.split(':')]
      if tokens[0] == 'available channels':
        #  The values of channels are increased.
        channel = int(GetElementFromList(tokens[1].split(' '), orig_channel))
      if tokens[0] == 'available formats':
        alsa_formats = tokens[1].split(' ')
        for try_format in SOX_SUPPORTED_FORMATS:
          if try_format in alsa_formats:
            data_format = try_format
            break
      if tokens[0] == 'available rates':
        #  The values of rates are increased.
        rate = int(GetElementFromList(tokens[1].split(' '), orig_rate))
    if channel is None or data_format is None or rate is None:
      raise RuntimeError("Device doesn't support recording.")
    return channel, data_format, rate

  def _RecordFile(self, file_type, out_file, card, device, duration, channels,
                  rate):
    """Record and save data to file.

    The output is always encoding in signed 16 bits little-endian. The recorded
    data is convert to the required format after recording.

    Args:
      file_type: RecordType Enum value.
      path: The record result file.
      card: The index of audio card.
      device: The index of the device.
      duration: (seconds) Record duration.
      channels: number of channels
      rate: Sampling rate
    """
    raw_channel, raw_format, raw_rate = self._GetSupportedRecordArgs(
        card, device, channels, rate)
    with file_utils.UnopenedTemporaryFile() as temp_file:
      self._device.CheckCall([
          'arecord',
          f'-Dhw:{card},{device}',
          '-twav',
          f'-d{duration}',
          f'-r{raw_rate}',
          f'-c{raw_channel}',
          f'-f{raw_format}',
          temp_file,
      ])

      if channels <= raw_channel:
        # The first `channels` channels is reserve. Other channels are dropped.
        remix = [str(x + 1) for x in range(channels)]
        logging.warning(
            'Raw data has %d channels. The channels after channel %d are '
            'dropped.', raw_channel, channels)
      else:
        # The i-th channel match the `((i * raw_channel) / channels)` channels.
        remix = [str(x * raw_channel // channels + 1) for x in range(channels)]
        logging.warning(
            'Raw data has %d channels. The channels are copied to match %d '
            'channels.', raw_channel, channels)
      if raw_format != 'S16_LE':
        logging.warning('Format "%s" is converted to "S16_LE".', raw_format)
      if raw_rate != rate:
        logging.warning('Rate "%d" is converted to "%d".', raw_rate, rate)

      # Convert the data into 16 bits little-endian.
      self._device.CheckCall([
          'sox',
          '-twav',
          temp_file,
          f'-t{file_type}',
          f'-r{rate}',
          f'-c{channels}',
          '-b16',
          '-esigned',
          '-L',
          out_file,
          'remix',
      ] + remix)

  def RecordWavFile(self, path, card, device, duration, channels, rate):
    """See BaseAudioControl.RecordWavFile"""
    self._RecordFile(self.RecordType.wav, path, card, device, duration,
                     channels, rate)

  def RecordRawFile(self, path, card, device, duration, channels, rate):
    """See BaseAudioControl.RecordRawFile"""
    self._RecordFile(self.RecordType.raw, path, card, device, duration,
                     channels, rate)
