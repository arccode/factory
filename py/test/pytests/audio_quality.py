# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Audio Quality Test the use audio fixture.

Description
-----------
This test case is used to communicate with audio fixture and parse
the result of CLIO which is audio quality analysis software.
DUT will connect to 2 subnets, one is for factory server and the other is for
fixture.

This pytest starts a socket server listening on port 8888 (can be overriden by
argument ``network_setting``).  Third party fixture will connect to this port
and communicate with this pytest in a speical protocol.  See
``HandleConnection`` and ``setupLoopHandler`` for more details.

The test flow is controlled by the third party fixture, this pytest is command
driven, it does whatever third party fixture asks it to do.

Test Procedure
--------------
This test does not require operator interaction.

1. Connect DUT with fixture.
2. Press ``SPACE`` to start testing.
3. The test will judge PASS / FAIL result by itself.

Dependency
----------
No extra dependency.

Examples
--------
Here is an example, assuming your audio device is ``<audio_device>``::

  "AudioQuality": {
    "label": "AudioQuality",
    "pytest_name": "audio_quality",
    "args": {
      "initial_actions": [["<audio_device>", "initial"]],
      "input_dev": ["<audio_device>", "1"],
      "output_dev": ["<audio_device>", "0"],
      "wav_file": "/usr/local/factory/third_party/SPK48k.wav"
    }
  }

(Optional) Use pytest ``retrieve parameter`` to download parameters from factory
server.
"""

import binascii
import logging
import os
import re
import select
import socket
import tempfile
import threading
import zipfile

import yaml

from cros.factory.device import device_utils
from cros.factory.goofy import goofy
from cros.factory.test.env import paths
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import audio_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils

# Host test machine crossover connected to DUT, fix local ip and port for
# communication in between.
_HOST = ''
_PORT = 8888
_LOCAL_IP = '192.168.1.2'

# Setting
_CHECK_FIXTURE_COMPLETE_SECS = 1  # Seconds to check fixture test.
_REMOVE_ETHERNET_TIMEOUT_SECS = 30  # Timeout for inserting dongle.
_FIXTURE_PARAMETERS = ['audio/audio_md5', 'audio/audio.zip']

# Label strings.
_LABEL_SPACE_TO_START = _("Press 'Space' to start test")
_LABEL_CONNECTED = _('Connected')
_LABEL_WAITING = _('Waiting for command')
_LABEL_AUDIOLOOP = _('Audio looping')
_LABEL_SPEAKER_MUTE_OFF = _('Speaker on')
_LABEL_DMIC_ON = _('LCD Dmic on')
_LABEL_MLBDMIC_ON = _('MLB Dmic on')
_LABEL_PLAYTONE_LEFT = _('Playing tone to left channel')
_LABEL_PLAYTONE_RIGHT = _('Playing tone to right channel')
_LABEL_WAITING_IP = _('Waiting for IP address')
_LABEL_READY = _('Ready for connection')

# Regular expression to match external commands.
_LOOP_0_RE = re.compile('(?i)loop_0')
_LOOP_1_RE = re.compile('(?i)loop_1')
_LOOP_2_RE = re.compile('(?i)loop_2')
_LOOP_3_RE = re.compile('(?i)loop_3')
_LOOP_4_RE = re.compile('(?i)loop_4')
_LOOP_5_RE = re.compile('(?i)loop_5')
_XTALK_L_RE = re.compile('(?i)xtalk_l')
_XTALK_R_RE = re.compile('(?i)xtalk_r')
_MUTE_SPK_L_RE = re.compile('(?i)mute_spk_l')
_MUTE_SPK_R_RE = re.compile('(?i)mute_spk_r')
_MULTITONE_RE = re.compile('(?i)multitone')
_SEND_FILE_RE = re.compile('(?i)send_file')
_TEST_COMPLETE_RE = re.compile('(?i)test_complete')
_RESULT_PASS_RE = re.compile('(?i)result_pass')
_RESULT_FAIL_RE = re.compile('(?i)result_fail')
_VERSION_RE = re.compile('(?i)version')
_CONFIG_FILE_RE = re.compile('(?i)config_file')
_PLAYBACK_WAV_FILE_RE = re.compile('(?i)playback_wav_file')

LoopType = type_utils.Enum(['sox', 'looptest', 'tinyloop', 'hwloop'])

# To optimize execution time. If we have shell script to create loop and restore
# configuration, we just use it and don't need to do separate actions.
# Note: If we use script to setup audio loop, we need to prepare restore script
# too.
_RESTORE_SCRIPT = 'restore_script'
_DMIC_JACK_SCRIPT = 'dmic_jack_script'
_KDMIC_JACK_SCRIPT = 'kdmic_jack_script'
_JACK_SPEAKER_SCRIPT = 'jack_speaker_script'
_JACK_HP_SCRIPT = 'jack_hp_script'
_DMIC2_JACK_SCRIPT = 'dmic2_jack_script'


class AudioQualityTest(test_case.TestCase):
  ARGS = [
      Arg('initial_actions', list, 'List of [card, actions], and card '
          'can be card index number or card name', default=[]),
      Arg('input_dev', list,
          'Input ALSA device.  [card_name, sub_device].'
          'For example: ["audio_card", "0"].', default=['0', '0']),
      Arg('output_dev', list,
          'Output ALSA device.  [card_name, sub_device].'
          'For example: ["audio_card", "0"].', default=['0', '0']),
      Arg('loop_type', str, 'Audio loop type: sox, looptest, tinyloop, hwloop',
          default='sox'),
      Arg('use_multitone', bool, 'Use multitone', default=False),
      Arg('loop_buffer_count', int, 'Count of loop buffer', default=10),
      Arg('fixture_param', list, 'Fixture parameters',
          default=_FIXTURE_PARAMETERS),
      Arg('network_setting', dict, 'Network setting to define *local_ip*, '
          '*port*, *gateway_ip*', default={}),
      Arg('audio_conf', str, 'Audio config file path', default=None),
      Arg('wav_file', str, 'Wav file path for playback_wav_file command.',
          default=None),
      Arg('keep_raw_logs', bool, 'Whether to attach the log by Testlog.',
          default=True)
  ]

  def setUpAudioDevice(self):
    logging.info('audio conf %s', self.args.audio_conf)
    if self.args.audio_conf:
      self._dut.audio.LoadConfig(self.args.audio_conf)

    # Tansfer input and output device format
    self._in_card = self._dut.audio.GetCardIndexByName(self.args.input_dev[0])
    self._in_device = self.args.input_dev[1]
    self._out_card = self._dut.audio.GetCardIndexByName(self.args.output_dev[0])
    self._out_device = self.args.output_dev[1]

    # Backward compatible for non-porting case, which use ALSA device name.
    # only works on chromebook device.
    # TODO(mojahsu): Remove them later.
    self._alsa_input_device = 'hw:%s,%s' % (self._in_card, self._in_device)
    self._alsa_output_device = 'hw:%s,%s' % (self._out_card, self._out_device)

  def setUpLoopHandler(self):
    # Register commands to corresponding handlers.
    self._handlers = {}
    self._handlers[_SEND_FILE_RE] = self.HandleSendFile
    self._handlers[_RESULT_PASS_RE] = self.HandleResultPass
    self._handlers[_RESULT_FAIL_RE] = self.HandleResultFail
    self._handlers[_TEST_COMPLETE_RE] = self.HandleTestComplete
    self._handlers[_LOOP_0_RE] = self.HandleLoopDefault
    self._handlers[_LOOP_1_RE] = self.HandleLoopFromDmicToJack
    self._handlers[_LOOP_2_RE] = self.HandleLoopFromJackToSpeaker
    self._handlers[_LOOP_3_RE] = self.HandleLoopJack
    self._handlers[_LOOP_4_RE] = self.HandleLoopFromKeyboardDmicToJack
    self._handlers[_LOOP_5_RE] = self.HandleLoopFromDmic2ToJack
    self._handlers[_XTALK_L_RE] = self.HandleXtalkLeft
    self._handlers[_XTALK_R_RE] = self.HandleXtalkRight
    self._handlers[_MUTE_SPK_L_RE] = self.HandleMuteSpeakerLeft
    self._handlers[_MUTE_SPK_R_RE] = self.HandleMuteSpeakerRight
    self._handlers[_MULTITONE_RE] = self.HandleMultitone
    self._handlers[_VERSION_RE] = self.HandleVersion
    self._handlers[_CONFIG_FILE_RE] = self.HandleConfigFile
    self._handlers[_PLAYBACK_WAV_FILE_RE] = self.HandlePlaybackWavFile

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self.setUpAudioDevice()
    self.setUpLoopHandler()

    # Initialize frontend presentation
    self._eth = None
    self._test_complete = False
    self._test_passed = False
    self._loop_type = {
        'sox': LoopType.sox,
        'looptest': LoopType.looptest,
        'tinyloop': LoopType.tinyloop,
        'hwloop': LoopType.hwloop
    }[self.args.loop_type]

    self._use_multitone = self.args.use_multitone
    self._loop_buffer_count = self.args.loop_buffer_count
    self._parameters = self.args.fixture_param
    self._local_ip = self.args.network_setting.get('local_ip', _LOCAL_IP)
    self._port = self.args.network_setting.get('port', _PORT)

    self._listen_thread = None
    self._aplay_process = None
    self._tone_process = None
    self._loop_process = None
    self._caches_dir = os.path.join(goofy.CACHES_DIR, 'parameters')
    self._file_path = self.ui.GetStaticDirectoryPath()

    # /var/factory/tests/<TestID>-<UUID>/
    self._test_dir = os.path.join(
        paths.DATA_TESTS_DIR, session.GetCurrentTestPath())

    self.event_loop.AddEventHandler('mock_command', self.MockCommand)
    process_utils.Spawn(
        ['iptables', '-A', 'INPUT', '-p', 'tcp', '--dport', str(self._port),
         '-j', 'ACCEPT'], check_call=True)

  def tearDown(self):
    self._dut.audio.RestoreMixerControls()
    net_utils.UnsetAliasEthernetIp(0, self._eth)

  def SetMessage(self, message):
    self.ui.SetHTML(message, id='message')

  def _HandleCommands(self, conn, command_list):
    """Handle commands"""
    for command in command_list:
      if not command:
        continue
      attr_list = command.split('\x05')
      instruction = attr_list[0]
      conn.send(instruction + '\x05' + 'Active' + '\x04\x03')

      match_command = False
      for key in self._handlers:
        if key.match(instruction):
          match_command = True
          session.console.info('match command %s', instruction)
          self._handlers[key](conn, attr_list)
          break
      if not match_command:
        session.console.error('Command %s cannot find', instruction)
        conn.send(instruction + '\x05' + 'Active_End' + '\x05' +
                  'Fail' + '\x04\x03')

  def HandleConnection(self, conn):
    """Asynchronous handler for socket connection.

    Command Protocol:
      Command1[\x05]Data1[\x05]Data2[\x04][\x03]
    One line may contains many commands. and the last character must
    be Ascii code \x03.

    Use Ascii code \x05 to seperate command and data.
    Use Ascii code \x04 to present the end of command.
    Use Ascii code \x03 to present the end of list of command.

    When DUT received command, DUT should reply Active status immediately.
    Format is
      Command[\x05]Active[\x04][\x03]

    When DUT executed command, DUT should return result.
    Format is
      Command[\x05]Active_Status[\x05]Result[\x05]Result_String[\x05]
      Error_Code[\x04][\x03]
    Active_Status may be:
      Active_End: executed commmand successfully
      Active_Timeout: executed command timeout
    Result may be:
      Pass: result of command is pass
      Fail: result of command is fail
    Result_String and Error_Code could be any plaintext.
    If Result_String and Error_Code are empty, you can omit these.
    For Example: Command[\x05]Active_End[\x05]Pass[\x04][\x03]

    Args:
      conn: socket connection
    """
    next_commands = ''
    while True:
      commands = next_commands
      while True:
        buf = conn.recv(1024)
        commands += buf
        if not buf or '\x03' in commands:
          break

      commands, unused_sep, next_commands = commands.partition('\x03')
      if not commands:
        break

      command_list = commands[0:-1].split('\x04')
      self._HandleCommands(conn, command_list)

      if self._test_complete:
        session.console.info('Test completed')
        break
    session.console.info('Connection disconnect')
    return False

  def RestoreConfiguration(self):
    """Stops all the running process and restore the mute settings."""
    if self._aplay_process:
      process_utils.TerminateOrKillProcess(self._aplay_process)
      self._aplay_process = None

    if self._tone_process:
      process_utils.TerminateOrKillProcess(self._tone_process)
      self._tone_process = None

    if self._loop_process:
      process_utils.TerminateOrKillProcess(self._loop_process)
      self._loop_process = None
      logging.info('Stopped audio loop process')

    # Always destroy tinyloop process.
    # If user has disconnected the device before test ends, there may be
    # tinyloop process left and will cause problem when we try to re-run, so we
    # have to always kill existing processes before starting to test.
    #
    # The DestroyAudioLoop is also ok if there is no tinyloop process.
    if self._loop_type == LoopType.tinyloop:
      self._dut.audio.DestroyAudioLoop()

    if self._dut.audio.ApplyAudioConfig(_RESTORE_SCRIPT, 0, True):
      return
    self._dut.audio.RestoreMixerControls()
    for card, action in self.args.initial_actions:
      if not card.isdigit():
        card = self._dut.audio.GetCardIndexByName(card)
      self._dut.audio.ApplyAudioConfig(action, card)
    self._dut.audio.DisableAllAudioInputs(self._in_card)
    self._dut.audio.DisableAllAudioOutputs(self._out_card)

  def SendResponse(self, response, args):
    """Sends response to DUT for each command.

    Args:
      response: response string
      args: This parameter is omitted when we test from FA-utility.
          Otherwise, this parameter is passing from handle_connection
          args[0] is socket connection
          args[1] is attr_list of handle_connection
    """
    # because there will not have args from mock_command
    if not args or not args[0] or not args[1][0]:
      return
    conn = args[0]
    command = args[1][0]
    if response:
      conn.send(command + '\x05' + 'Active_End' + '\x05' +
                'Pass' + '\x05' + response + '\x04\x03')
    else:
      conn.send(command + '\x05' + 'Active_End' + '\x05' +
                'Pass' + '\x04\x03')
    logging.info('Respond %s OK', command)

  def HandleVersion(self, *args):
    """Returns the md5 checksum of configuration file."""
    file_path = os.path.join(self._caches_dir, self._parameters[0])
    try:
      with open(file_path, 'rb') as md5_file:
        rawstring = md5_file.read()
        self.SendResponse(rawstring.strip(), args)
    except IOError:
      session.console.error('No such file or directory: %s', file_path)
      self.SendResponse('NO_VERSION', args)

  def HandleConfigFile(self, *args):
    """Return the content of configuration file."""
    file_path = os.path.join(self._caches_dir, self._parameters[1])
    try:
      with open(file_path, 'rb') as config_file:
        rawstring = config_file.read()
        # The format of file content is 'file_name;file_size;file_content'.
        # The file size is real file size instead of the size after
        # b2a_hex. Using b2a_hex is to avoid the file content including
        # special character such as '\x03', '\x04', and '\x05'.
        rawdata = (os.path.basename(self._parameters[1]) + ';' +
                   str(len(rawstring)) + ';' +
                   binascii.b2a_hex(rawstring))

        self.SendResponse(rawdata, args)
    except IOError:
      session.console.error('No such file or directory: %s', file_path)
      self.SendResponse('NO_CONFIG;0;%s' % binascii.b2a_hex(b''), args)

  def DecompressZip(self, file_path, target_path):
    """Decompresses ZIP format file

    Args:
      file_path: the path of compressed file
      target_path: the path of extracted files

    Returns:
      True if file is a ZIP format file
    """
    if not zipfile.is_zipfile(file_path):
      return False
    with zipfile.ZipFile(file_path) as zf:
      zf.extractall(target_path)
    return True

  def HandleSendFile(self, *args):
    """This function is used to save test results from DUT.

    Supposes the file is a YAML format. Reads the file and uploads to event
    log.
    """
    attr_list = args[1]
    file_name = attr_list[1]
    size = int(attr_list[2])
    received_data = attr_list[3]

    logging.info('Received file %s with size %d', file_name, size)
    real_data = binascii.a2b_hex(received_data)

    write_path = os.path.join(self._test_dir, file_name)
    file_utils.TryMakeDirs(os.path.dirname(write_path))
    session.console.info('save file: %s', write_path)
    with open(write_path, 'wb') as f:
      f.write(real_data)

    if self.args.keep_raw_logs:
      testlog.AttachFile(
          path=write_path,
          name=file_name,
          mime_type='application/octet-stream')

    if self.DecompressZip(write_path, tempfile.gettempdir()):
      file_path = os.path.join(tempfile.gettempdir(), 'description.yaml')
      if self.args.keep_raw_logs:
        testlog.AttachFile(
            path=file_path,
            name='audio_quality_result.yaml',
            mime_type='text/plain')

    self.SendResponse(None, args)

  def HandleSendFile_CLIO(self, *args):
    """This function is used to save test results from DUT.

    This is a deprecated function because it is only for CLIO output.
    This function also uploads the parsed data to log.
    """
    attr_list = args[1]
    file_name = attr_list[1]
    size = int(attr_list[2])
    received_data = attr_list[3].replace('\x00', ' ')

    write_path = os.path.join(self._test_dir, file_name)
    file_utils.TryMakeDirs(os.path.dirname(write_path))
    session.console.info('save file: %s', write_path)
    with open(write_path, 'wb') as f:
      f.write(received_data)

    if self.args.keep_raw_logs:
      testlog.AttachFile(
          path=write_path,
          name=file_name,
          mime_type='application/octet-stream')

    logging.info('Received file %s with size %d', file_name, size)

    # Dump another copy of logs
    logging.info(repr(received_data))

    # The result logs are stored in filename ending in _[0-9]+.txt.
    #
    # Its content looks like:
    # Freq [Hz]   dBV         Phase [Deg]
    # 100.00      -60.01      3.00
    # 105.93      -64.04      33.85
    # 112.20      -68.47      92.10
    # ...
    #
    # The column count is variable. There may be up to ten columns in the
    # results. Each column contains 12 characters. Because the spaces on
    # the right side of last colume are stripped. So the number of column
    # is the length of line divides by 12 and plus one.
    #
    # Unfortunately, we cannot read the column names in the header row
    # by splitting with spaces.

    match = re.search(r'(\d+)_(\d+)_(\d+).txt', file_name)
    match2 = re.search(r'(\d+)_(\d+).txt', file_name)

    if match:
      # serial_number and timestamp are generated by camerea test fixture.
      # We can use these two strings to lookup the raw logs on fixture.
      serial_number, timestamp, test_index = match.groups()

      lines = received_data.splitlines()
      header_row = lines[0]

      table = []
      # Record the maximum column_number, to add sufficient 'nan' to the end of
      # list if the spaces in the end of line are stripped.
      column_number = max([len(line) // 12 + 1 for line in lines[1:]])
      for line in lines[1:]:
        x = []
        for i in range(column_number):
          x.append(float(line[i * 12:i * 12 + 12].strip() or 'nan'))
        table.append(x)

      test_result = {}
      # Remarks:
      # 1. because the harmonic of some frequencies are not valid, we may
      #    have empty values in certain fields
      # 2. The missing fields are always in the last columns
      frequencies = {row[0]: row[1:] for row in table}
      test_result['frequencies'] = frequencies
      test_result['header_row'] = header_row
      test_result['serial_number'] = serial_number
      test_result['timestamp'] = timestamp
      test_result['test_index'] = test_index

      with file_utils.UnopenedTemporaryFile() as path:
        with open(path, 'w') as f:
          yaml.dump(test_result, f)
        testlog.AttachFile(
            path=path,
            name='audio_quality_test_%s' % test_index,
            mime_type='text/plain')
    elif match2:
      serial_number, timestamp = match2.groups()

      final_result = {}
      final_result['serial_number'] = serial_number
      final_result['timestamp'] = timestamp
      final_result['data'] = received_data.replace('\r', '')

      with file_utils.UnopenedTemporaryFile() as path:
        with open(path, 'w') as f:
          yaml.dump(final_result, f)
        testlog.AttachFile(
            path=path,
            name='audio_quality_final_result',
            mime_type='text/plain')
    else:
      logging.info('Unrecognizable filename %s', file_name)

    self.SendResponse(None, args)

  def HandleResultPass(self, *args):
    """Mark pass of this test case."""
    self._test_passed = True
    self.SendResponse(None, args)

  def HandleResultFail(self, *args):
    """Mark fail of this test case."""
    self._test_passed = False
    self.SendResponse(None, args)

  def HandleTestComplete(self, *args):
    """Handles test completion.
    Runs post test script before ends this test
    """
    self.SendResponse(None, args)
    self._test_complete = True

    # Restores the original state before exiting the test.
    process_utils.Spawn(
        ['iptables', '-D', 'INPUT', '-p', 'tcp', '--dport', str(self._port),
         '-j', 'ACCEPT'], check_call=True)
    self.RestoreConfiguration()

    logging.info('%s run_once finished', self.__class__)

  def HandleLoopDefault(self, *args):
    """Restore amixer configuration to default."""
    self.RestoreConfiguration()
    self.SetMessage(_LABEL_WAITING)
    self.SendResponse(None, args)

  def HandleLoop(self):
    """Starts the internal audio loopback."""
    self.SetMessage(_LABEL_AUDIOLOOP)

    if self._loop_type == LoopType.sox:
      cmdargs = [audio_utils.SOX_PATH, '-t', 'alsa',
                 self._alsa_input_device, '-t',
                 'alsa', self._alsa_output_device]
      self._loop_process = process_utils.Spawn(cmdargs)
    elif self._loop_type == LoopType.looptest:
      cmdargs = [audio_utils.AUDIOLOOP_PATH, '-i', self._alsa_input_device,
                 '-o', self._alsa_output_device, '-c',
                 str(self._loop_buffer_count)]
      self._loop_process = process_utils.Spawn(cmdargs)
    elif self._loop_type == LoopType.tinyloop:
      self._dut.audio.CreateAudioLoop(self._in_card, self._in_device,
                                      self._out_card, self._out_device)
    elif self._loop_type == LoopType.hwloop:
      pass

  def HandleMultitone(self, *args):
    """Plays the multi-tone sound file."""
    sound_path = os.path.join(self._file_path, 'multi_tone_10s.ogg')
    self.PlayWav(sound_path)
    self.SendResponse(None, args)

  def PlayWav(self, wav_path):
    """Play wav file by aplay command, require cras service enabled."""
    cmdargs = ['aplay', wav_path]
    self._aplay_process = process_utils.Spawn(cmdargs)

  def HandleLoopJack(self, *args):
    """External mic loop to headphone."""
    session.console.info('Audio Loop Mic Jack->Headphone')
    self.RestoreConfiguration()
    if not self._dut.audio.ApplyAudioConfig(_JACK_HP_SCRIPT, 0, True):
      self._dut.audio.EnableExtmic(self._in_card)
      self._dut.audio.EnableHeadphone(self._out_card)
    if self._use_multitone:
      self.HandleMultitone()
    elif self.args.wav_file is not None:
      self.HandlePlaybackWavFile()
    else:
      self.HandleLoop()
    self.SetMessage(_LABEL_AUDIOLOOP)
    self.SendResponse(None, args)

  def HandleLoopFromDmicToJack(self, *args):
    """LCD mic loop to headphone."""
    session.console.info('Audio Loop DMIC->Headphone')
    self.RestoreConfiguration()
    self.SetMessage([_LABEL_AUDIOLOOP, _LABEL_DMIC_ON])
    if not self._dut.audio.ApplyAudioConfig(_DMIC_JACK_SCRIPT, 0, True):
      self._dut.audio.EnableHeadphone(self._out_card)
      self._dut.audio.EnableDmic(self._in_card)
    self.HandleLoop()
    self.SendResponse(None, args)

  def HandleLoopFromDmic2ToJack(self, *args):
    """LCD mic loop to headphone."""
    session.console.info('Audio Loop DMIC2->Headphone')
    self.RestoreConfiguration()
    self.SetMessage([_LABEL_AUDIOLOOP, _LABEL_DMIC_ON])
    if not self._dut.audio.ApplyAudioConfig(_DMIC2_JACK_SCRIPT, 0, True):
      self._dut.audio.EnableDmic2(self._in_card)
      self._dut.audio.EnableHeadphone(self._out_card)
    self.HandleLoop()
    self.SendResponse(None, args)

  def HandleLoopFromJackToSpeaker(self, *args):
    """External mic loop to speaker."""
    session.console.info('Audio Loop Mic Jack->Speaker')
    self.RestoreConfiguration()
    self.SetMessage([_LABEL_AUDIOLOOP, _LABEL_SPEAKER_MUTE_OFF])
    if not self._dut.audio.ApplyAudioConfig(_JACK_SPEAKER_SCRIPT, 0, True):
      self._dut.audio.EnableExtmic(self._in_card)
      self._dut.audio.EnableSpeaker(self._out_card)
    if self._use_multitone:
      self.HandleMultitone()
    elif self.args.wav_file is not None:
      self.HandlePlaybackWavFile()
    else:
      self.HandleLoop()
    self.SendResponse(None, args)

  def HandleLoopFromKeyboardDmicToJack(self, *args):
    """Keyboard mic loop to headphone."""
    session.console.info('Audio Loop MLB DMIC->Headphone')
    self.RestoreConfiguration()
    self.SetMessage([_LABEL_AUDIOLOOP, _LABEL_MLBDMIC_ON])
    if not self._dut.audio.ApplyAudioConfig(_KDMIC_JACK_SCRIPT, 0, True):
      self._dut.audio.EnableMLBDmic(self._in_card)
      self._dut.audio.EnableHeadphone(self._out_card)
    self.HandleLoop()
    self.SendResponse(None, args)

  def HandleXtalkLeft(self, *args):
    """Cross talk left."""
    self.RestoreConfiguration()
    self.SetMessage(_LABEL_PLAYTONE_LEFT)
    self._dut.audio.MuteLeftHeadphone(self._out_card)
    cmdargs = audio_utils.GetPlaySineArgs(1, self._alsa_output_device)
    self._tone_process = process_utils.Spawn(cmdargs)
    self.SendResponse(None, args)

  def HandleXtalkRight(self, *args):
    """Cross talk right."""
    self.RestoreConfiguration()
    self.SetMessage(_LABEL_PLAYTONE_RIGHT)
    self._dut.audio.MuteRightHeadphone(self._out_card)
    cmdargs = audio_utils.GetPlaySineArgs(0, self._alsa_output_device)
    self._tone_process = process_utils.Spawn(cmdargs)
    self.SendResponse(None, args)

  def HandleMuteSpeakerLeft(self, *args):
    """Mute Left Speaker."""
    session.console.info('Mute Speaker Left')
    self._dut.audio.MuteLeftSpeaker(self._out_card)
    self.SendResponse(None, args)

  def HandleMuteSpeakerRight(self, *args):
    """Mute Left Speaker."""
    session.console.info('Mute Speaker Right')
    self._dut.audio.MuteRightSpeaker(self._out_card)
    self.SendResponse(None, args)

  def HandlePlaybackWavFile(self, *args):
    """Play a specific wav file."""
    self.PlayWav(self.args.wav_file)
    self.SendResponse(None, args)

  def ListenForever(self, sock):
    """Thread function to handle socket.

    Args:
      sock: socket object.
    """
    fd = sock.fileno()
    while True:
      _rl, unused_wl, unused_xl = select.select([fd], [], [])
      if fd in _rl:
        conn = sock.accept()[0]
        self.HandleConnection(conn)
      if self._test_complete:
        break

  def MockCommand(self, event):
    """Receive test command from FA-utility.

    Args:
      event: event from UI.
    """
    logging.info('Get event %s', event)
    cmd = event.data.get('cmd', '')
    if cmd == 'reset':
      self.SetMessage(_LABEL_SPACE_TO_START)
    for key, handler in self._handlers.items():
      if key.match(cmd):
        handler()
        break

  def RunAudioServer(self):
    """Initializes server and starts listening for external commands."""
    # Setup alias IP, the subnet is the same as Fixture
    self._eth = net_utils.FindUsableEthDevice(True)
    net_utils.SetAliasEthernetIp(self._local_ip, 0, self._eth)

    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((_HOST, self._port))
    sock.listen(1)
    logging.info('Listening at port %d', self._port)

    self._listen_thread = threading.Thread(target=self.ListenForever,
                                           args=(sock,))
    self._listen_thread.start()
    self.SetMessage(_LABEL_READY)

    while True:
      if self._test_complete:
        break
      self.Sleep(_CHECK_FIXTURE_COMPLETE_SECS)

  def runTest(self):
    self.SetMessage(_LABEL_SPACE_TO_START)
    self.ui.WaitKeysOnce(test_ui.SPACE_KEY)
    self.ui.HideElement('msg-utility')
    self.ui.HideElement('fa-utility')

    self.RunAudioServer()

    if not self._test_passed:
      self.FailTask('Test fail, find more detail in log.')
