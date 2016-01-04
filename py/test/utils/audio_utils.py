#!/usr/bin/python

# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is audio utility module to setup amixer related options."""

from __future__ import print_function

import dbus
import os
import re
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn, SpawnOutput

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

# Tools from platform/audiotest
AUDIOFUNTEST_PATH = 'audiofuntest'
AUDIOLOOP_PATH = 'looptest'
SOX_PATH = 'sox'
DEFAULT_NUM_CHANNELS = 2

_DEFAULT_SOX_FORMAT = '-t raw -b 16 -e signed -r 48000 -L'

# SOX related utilities


def GetPlaySineArgs(channel, odev='default', freq=1000, duration_secs=10,
                    sample_size=16):
  """Gets the command args to generate a sine wav to play to odev.

  Args:
    channel: 0 for left, 1 for right; otherwize, mono.
    odev: ALSA output device.
    freq: Frequency of the generated sine tone.
    duration_secs: Duration of the generated sine tone.
    sample_size: Output audio sample size. Default to 16.

  Returns:
    A command string to generate a sine wav
  """
  cmdargs = '%s -b %d -n -t alsa %s synth %d' % (
      SOX_PATH, sample_size, odev, duration_secs)
  if channel == 0:
    cmdargs += ' sine %d sine 0' % freq
  elif channel == 1:
    cmdargs += ' sine 0 sine %d' % freq
  else:
    cmdargs += ' sine %d' % freq
  return cmdargs


def GetGenerateSineWavArgs(path, channel, freq=1000, duration_secs=10,
                           sample_size=16):
  """Gets the command args to generate a sine .wav file.

  Args:
    path: The generated path of the sine .wav file.
    channel: 0 for left, 1 for right; otherwize, mono.
    freq: Frequency of the generated sine tone.
    duration_secs: Duration of the generated sine tone.
    sample_size: Output audio sample size. Default to 16.
  """
  cmdargs = '%s -b %d -n %s synth %d' % (
      SOX_PATH, sample_size, path, duration_secs)
  if channel == 0:
    cmdargs += ' sine %d sine 0' % freq
  elif channel == 1:
    cmdargs += ' sine 0 sine %d' % freq
  else:
    cmdargs += ' sine %d' % freq
  return cmdargs


def TrimAudioFile(in_path, out_path, start, end,
                  num_channel, sox_format=_DEFAULT_SOX_FORMAT):
  """Trims an audio file using sox command.

  Args:
    in_path: Path to the input audio file.
    out_path: Path to the output audio file.
    start: The starting time in seconds of specified range.
    end: The ending time in seconds of specified range.
         Sets to None for the end of audio file.
    num_channel: The number of channels in input file.
    sox_format: Format to generate sox command.
  """
  cmd = '%s -c %s %s %s -c %s %s %s trim %s' % (
      SOX_PATH, str(num_channel), sox_format, in_path,
      str(num_channel), sox_format, out_path, str(start))
  if end is not None:
    cmd += str(end)

  Spawn(cmd.split(' '), log=True, check_call=True)


# Functions to compose customized sox command, execute it and process the
# output of sox command.
def SoxMixerOutput(in_file, channel, sox_format=_DEFAULT_SOX_FORMAT):
  """Gets sox mixer command to reduce channel.

  Args:
    in_file: Input file name.
    channel: The selected channel to take effect.
    sox_format: A dict format to generate sox command.

  Returns:
    The output of sox mixer command
  """
  # The selected channel from input.(1 for the first channel).
  remix_channel = channel + 1

  command = (
      '%s -c 2 %s %s -c 1 %s - remix %s' %
      (SOX_PATH, sox_format, in_file, sox_format, str(remix_channel)))
  return Spawn(command.split(' '), log=True, read_stdout=True).stdout_data


def SoxStatOutput(in_file, channel, sox_format=_DEFAULT_SOX_FORMAT):
  """Executes sox stat command.

  Args:
    in_file: Input file name.
    channel: The selected channel.
    sox_format: Format to generate sox command.

  Returns:
    The output of sox stat command
  """
  sox_output = SoxMixerOutput(in_file, channel, sox_format)
  with tempfile.NamedTemporaryFile(delete=False) as temp_file:
    temp_file.write(sox_output)
  stat_cmd = '%s -c 1 %s %s -n stat' % (SOX_PATH, sox_format, temp_file.name)
  output = Spawn(stat_cmd.split(' '), read_stderr=True).stderr_data
  os.unlink(temp_file.name)
  return output


def GetAudioMinimumAmplitude(sox_output):
  """Gets the audio minimum amplitude from sox stat output

  Args:
    sox_output: Output of sox stat command.

  Returns:
    The minimum amplitude parsed from sox stat output.
  """
  m = re.search(r'^Minimum\s+amplitude:\s+(.+)$', sox_output, re.MULTILINE)
  if m is not None:
    return float(m.group(1))
  return None


def GetAudioMaximumAmplitude(sox_output):
  """Gets the audio maximum amplitude from sox stat output

  Args:
    sox_output: Output of sox stat command.

  Returns:
    The maximum amplitude parsed from sox stat output.
  """
  m = re.search(r'^Maximum\s+amplitude:\s+(.+)$', sox_output, re.MULTILINE)
  if m is not None:
    return float(m.group(1))
  return None


def GetAudioRms(sox_output):
  """Gets the audio RMS value from sox stat output

  Args:
    sox_output: Output of sox stat command.

  Returns:
    The RMS value parsed from sox stat output.
  """
  m = re.search(r'^RMS\s+amplitude:\s+(.+)$', sox_output, re.MULTILINE)
  if m is not None:
    return float(m.group(1))
  return None


def GetRoughFreq(sox_output):
  """Gets the rough audio frequency from sox stat output

  Args:
    sox_output: Output of sox stat command.

  Returns:
    The rough frequency value parsed from sox stat output.
  """
  _SOX_ROUGH_FREQ_RE = re.compile(r'Rough\s+frequency:\s+(.+)')
  for rms_line in sox_output.split('\n'):
    m = _SOX_ROUGH_FREQ_RE.match(rms_line)
    if m is not None:
      return int(m.group(1))
  return None


def NoiseReduceFile(in_file, noise_file, out_file,
                    sox_format=_DEFAULT_SOX_FORMAT):
  """Runs the sox command to noise-reduce in_file using
     the noise profile from noise_file.

  Args:
    in_file: The file to noise reduce.
    noise_file: The file containing the noise profile.
        This can be created by recording silence.
    out_file: The file contains the noise reduced sound.
    sox_format: The  sox format to generate sox command.
  """
  f = tempfile.NamedTemporaryFile(delete=False)
  f.close()
  prof_cmd = '%s -c 2 %s %s -n noiseprof %s' % (SOX_PATH,
                                                sox_format, noise_file, f.name)
  Spawn(prof_cmd.split(' '), check_call=True)

  reduce_cmd = ('%s -c 2 %s %s -c 2 %s %s noisered %s' %
                (SOX_PATH, sox_format, in_file, sox_format, out_file, f.name))
  Spawn(reduce_cmd.split(' '), check_call=True)
  os.unlink(f.name)


def GetCardIndexByName(card_name):
  """Get audio card index by card name.

  Args:
    card_name: Audio card name.

  Returns:
    Card index of the card name.

  Raises:
    ValueError when card name does not exist.
  """
  _RE_CARD_INDEX = re.compile(r'^card (\d+):.*?\[(.+?)\]')
  output = Spawn(['aplay', '-l'], read_stdout=True).stdout_data
  for line in output.split('\n'):
    m = _RE_CARD_INDEX.match(line)
    if m is not None and m.group(2) == card_name:
      return m.group(1)
  raise ValueError('device name %s is incorrect' % card_name)


def GetTotalNumberOfAudioDevices():
  """Get total number of audio devices.

  Returns:
    Total number of audio devices.
  """
  playback_num = int(SpawnOutput('aplay -l | grep ^card | wc -l', shell=True))
  record_num = int(SpawnOutput('arecord -l | grep ^card | wc -l', shell=True))
  return playback_num + record_num


class CRAS(object):
  """Class used to access CRAS information by
  executing commnad cras_test_clinet.
  """
  OUTPUT = 0
  INPUT = 1

  class Node(object):
    """Class to represent a input or output node in CRAS."""

    def __init__(self, node_id, plugged, name):
      self.node_id = node_id
      self.plugged = plugged
      self.name = name

    def __str__(self):
      return 'Cras node %s, id=%s, plugged=%s' % (self.name, self.node_id,
                                                  self.plugged)

  def __init__(self):
    self.CRAS_TEST_CLIENT = 'cras_test_client'
    self._RE_INPUT_NODES_SECTION = re.compile('Input Nodes:.*')
    self._RE_OUTPUT_NOTES_SECTION = re.compile('Output Nodes:.*')
    self._RE_END_SECTION = re.compile(r'^[A-Z].*')
    self._RE_IO_NODE_LINE = re.compile(r'\t(\d+:\d+).*')

    self.input_nodes = []
    self.output_nodes = []

  def DumpServerInfo(self):
    """Gets the server info of CRAS"""
    command = [self.CRAS_TEST_CLIENT, '--dump_server_info']
    return Spawn(command, read_stdout=True).stdout_data

  def UpdateIONodes(self):
    """Updates the input and output nodes of CRAS"""
    server_info = self.DumpServerInfo()
    node_section = 0
    self.input_nodes = []
    self.output_nodes = []

    for line in server_info.split('\n'):
      if self._RE_END_SECTION.match(line):
        node_section = 0
      if self._RE_INPUT_NODES_SECTION.match(line):
        node_section = 1
      if self._RE_OUTPUT_NOTES_SECTION.match(line):
        node_section = 2

      if self._RE_IO_NODE_LINE.match(line):
        # ID Prio Vol Plugged Time Type Name
        args = line.split()
        if node_section == 1:
          self.input_nodes.append(self.Node(args[0], args[3],
                                            ' '.join(args[5:])))
        elif node_section == 2:
          self.output_nodes.append(self.Node(args[0], args[3],
                                             ' '.join(args[5:])))

  def _SelectNode(self, node, direction):
    """Selects node.

    Args:
      node: The node to select to
      direction: Input or output of the node
    """
    command = [self.CRAS_TEST_CLIENT,
               '--select_input' if direction == CRAS.INPUT
               else '--select_output',
               node.node_id]
    Spawn(command, call=True)

  def SelectNodeById(self, node_id):
    """Selects node by given id.

    Args:
      node_id: The id of input/output node
    """
    for node in self.input_nodes:
      if node_id == node.node_id:
        self._SelectNode(node, CRAS.INPUT)
        return
    for node in self.output_nodes:
      if node_id == node.node_id:
        self._SelectNode(node, CRAS.OUTPUT)
        return

  def _GetControlInterface(self):
    """Returns an interface to control Cras using DBus API.

    Returns:
      A dbus.Interface object that can control Cras through DBus API.
    """
    bus = dbus.SystemBus()
    cras_object = bus.get_object('org.chromium.cras', '/org/chromium/cras')
    return dbus.Interface(cras_object, 'org.chromium.cras.Control')

  def EnableOutput(self):
    """Enables output by setting system mute and user mute states to False."""
    interface = self._GetControlInterface()
    interface.SetOutputMute(False)
    interface.SetOutputUserMute(False)

  def SetActiveOutputNodeVolume(self, volume):
    """Sets active output node volume.

    Args:
      volume: 0-100 for active output node volume.
    """
    interface = self._GetControlInterface()
    for node in interface.GetNodes():
      if not node['IsInput'] and node['Active']:
        interface.SetOutputNodeVolume(node['Id'], volume)
