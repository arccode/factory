#!/usr/bin/python

# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is audio utility module to setup amixer related options."""

from __future__ import print_function

import logging
import re

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut.audio import base
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


class AlsaAudioControl(base.BaseAudioControl):
  """This class is used for setting audio related configuration.
  It reads audio.conf initially to decide how to enable/disable each
  component by amixer.
  """
  _RE_CARD_INDEX = re.compile(r'^card (\d+):.*?\[(.+?)\]')
  _RE_DEV_NAME = re.compile(r'.*?hw:([0-9]+),([0-9]+)')
  _CONTROL_RE_STR = r'numid=(\d+).*?name=\'%s\''
  # Just list all supported options. But we only use wav and raw types.
  RecordType = Enum(['voc', 'wav', 'raw', 'au'])

  def GetCardIndexByName(self, card_name):
    """See BaseAudioControl.GetCardIndexByName"""
    if card_name.isdigit():
      return card_name
    output = self._dut.CallOutput(['aplay', '-l'])
    for line in output.splitlines():
      m = self._RE_CARD_INDEX.match(line)
      if m is not None and m.group(2) == card_name:
        return m.group(1)
    raise ValueError('device name %s is incorrect' % card_name)

  def GetCardIndex(self, device):
    """Gets the card index from given device names.

    Args:
      device: ALSA device name
    """
    match = self._RE_DEV_NAME.match(device)
    if match:
      return match.group(1)
    else:
      raise ValueError('device name %s is incorrect' % device)

  def GetMixerControls(self, name, card='0'):
    """See BaseAudioControl.GetMixerControls"""
    list_controls = self._dut.CallOutput(
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

    lines = self._dut.CallOutput(
        ['amixer', '-c%d' % int(card), 'cget', 'numid=%d' % numid])
    logging.info('lines: %s', lines)
    m = re.search(r'^.*: values=(.*)$', lines, re.MULTILINE)
    if m:
      return m.group(1)
    else:
      logging.info('Unable to get value for mixer control \'%s\', numid=%d',
                   name, numid)
      return None

  def SetMixerControls(self, mixer_settings, card='0', store=True):
    """Sets all mixer controls listed in the mixer settings on card.

    Args:
      mixer_settings: A dict of mixer settings to set.
      card: The index of audio card
      store: Store the current value so it can be restored later using
        RestoreMixerControls.
    """
    logging.info('Setting mixer control values on card %s', card)
    restore_mixer_settings = dict()
    for name, value in mixer_settings.items():
      if store:
        old_value = self.GetMixerControls(name, card)
        restore_mixer_settings[name] = old_value
        logging.info('Saving \'%s\' with value %s on card %s',
                     name, old_value, card)
      logging.info('Setting \'%s\' to %s on card %s', name, value, card)
      command = ['amixer', '-c', card, 'cset', 'name=%r' % name, value]
      self._dut.CheckCall(command)
    if store:
      self._restore_mixer_control_stack.append((restore_mixer_settings, card))

  def _GetPIDByName(self, name):
    """Used to get process ID"""
    lines = self._dut.CallOutput(['ps', '-C', name])
    m = re.search(r'(\d+).*%s' % name, lines, re.MULTILINE)
    if m:
      pid = m.group(1)
      return pid
    else:
      return None

  def _PlaybackWavFile(self, path, card, device):
    """See BaseAudioControl._PlaybackWavFile"""
    self._dut.Call(['aplay', '-D', 'hw:%s,%s' % (card, device), path])

  def _StopPlaybackWavFile(self):
    """See BaseAudioControl._StopPlaybackWavFile"""
    pid = self._GetPIDByName('aplay')
    if pid:
      self._dut.Call(['kill', pid])

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
      An array of the arecord command used by self._dut.Call.
    """
    file_type = {self.RecordType.voc: 'voc',
                 self.RecordType.wav: 'wav',
                 self.RecordType.raw: 'raw',
                 self.RecordType.au: 'au',
                }[file_type]
    return ['arecord', '-D', 'hw:%s,%s' % (card, device), '-t', file_type,
            '-d', str(duration), '-r', str(rate), '-c', str(channels),
            '-f', 'S16_LE', path]

  def RecordWavFile(self, path, card, device, duration, channels, rate):
    """See BaseAudioControl.RecordWavFile"""

    self._dut.Call(self._GetRecordArgs(self.RecordType.wav, path, card, device,
                                       duration, channels, rate))

  def RecordRawFile(self, path, card, device, duration, channels, rate):
    """See BaseAudioControl.RecordRawFile"""
    self._dut.Call(self._GetRecordArgs(self.RecordType.raw, path, card, device,
                                       duration, channels, rate))
