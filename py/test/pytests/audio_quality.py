# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# DESCRIPTION :
#
# This test case is used to communicate with audio fixture and parse
# the result of CLIO which is audio quality analysis software.
# DUT will connect to 2 subnets, one is for shopfloor the other is for fixture.

from __future__ import print_function

import binascii
import logging
import os
import re
import select
import socket
import tempfile
import threading
import time
import unittest
import yaml
import zipfile

import factory_common  # pylint: disable=W0611
from cros.factory.device import device_utils
from cros.factory.goofy.goofy import CACHES_DIR
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test.env import paths
from cros.factory.test.event_log import Log
from cros.factory.test.utils import audio_utils
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.process_utils import Spawn, TerminateOrKillProcess
from cros.factory.utils.type_utils import Enum

# Host test machine crossover connected to DUT, fix local ip and port for
# communication in between.
_HOST = ''
_PORT = 8888
_LOCAL_IP = '192.168.1.2'

# Setting
_SHOPFLOOR_TIMEOUT_SECS = 10  # Timeout for shopfloor connection.
_SHOPFLOOR_RETRY_INTERVAL_SECS = 10  # Seconds to wait between retries.
_CHECK_FIXTURE_COMPLETE_SECS = 1  # Seconds to check fixture test.
_REMOVE_ETHERNET_TIMEOUT_SECS = 30  # Timeout for inserting dongle.
_FIXTURE_PARAMETERS = ['audio/audio_md5', 'audio/audio.zip']

# Label strings.
_LABEL_SPACE_TO_START = test_ui.MakeLabel(
    'Press \'Space\' to start test', u'按空白键开始测试')
_LABEL_CONNECTED = test_ui.MakeLabel('Connected', u'已连线')
_LABEL_WAITING = test_ui.MakeLabel('Waiting for command', u'等待指令中')
_LABEL_AUDIOLOOP = test_ui.MakeLabel('Audio looping', u'音源回放中')
_LABEL_SPEAKER_MUTE_OFF = test_ui.MakeLabel('Speaker on', u'喇叭开启')
_LABEL_DMIC_ON = test_ui.MakeLabel('LCD Dmic on', u'LCD mic开启')
_LABEL_MLBDMIC_ON = test_ui.MakeLabel('MLB Dmic on', u'MLB mic开启')
_LABEL_PLAYTONE_LEFT = test_ui.MakeLabel(
    'Playing tone to left channel', u'播音至左声道')
_LABEL_PLAYTONE_RIGHT = test_ui.MakeLabel(
    'Playing tone to right channel', u'播音至右声道')
_LABEL_WAITING_IP = test_ui.MakeLabel(
    'Waiting for IP address', u'等待 IP 设定')
_LABEL_CONNECT_SHOPFLOOR = test_ui.MakeLabel(
    'Connecting to ShopFloor...', u'连接到 ShopFloor 中...')
_LABEL_DOWNLOADING_PARAMETERS = test_ui.MakeLabel(
    'Downloading parameters', u'下载测试规格中')
_LABEL_REMOVE_ETHERNET = test_ui.MakeLabel(
    'Remove Ethernet connectivity', u'移除网路介面卡')
_LABEL_WAITING_ETHERNET = test_ui.MakeLabel(
    'Waiting for Ethernet connectivity to audio fixture',
    u'等待网路介面卡连接到 audio 置具')
_LABEL_READY = test_ui.MakeLabel(
    'Ready for connection', u'準备完成,等待链接')
_LABEL_UPLOAD_AUXLOG = test_ui.MakeLabel('Upload log', u'上传记录档')
_LABEL_FAIL_LOGS = 'Test fail, find more detail in log.'

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

LoopType = Enum(['sox', 'looptest', 'tinyloop', 'hwloop'])

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


class AudioQualityTest(unittest.TestCase):
  ARGS = [
      Arg('initial_actions', list, 'List of tuple (card, actions), and card '
          'can be card index number or card name', []),
      Arg('input_dev', tuple,
          'Input ALSA device.  (card_name, sub_device).'
          'For example: ("audio_card", "0").', ('0', '0')),
      Arg('output_dev', tuple,
          'Output ALSA device.  (card_name, sub_device).'
          'For example: ("audio_card", "0").', ('0', '0')),
      Arg('loop_type', str, 'Audio loop type: sox, looptest, tinyloop, hwloop',
          'sox'),
      Arg('use_multitone', bool, 'Use multitone', False, optional=True),
      Arg('loop_buffer_count', int, 'Count of loop buffer', 10,
          optional=True),
      Arg('fixture_param', list, 'Fixture parameters', _FIXTURE_PARAMETERS,
          optional=True),
      Arg('use_shopfloor', bool, 'Use shopfloor', True, optional=True),
      Arg('network_setting', dict, 'Network setting to define *local_ip*, \n'
          '*port*, *gateway_ip*', {}, optional=True),
      Arg('audio_conf', str, 'Audio config file path', None, optional=True),
  ]

  def setUpAudioDevice(self):
    logging.info('audio conf %s', self.args.audio_conf)
    if self.args.audio_conf:
      self._dut.audio.ApplyConfig(self.args.audio_conf)

    # Devices Type check
    if not isinstance(self.args.input_dev, tuple):
      raise ValueError('input_dev type is incorrect, need tuple')
    if not isinstance(self.args.output_dev, tuple):
      raise ValueError('output_dev type is incorrect, need tuple')

    # Tansfer input and output device format
    self._in_card = self._dut.audio.GetCardIndexByName(self.args.input_dev[0])
    self._in_device = self.args.input_dev[1]
    self._out_card = self._dut.audio.GetCardIndexByName(self.args.output_dev[0])
    self._out_device = self.args.output_dev[1]

    # Backward compitable for non-porting case, which use ALSA device name.
    # only works on chromebook device
    # TODO(mojahsu) Remove them later.
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

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self.setUpAudioDevice()
    self.setUpLoopHandler()

    # Initialize frontend presentation
    self._eth = None
    self._test_complete = False
    self._test_passed = False
    self._loop_type = {'sox': LoopType.sox,
                       'looptest': LoopType.looptest,
                       'tinyloop': LoopType.tinyloop,
                       'hwloop': LoopType.hwloop
                      }[self.args.loop_type]

    self._use_multitone = self.args.use_multitone
    self._loop_buffer_count = self.args.loop_buffer_count
    self._parameters = self.args.fixture_param
    self._use_shopfloor = self.args.use_shopfloor
    self._local_ip = self.args.network_setting.get('local_ip', _LOCAL_IP)
    self._port = self.args.network_setting.get('port', _PORT)

    self._listen_thread = None
    self._multitone_process = None
    self._tone_process = None
    self._loop_process = None
    self._caches_dir = os.path.join(CACHES_DIR, 'parameters')
    base = os.path.dirname(os.path.realpath(__file__))
    self._file_path = os.path.join(base, '..', '..', 'goofy', 'static',
                                   'sounds')
    self._auxlogs = []

    self._ui = test_ui.UI()
    self._ui.CallJSFunction('setMessage', _LABEL_SPACE_TO_START)
    self._ui.AddEventHandler('start_run', self.StartRun)
    self._ui.BindKeyJS(
        test_ui.SPACE_KEY,
        'test.sendTestEvent("start_run",{});' +
        'document.getElementById("msg-utility").style.display="none";',
        once=True)
    self._ui.AddEventHandler('mock_command', self.MockCommand)
    Spawn(['iptables', '-A', 'INPUT', '-p', 'tcp', '--dport', str(self._port),
           '-j', 'ACCEPT'], check_call=True)

  def runTest(self):
    self._ui.Run()

  def tearDown(self):
    self._dut.audio.RestoreMixerControls()
    net_utils.UnsetAliasEthernetIp(0, self._eth)

  def _HandleCommands(self, conn, command_list):
    """Handle commands"""
    for command in command_list:
      if not command:
        continue
      attr_list = command.split('\x05')
      instruction = attr_list[0]
      conn.send(instruction + '\x05' + 'Active' + '\x04\x03')

      match_command = False
      for key in self._handlers.iterkeys():
        if key.match(instruction):
          match_command = True
          factory.console.info('match command %s', instruction)
          self._handlers[key](conn, attr_list)
          break
      if not match_command:
        factory.console.error('Command %s cannot find', instruction)
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

      commands, next_commands = commands.split('\x03', 1)
      if not commands:
        break

      command_list = commands[0:-1].split('\x04')
      self._HandleCommands(conn, command_list)

      if self._test_complete:
        factory.console.info('Test completed')
        break
    factory.console.info('Connection disconnect')
    return False

  def RestoreConfiguration(self):
    """Stops all the running process and restore the mute settings."""
    if self._multitone_process:
      TerminateOrKillProcess(self._multitone_process)
      self._multitone_process = None

    if self._tone_process:
      TerminateOrKillProcess(self._tone_process)
      self._tone_process = None

    if self._loop_process:
      TerminateOrKillProcess(self._loop_process)
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
      if card.isdigit() is False:
        card = self._dut.audio.GetCardIndexByName(card)
      self._dut.audio.ApplyAudioConfig(action, card)
    self._dut.audio.DisableAllAudioInputs(self._in_card)
    self._dut.audio.DisableAllAudioOutputs(self._out_card)

  def SendResponse(self, response, args):
    """Sends response to DUT for each command.

    Args:
      response: response string
      args: This parameter is omitted when we test from FA-utility.
                 Otherwise, this parameter is passing from
                 handle_connection
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
    if self._use_shopfloor:
      self.InitAudioParameter()

    file_path = os.path.join(self._caches_dir, self._parameters[0])
    try:
      with open(file_path, 'rb') as md5_file:
        rawstring = md5_file.read()
        self.SendResponse(rawstring.strip(), args)
    except IOError:
      factory.console.error('No such file or directory: %s', file_path)
      self.SendResponse('NO_VERSION', args)

  def HandleConfigFile(self, *args):
    """Return the content of configuration file."""
    file_path = os.path.join(self._caches_dir, self._parameters[1])
    try:
      with open(file_path, 'rb') as config_file:
        rawstring = config_file.read()
        """The format of file content is 'file_name;file_size;file_content'.

        The file size is real file size instead of the size after
        b2a_hex. Using b2a_hex is to avoid the file content including
        special character such as '\x03', '\x04', and '\x05'.
        """  # pylint: disable=W0105
        rawdata = (os.path.basename(self._parameters[1]) + ';' +
                   str(len(rawstring)) + ';' +
                   binascii.b2a_hex(rawstring))

        self.SendResponse(rawdata, args)
    except IOError:
      factory.console.error('No such file or directory: %s', file_path)
      self.SendResponse('NO_CONFIG;0;%s' % binascii.b2a_hex(''), args)

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

    write_path = os.path.join(paths.GetLogRoot(), 'aux', 'audio', file_name)
    file_utils.TryMakeDirs(os.path.dirname(write_path))
    factory.console.info('save file: %s', write_path)
    with open(write_path, 'wb') as f:
      f.write(real_data)
    self._auxlogs.append(write_path)

    if self.DecompressZip(write_path, tempfile.gettempdir()):
      file_path = os.path.join(tempfile.gettempdir(), 'description.yaml')
      with open(file_path, 'r') as f:
        test_result = yaml.load(f)
      Log('audio_quality_result', **test_result)

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

    write_path = os.path.join(paths.GetLogRoot(), 'aux', 'audio', file_name)
    file_utils.TryMakeDirs(os.path.dirname(write_path))
    factory.console.info('save file: %s', write_path)
    with open(write_path, 'wb') as f:
      f.write(received_data)
    self._auxlogs.append(write_path)

    logging.info('Received file %s with size %d', file_name, size)

    # Dump another copy of logs
    logging.info(repr(received_data))

    '''The result logs are stored in filename ending in _[0-9]+.txt.

    Its content looks like:
    Freq [Hz]   dBV         Phase [Deg]
    100.00      -60.01      3.00
    105.93      -64.04      33.85
    112.20      -68.47      92.10
    ...

    The column count is variable. There may be up to ten columns in the
    results. Each column contains 12 characters. Because the spaces on
    the right side of last colume are stripped. So the number of column
    is the length of line divides by 12 and plus one.

    Unfortunately, we cannot read the column names in the header row
    by splitting with spaces.
    '''  # pylint: disable=W0105

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
      column_number = max([len(line) / 12 + 1 for line in lines[1:]])
      for line in lines[1:]:
        x = []
        for i in range(column_number):
          x.append(float(line[i * 12:i * 12 + 12].strip() or 'nan'))
        table.append(x)

      test_result = {}
      # Remarks:
      # 1. cros.factory.test.event_log requires special format for key string
      # 2. because the harmonic of some frequencies are not valid, we may
      #    have empty values in certain fields
      # 3. The missing fields are always in the last columns
      frequencies = dict((row[0], row[1:]) for row in table)
      test_result['frequencies'] = frequencies
      test_result['header_row'] = header_row
      test_result['serial_number'] = serial_number
      test_result['timestamp'] = timestamp

      Log(('audio_quality_test_%s' % test_index), **test_result)
    elif match2:
      serial_number, timestamp = match2.groups()

      final_result = {}
      final_result['serial_number'] = serial_number
      final_result['timestamp'] = timestamp
      final_result['data'] = received_data.replace('\r', '')

      Log('audio_quality_final_result', **final_result)
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
    if self._use_shopfloor:
      self.UploadAuxlog()

    self.SendResponse(None, args)
    self._test_complete = True

    # Restores the original state before exiting the test.
    Spawn(['iptables', '-D', 'INPUT', '-p', 'tcp', '--dport', str(self._port),
           '-j', 'ACCEPT'], check_call=True)
    self.RestoreConfiguration()

    logging.info('%s run_once finished', self.__class__)

  def HandleLoopDefault(self, *args):
    """Restore amixer configuration to default."""
    self.RestoreConfiguration()
    self._ui.CallJSFunction('setMessage', _LABEL_WAITING)
    self.SendResponse(None, args)

  def HandleLoop(self):
    """Starts the internal audio loopback."""
    self._ui.CallJSFunction('setMessage', _LABEL_AUDIOLOOP)

    if self._loop_type == LoopType.sox:
      cmdargs = [audio_utils.SOX_PATH, '-t', 'alsa',
                 self._alsa_input_device, '-t',
                 'alsa', self._alsa_output_device]
      self._loop_process = Spawn(cmdargs)
    elif self._loop_type == LoopType.looptest:
      cmdargs = [audio_utils.AUDIOLOOP_PATH, '-i', self._alsa_input_device,
                 '-o', self._alsa_output_device, '-c',
                 str(self._loop_buffer_count)]
      self._loop_process = Spawn(cmdargs)
    elif self._loop_type == LoopType.tinyloop:
      self._dut.audio.CreateAudioLoop(self._in_card, self._in_subdevice,
                                      self._out_card, self._out_subdevice)
    elif self._loop_type == LoopType.hwloop:
      pass

  def HandleMultitone(self, *args):
    """Plays the multi-tone wav file."""
    wav_path = os.path.join(self._file_path, '10SEC.wav')
    cmdargs = ['aplay', wav_path]
    self._multitone_process = Spawn(cmdargs)
    self.SendResponse(None, args)

  def HandleLoopJack(self, *args):
    """External mic loop to headphone."""
    factory.console.info('Audio Loop Mic Jack->Headphone')
    self.RestoreConfiguration()
    if not self._dut.audio.ApplyAudioConfig(_JACK_HP_SCRIPT, 0, True):
      self._dut.audio.EnableExtmic(self._in_card)
      self._dut.audio.EnableHeadphone(self._out_card)
    if self._use_multitone:
      self.HandleMultitone()
    else:
      self.HandleLoop()
    self._ui.CallJSFunction('setMessage', _LABEL_AUDIOLOOP)
    self.SendResponse(None, args)

  def HandleLoopFromDmicToJack(self, *args):
    """LCD mic loop to headphone."""
    factory.console.info('Audio Loop DMIC->Headphone')
    self.RestoreConfiguration()
    self._ui.CallJSFunction('setMessage', _LABEL_AUDIOLOOP + _LABEL_DMIC_ON)
    if not self._dut.audio.ApplyAudioConfig(_DMIC_JACK_SCRIPT, 0, True):
      self._dut.audio.EnableHeadphone(self._out_card)
      self._dut.audio.EnableDmic(self._in_card)
    self.HandleLoop()
    self.SendResponse(None, args)

  def HandleLoopFromDmic2ToJack(self, *args):
    """LCD mic loop to headphone."""
    factory.console.info('Audio Loop DMIC2->Headphone')
    self.RestoreConfiguration()
    self._ui.CallJSFunction('setMessage', _LABEL_AUDIOLOOP + _LABEL_DMIC_ON)
    if not self._dut.audio.ApplyAudioConfig(_DMIC2_JACK_SCRIPT, 0, True):
      self._dut.audio.EnableDmic2(self._in_card)
      self._dut.audio.EnableHeadphone(self._out_card)
    self.HandleLoop()
    self.SendResponse(None, args)

  def HandleLoopFromJackToSpeaker(self, *args):
    """External mic loop to speaker."""
    factory.console.info('Audio Loop Mic Jack->Speaker')
    self.RestoreConfiguration()
    self._ui.CallJSFunction('setMessage', _LABEL_AUDIOLOOP +
                            _LABEL_SPEAKER_MUTE_OFF)
    if not self._dut.audio.ApplyAudioConfig(_JACK_SPEAKER_SCRIPT, 0, True):
      self._dut.audio.EnableExtmic(self._in_card)
      self._dut.audio.EnableSpeaker(self._out_card)
    if self._use_multitone:
      self.HandleMultitone()
    else:
      self.HandleLoop()
    self.SendResponse(None, args)

  def HandleLoopFromKeyboardDmicToJack(self, *args):
    """Keyboard mic loop to headphone."""
    factory.console.info('Audio Loop MLB DMIC->Headphone')
    self.RestoreConfiguration()
    self._ui.CallJSFunction('setMessage', _LABEL_AUDIOLOOP + _LABEL_MLBDMIC_ON)
    if not self._dut.audio.ApplyAudioConfig(_KDMIC_JACK_SCRIPT, 0, True):
      self._dut.audio.EnableMLBDmic(self._in_card)
      self._dut.audio.EnableHeadphone(self._out_card)
    self.HandleLoop()
    self.SendResponse(None, args)

  def HandleXtalkLeft(self, *args):
    """Cross talk left."""
    self.RestoreConfiguration()
    self._ui.CallJSFunction('setMessage', _LABEL_PLAYTONE_LEFT)
    self._dut.audio.MuteLeftHeadphone(self._out_card)
    cmdargs = audio_utils.GetPlaySineArgs(1, self._alsa_output_device)
    self._tone_process = Spawn(cmdargs)
    self.SendResponse(None, args)

  def HandleXtalkRight(self, *args):
    """Cross talk right."""
    self.RestoreConfiguration()
    self._ui.CallJSFunction('setMessage', _LABEL_PLAYTONE_RIGHT)
    self._dut.audio.MuteRightHeadphone(self._out_card)
    cmdargs = audio_utils.GetPlaySineArgs(0, self._alsa_output_device)
    self._tone_process = Spawn(cmdargs)
    self.SendResponse(None, args)

  def HandleMuteSpeakerLeft(self, *args):
    """Mute Left Speaker."""
    factory.console.info('Mute Speaker Left')
    self._dut.audio.MuteLeftSpeaker(self._out_card)
    self.SendResponse(None, args)

  def HandleMuteSpeakerRight(self, *args):
    """Mute Left Speaker."""
    factory.console.info('Mute Speaker Right')
    self._dut.audio.MuteRightSpeaker(self._out_card)
    self.SendResponse(None, args)

  def ListenForever(self, sock):
    """Thread function to handle socket.

    Args:
      sock: socket object.
    """
    fd = sock.fileno()
    while True:
      _rl, _, _ = select.select([fd], [], [])
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
      self._ui.CallJSFunction('setMessage', _LABEL_SPACE_TO_START)
    for key in self._handlers.iterkeys():
      if key.match(cmd):
        self._handlers[key]()
        break

  def InitAudioParameter(self):
    """Downloads parameters from shopfloor and saved to state/caches.

    The parameters include a ZIP file and a md5 checksum file.
    ZIP file is including all the files which are needed by Audio
    analysis software.
    md5 checksum file is used to check ZIP file version.
    If the version is mismatch, analysis software can download
    latest parameter and apply it.
    """
    factory.console.info('Start downloading parameters...')
    self._ui.CallJSFunction('setMessage', _LABEL_CONNECT_SHOPFLOOR)
    shopfloor_client = shopfloor.GetShopfloorConnection(retry_interval_secs=3)
    logging.info('Syncing time with shopfloor...')
    goofy = factory.get_state_instance()
    goofy.SyncTimeWithShopfloorServer()

    self._ui.CallJSFunction('setMessage', _LABEL_DOWNLOADING_PARAMETERS)
    download_list = []
    for glob_expression in self._parameters:
      logging.info('Listing %s', glob_expression)
      download_list.extend(
          shopfloor_client.ListParameters(glob_expression))
    factory.console.info('Download list prepared:\n%s',
                         '\n'.join(download_list))
    if len(download_list) < len(self._parameters):
      factory.console.warn('Parameters cannot be found on shopfloor:\n%s',
                           self._parameters)
      return

    # Download the list and saved to caches in state directory.
    for filepath in download_list:
      Spawn(['mkdir', '-p', os.path.join(
          self._caches_dir, os.path.dirname(filepath))], check_call=True)
      binary_obj = shopfloor_client.GetParameter(filepath)
      with open(os.path.join(self._caches_dir, filepath), 'wb') as fd:
        fd.write(binary_obj.data)

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
    self._ui.CallJSFunction('setMessage', _LABEL_READY)

    while True:
      if self._test_complete:
        break
      time.sleep(_CHECK_FIXTURE_COMPLETE_SECS)

  def UploadAuxlog(self):
    """Uploads files which are sent from DUT by send_file command to
    shopfloor.
    """
    factory.console.info('Start uploading logs...')
    self._ui.CallJSFunction('setMessage', _LABEL_UPLOAD_AUXLOG)
    shopfloor.UploadAuxLogs(self._auxlogs, dir_name='audio')

  def StartRun(self, event):  # pylint: disable=W0613
    """Runs the testing flow after user press 'space'.

    Args:
      event: event from UI.
    """
    self.RunAudioServer()

    if self._test_passed:
      self._ui.Pass()
      factory.console.info('Test passed')
    else:
      if self._use_shopfloor:
        factory.console.info(
            'Test failed. Force to flush event logs...')
        goofy = factory.get_state_instance()
        goofy.FlushEventLogs()
      self._ui.Fail(_LABEL_FAIL_LOGS)
