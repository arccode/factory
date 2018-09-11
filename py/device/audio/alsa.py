# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is audio utility module to setup amixer related options."""

from __future__ import print_function

import logging
import re

import factory_common  # pylint: disable=unused-import
from cros.factory.device.audio import base
from cros.factory.device.audio import config_manager
from cros.factory.utils.type_utils import Enum

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
    else:
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
  RecordType = Enum(['voc', 'wav', 'raw', 'au'])

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
      return config_mgr
    except Exception:
      pass

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

  def _GetRecordArgs(self, file_type, path, card, device, duration, channels,
                     rate):
    """Gets the command args for arecord to record audio

    Args:
      file_type: RecordType Enum value.
      path: The record result file.
      card: The index of audio card.
      device: The index of the device.
      duration: (seconds) Record duration.
      channels: number of channels
      rate: Sampling rate

    Returns:
      An array of the arecord command used by self._device.Call.
    """
    file_type = {
        self.RecordType.voc: 'voc',
        self.RecordType.wav: 'wav',
        self.RecordType.raw: 'raw',
        self.RecordType.au: 'au',
    }[file_type]
    return ['arecord', '-D', 'hw:%s,%s' % (card, device), '-t', file_type,
            '-d', str(duration), '-r', str(rate), '-c', str(channels),
            '-f', 'S16_LE', path]

  def RecordWavFile(self, path, card, device, duration, channels, rate):
    """See BaseAudioControl.RecordWavFile"""

    self._device.Call(self._GetRecordArgs(
        self.RecordType.wav, path, card, device, duration, channels, rate))

  def RecordRawFile(self, path, card, device, duration, channels, rate):
    """See BaseAudioControl.RecordRawFile"""
    self._device.Call(self._GetRecordArgs(
        self.RecordType.raw, path, card, device, duration, channels, rate))
