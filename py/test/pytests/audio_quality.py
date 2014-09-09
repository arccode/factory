# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# DESCRIPTION :
#
# This test case is used to communicate with audio fixture and parse
# the result of CLIO which is audio quality analysis software.

import binascii
import logging
import os
import re
import select
import socket
import threading
import time
import unittest
import yaml

from cros.factory.event_log import Log
from cros.factory.test.args import Arg
from cros.factory.test import factory
from cros.factory.test import network
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import utils
from cros.factory.test import audio_utils
from cros.factory.utils import net_utils
from cros.factory.utils.process_utils import Spawn, TerminateOrKillProcess
from cros.factory.goofy.goofy import CACHES_DIR

# Host test machine crossover connected to DUT, fix local ip and port for
# communication in between.
_HOST = ''
_PORT = 8888
_LOCAL_IP = '192.168.1.2'

# Setting
_SHOPFLOOR_TIMEOUT_SECS = 10 # Timeout for shopfloor connection.
_SHOPFLOOR_RETRY_INTERVAL_SECS = 10 # Seconds to wait between retries.
_CHECK_FIXTURE_COMPLETE_SECS = 1 # Seconds to check fixture test.
_REMOVE_ETHERNET_TIMEOUT_SECS = 30 # Timeout for inserting dongle.
_FIXTURE_PARAMETERS = ['audio/audio_md5', 'audio/audio.zip']

# Label strings.
_LABEL_SPACE_TO_START = test_ui.MakeLabel('Press \'Space\' to start test',
    u'按空白键开始测试')
_LABEL_CONNECTED = test_ui.MakeLabel('Connected', u'已连线')
_LABEL_WAITING = test_ui.MakeLabel('Waiting for command', u'等待指令中')
_LABEL_AUDIOLOOP = test_ui.MakeLabel('Audio looping', u'音源回放中')
_LABEL_SPEAKER_MUTE_OFF = test_ui.MakeLabel('Speaker on', u'喇叭开启')
_LABEL_DMIC_ON = test_ui.MakeLabel('Dmic on', u'LCD mic开启')
_LABEL_PLAYTONE_LEFT = test_ui.MakeLabel('Playing tone to left channel',
    u'播音至左声道')
_LABEL_PLAYTONE_RIGHT = test_ui.MakeLabel('Playing tone to right channel',
    u'播音至右声道')
_LABEL_WAITING_ETHERNET = test_ui.MakeLabel(
    'Waiting for Ethernet connectivity to ShopFloor',
    u'等待网路介面卡连接到 ShopFloor')
_LABEL_WAITING_IP = test_ui.MakeLabel('Waiting for IP address',
    u'等待 IP 设定')
_LABEL_CONNECT_SHOPFLOOR = test_ui.MakeLabel('Connecting to ShopFloor...',
    u'连接到 ShopFloor 中...')
_LABEL_DOWNLOADING_PARAMETERS = test_ui.MakeLabel(
    'Downloading parameters', u'下载测试规格中')
_LABEL_REMOVE_ETHERNET = test_ui.MakeLabel(
    'Remove Ethernet connectivity', u'移除网路介面卡')
_LABEL_WAITING_FIXTURE_ETHERNET = test_ui.MakeLabel(
    'Waiting for Ethernet connectivity to audio fixture',
    u'等待网路介面卡连接到 audio 置具')
_LABEL_READY = test_ui.MakeLabel(
    'Ready for connection', u'準备完成,等待链接')
_LABEL_UPLOAD_AUXLOG = test_ui.MakeLabel('Upload log', u'上传记录档')
_LABEL_FAIL_LOGS = 'Test fail, find more detail in log.'

# Regular expression to match external commands.
_LOOP_0_RE = re.compile("(?i)loop_0")
_LOOP_1_RE = re.compile("(?i)loop_1")
_LOOP_2_RE = re.compile("(?i)loop_2")
_LOOP_3_RE = re.compile("(?i)loop_3")
_XTALK_L_RE = re.compile("(?i)xtalk_l")
_XTALK_R_RE = re.compile("(?i)xtalk_r")
_MULTITONE_RE = re.compile("(?i)multitone")
_SEND_FILE_RE = re.compile("(?i)send_file")
_TEST_COMPLETE_RE = re.compile("(?i)test_complete")
_RESULT_PASS_RE = re.compile("(?i)result_pass")
_RESULT_FAIL_RE = re.compile("(?i)result_fail")
_VERSION_RE = re.compile("(?i)version")
_CONFIG_FILE_RE = re.compile("(?i)config_file")

class AudioQualityTest(unittest.TestCase):
  ARGS = [
    Arg('initial_actions', list, 'List of tuple (card, actions)', []),
    Arg('input_dev', (str, tuple),
        'Input ALSA device for string.  (card_name, sub_device) for tuple. '
        'For example: "hw:0,0" or ("audio_card", "0").', 'hw:0,0'),
    Arg('output_dev', (str, tuple),
        'Output ALSA device for string.  (card_name, sub_device) for tuple. '
        'For example: "hw:0,0" or ("audio_card", "0").', 'hw:0,0'),
    Arg('use_sox_loop', bool, 'Use SOX loop', False, optional=True),
    Arg('use_multitone', bool, 'Use multitone', False, optional=True),
    Arg('loop_buffer_count', int, 'Count of loop buffer', 10,
        optional=True),
    Arg('fixture_param', list, 'Fixture parameters', _FIXTURE_PARAMETERS,
        optional=True),
    Arg('use_shopfloor', bool, 'Use shopfloor', True, optional=True),
  ]

  def setUp(self):
    # Tansfer input and output device format
    if isinstance(self.args.input_dev, tuple):
      self._in_card = audio_utils.GetCardIndexByName(self.args.input_dev[0])
      self._input_device = "hw:%s,%s" % (
          self._in_card, self.args.input_dev[1])
    else:
      self._input_device = self.args.input_dev
      self._in_card = self.GetCardIndex(self._input_device)

    if isinstance(self.args.output_dev, tuple):
      self._out_card = audio_utils.GetCardIndexByName(self.args.output_dev[0])
      self._output_device = "hw:%s,%s" % (
          self._out_card, self.args.output_dev[1])
    else:
      self._output_device = self.args.output_dev
      self._out_card = self.GetCardIndex(self._output_device)

    # Initialize frontend presentation
    self._eth = None
    self._test_complete = False
    self._test_passed = False
    self._use_sox_loop = self.args.use_sox_loop
    self._use_multitone = self.args.use_multitone
    self._loop_buffer_count = self.args.loop_buffer_count
    self._parameters = self.args.fixture_param
    self._use_shopfloor = self.args.use_shopfloor

    self._listen_thread = None
    self._multitone_process = None
    self._tone_process = None
    self._loop_process = None
    self._caches_dir = os.path.join(CACHES_DIR, 'parameters')
    base = os.path.dirname(os.path.realpath(__file__))
    self._file_path = os.path.join(base, '..', '..', 'goofy', 'static',
        'sounds')
    self._auxlogs = []

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
    self._handlers[_XTALK_L_RE] = self.HandleXtalkLeft
    self._handlers[_XTALK_R_RE] = self.HandleXtalkRight
    self._handlers[_MULTITONE_RE] = self.HandleMultitone
    self._handlers[_VERSION_RE] = self.HandleVersion
    self._handlers[_CONFIG_FILE_RE] = self.HandleConfigFile

    self._audio_util = audio_utils.AudioUtil()
    self._ui = test_ui.UI()
    self._ui.CallJSFunction('setMessage', _LABEL_SPACE_TO_START)
    self._ui.AddEventHandler('start_run', self.StartRun)
    self._ui.AddEventHandler('mock_command', self.MockCommand)
    Spawn(['iptables', '-A', 'INPUT', '-p', 'tcp', '--dport', str(_PORT), '-j',
        'ACCEPT'], check_call=True)

  def runTest(self):
    self._ui.Run()

  def tearDown(self):
    self._audio_util.RestoreMixerControls()

  def GetCardIndex(self, device):
    """Gets the card index from given device names.

    Args:
      device: ALSA device name
    """
    dev_name_pattern = re.compile(".*?hw:([0-9]+),([0-9]+)")
    match = dev_name_pattern.match(device)
    if match:
      return match.group(1)
    else:
      raise ValueError('device name %s is incorrect' % device)

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
          factory.console.error("Command %s cannot find", instruction)
          conn.send(instruction + '\x05' + 'Active_End' + '\x05' +
              'Fail' + '\x04\x03')

      if self._test_complete:
        factory.console.info('Test completed')
        break
    factory.console.info("Connection disconnect")
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
      logging.info("Stopped audio loop process")

    for card, action in self.args.initial_actions:
      if card.isdigit() is False:
        card = audio_utils.GetCardIndexByName(card)
      self._audio_util.ApplyAudioConfig(action, card)
    self._audio_util.DisableDmic(self._in_card)
    self._audio_util.EnableExtmic(self._in_card)
    self._audio_util.DisableSpeaker(self._out_card)
    self._audio_util.EnableHeadphone(self._out_card)

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
    file_path = os.path.join(self._caches_dir, self._parameters[0])
    try:
      with open(file_path, "rb") as md5_file:
        rawstring = md5_file.read()
        self.SendResponse(rawstring.strip(), args)
    except IOError:
      factory.console.error('No such file or directory: %s', file_path)
      self.SendResponse("NO_VERSION", args)

  def HandleConfigFile(self, *args):
    """Return the content of configuration file."""
    file_path = os.path.join(self._caches_dir, self._parameters[1])
    try:
      with open(file_path, "rb") as config_file:
        rawstring = config_file.read()
        """
        The format of file content is
        'file_name;file_size;file_content'.
        The file size is real file size instead of the size after b2a_hex.
        Using b2a_hex is to avoid the file content including special
        character such as '\x03', '\x04', and '\x05'.
        """ # pylint: disable=W0105
        rawdata = (os.path.basename(self._parameters[1]) + ';' +
                   str(len(rawstring)) + ';' +
                   binascii.b2a_hex(rawstring))

        self.SendResponse(rawdata, args)
    except IOError:
      factory.console.error('No such file or directory: %s', file_path)
      self.SendResponse("NO_CONFIG;0;%s" % binascii.b2a_hex(''), args)

  def HandleSendFile(self, *args):
    """This function is used to save test results from DUT.

    Supposes the file is a YAML format. Reads the file and uploads to event
    log.
    """
    attr_list = args[1]
    file_name = attr_list[1]
    size = int(attr_list[2])
    received_data = attr_list[3]

    logging.info("Received file %s with size %d" , file_name, size)

    write_path = os.path.join(factory.get_log_root(), 'aux', 'audio', file_name)
    utils.TryMakeDirs(os.path.dirname(write_path))
    factory.console.info('save file: %s', write_path)
    with open(write_path, 'wb') as f:
      f.write(received_data)
    self._auxlogs.append(write_path)

    test_result = yaml.load(received_data)
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

    write_path = os.path.join(factory.get_log_root(), 'aux', 'audio', file_name)
    utils.TryMakeDirs(os.path.dirname(write_path))
    factory.console.info('save file: %s', write_path)
    with open(write_path, 'wb') as f:
      f.write(received_data)
    self._auxlogs.append(write_path)

    logging.info("Received file %s with size %d" , file_name, size)

    # Dump another copy of logs
    logging.info(repr(received_data))

    '''
    The result logs are stored in filename ending in _[0-9]+.txt.

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
    ''' # pylint: disable=W0105

    match = re.search(r"(\d+)_(\d+)_(\d+).txt", file_name)
    match2 = re.search(r"(\d+)_(\d+).txt", file_name)

    if match:
      """
      serial_number and timestamp are generated by camerea test fixture.
      We can use these two strings to lookup the raw logs on fixture.
      """ # pylint: disable=W0105
      serial_number, timestamp, test_index = match.groups()

      lines = received_data.splitlines()
      header_row = lines[0]

      table = []
      """
      record the maximum column_number, to add sufficient 'nan' to
      the end of list if the spaces in the end of line are stripped.
      """ # pylint: disable=W0105
      column_number = max([len(line)/12 + 1 for line in lines[1:]])
      for line in lines[1:]:
        x = []
        for i in range(column_number):
          x.append(float(line[i*12:i*12 + 12].strip() or 'nan'))
        table.append(x)

      test_result = {}
      """
      Remarks:
      1. cros.factory.event_log requires special format for key string
      2. because the harmonic of some frequencies are not valid, we may
         have empty values in certain fields
      3. The missing fields are always in the last columns
      """ # pylint: disable=W0105
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
      logging.info("Unrecognizable filename %s", file_name)

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
    #Restores the original state before exiting the test.
    Spawn(['iptables', '-D', 'INPUT', '-p', 'tcp', '--dport', str(_PORT),
        '-j', 'ACCEPT'], check_call=True)
    Spawn(['ifconfig', self._eth, 'down'], check_call=True)
    Spawn(['ifconfig', self._eth, 'up'], check_call=True)
    self.RestoreConfiguration()

    logging.info('%s run_once finished', self.__class__)
    self.SendResponse(None, args)
    self._test_complete = True

  def HandleLoopDefault(self, *args):
    """Restore amixer configuration to default."""
    self.RestoreConfiguration()
    self._ui.CallJSFunction('setMessage', _LABEL_WAITING)
    self.SendResponse(None, args)

  def HandleLoop(self):
    """Starts the internal audio loopback."""
    self.RestoreConfiguration()
    self._ui.CallJSFunction('setMessage', _LABEL_AUDIOLOOP)
    if self._use_sox_loop:
      cmdargs = [audio_utils.SOX_PATH, '-t', 'alsa',
                 self._input_device, '-t',
                 'alsa', self._output_device]
      self._loop_process = Spawn(cmdargs)
    else:
      cmdargs = [audio_utils.AUDIOLOOP_PATH, '-i', self._input_device, '-o',
                 self._output_device, '-c', str(self._loop_buffer_count)]
      self._loop_process = Spawn(cmdargs)

  def HandleMultitone(self, *args):
    """Plays the multi-tone wav file."""
    self.RestoreConfiguration()
    wav_path = os.path.join(self._file_path, '10SEC.wav')
    cmdargs = ['aplay', wav_path]
    self._multitone_process = Spawn(cmdargs)
    self.SendResponse(None, args)

  def HandleLoopJack(self, *args):
    """External mic loop to headphone."""
    if self._use_multitone:
      self.HandleMultitone()
    else:
      self.HandleLoop()
    self._ui.CallJSFunction('setMessage', _LABEL_AUDIOLOOP)
    self.SendResponse(None, args)

  def HandleLoopFromDmicToJack(self, *args):
    """Digital mic loop to headphone."""
    self.HandleLoop()
    self._ui.CallJSFunction('setMessage', _LABEL_AUDIOLOOP + _LABEL_DMIC_ON)
    self._audio_util.DisableExtmic(self._in_card)
    self._audio_util.EnableDmic(self._in_card)
    self._audio_util.DisableSpeaker(self._out_card)
    self._audio_util.EnableHeadphone(self._out_card)
    self.SendResponse(None, args)

  def HandleLoopFromJackToSpeaker(self, *args):
    """External mic loop to speaker."""
    if self._use_multitone:
      self.HandleMultitone()
    else:
      self.HandleLoop()
    self._ui.CallJSFunction('setMessage', _LABEL_AUDIOLOOP +
        _LABEL_SPEAKER_MUTE_OFF)
    self._audio_util.DisableDmic(self._in_card)
    self._audio_util.EnableExtmic(self._in_card)
    self._audio_util.DisableHeadphone(self._out_card)
    self._audio_util.EnableSpeaker(self._out_card)
    self.SendResponse(None, args)

  def HandleXtalkLeft(self, *args):
    """Cross talk left."""
    self.RestoreConfiguration()
    self._ui.CallJSFunction('setMessage', _LABEL_PLAYTONE_LEFT)
    self._audio_util.MuteLeftHeadphone(self._out_card)
    cmdargs = audio_utils.GetPlaySineArgs(1, self._output_device)
    self._tone_process = Spawn(cmdargs)
    self.SendResponse(None, args)

  def HandleXtalkRight(self, *args):
    """Cross talk right."""
    self.RestoreConfiguration()
    self._ui.CallJSFunction('setMessage', _LABEL_PLAYTONE_RIGHT)
    self._audio_util.MuteRightHeadphone(self._out_card)
    cmdargs = audio_utils.GetPlaySineArgs(0, self._output_device)
    self._tone_process = Spawn(cmdargs)
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

  def RemoveNetwork(self):
    """Detect and wait ethernet remove."""
    while True:
      try:
        self._ui.CallJSFunction('setMessage', _LABEL_REMOVE_ETHERNET)
        logging.info('Removing Ethernet device...')
        net_utils.PollForCondition(condition=(
            lambda: False if net_utils.FindUsableEthDevice() else True),
            timeout=_REMOVE_ETHERNET_TIMEOUT_SECS,
            condition_name='Remove Ethernet device')
        break
      except:  # pylint: disable=W0702
        exception_string = utils.FormatExceptionOnly()
        factory.console.error('Remove Ethernet Exception: %s',
                              exception_string)

  def PrepareNetwork(self, force_ip, msg):
    """Blocks forever until network is prepared.

    Args:
      force_ip: If true, set _LOCAL_IP. Otherwise, use DHCP
      msg: The message will be shown in UI
    """
    self._ui.CallJSFunction('setMessage', msg)
    network.PrepareNetwork(
        _LOCAL_IP, force_ip,
        lambda: self._ui.CallJSFunction('setMessage', _LABEL_WAITING_IP))
    self._eth = net_utils.FindUsableEthDevice()

  def GetShopfloorConnection(
      self, timeout_secs=_SHOPFLOOR_TIMEOUT_SECS,
      retry_interval_secs=_SHOPFLOOR_RETRY_INTERVAL_SECS):
    """Returns a shopfloor client object.

    Try forever until a connection of shopfloor is established.

    Args:
      timeout_secs: Timeout for shopfloor connection.
      retry_interval_secs: Seconds to wait between retries.
    """
    factory.console.info('Connecting to shopfloor...')
    while True:
      try:
        shopfloor_client = shopfloor.get_instance(
            detect=True, timeout=timeout_secs)
        break
      except:  # pylint: disable=W0702
        exception_string = utils.FormatExceptionOnly()
        logging.info('Unable to sync with shopfloor server: %s',
                     exception_string)
      time.sleep(retry_interval_secs)
    return shopfloor_client

  def InitAudioParameter(self):
    """Downloads parameters from shopfloor and saved to state/caches.

    The parameters include a ZIP file and a md5 checksum file.
    ZIP file is including all the files which are needed by Audio
    analysis software.
    md5 checksum file is used to check ZIP file version.
    If the version is mismatch, analysis software can download
    latest parameter and apply it.
    """
    self.PrepareNetwork(False, _LABEL_WAITING_ETHERNET)
    factory.console.info('Start downloading parameters...')
    self._ui.CallJSFunction('setMessage', _LABEL_CONNECT_SHOPFLOOR)
    shopfloor_client = self.GetShopfloorConnection()
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
      factory.console.error('Parameters cannot be found on shopfloor:\n%s',
          self._parameters)
      self._ui.Fail('Parameters cannot be found on shopfloor')
    #Download the list and saved to caches in state directory.
    for filepath in download_list:
      Spawn(['mkdir', '-p', os.path.join(
          self._caches_dir, os.path.dirname(filepath))], check_call=True)
      binary_obj = shopfloor_client.GetParameter(filepath)
      with open(os.path.join(self._caches_dir, filepath), 'wb') as fd:
        fd.write(binary_obj.data)
    self.RemoveNetwork()

  def RunAudioServer(self):
    """Initializes server and starts listening for external commands."""
    self.PrepareNetwork(True, _LABEL_WAITING_FIXTURE_ETHERNET)
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((_HOST, _PORT))
    sock.listen(1)
    logging.info("Listening at port %d", _PORT)

    self._listen_thread = threading.Thread(target=self.ListenForever,
        args=(sock,))
    self._listen_thread.start()
    self._ui.CallJSFunction('setMessage', _LABEL_READY)

    while True:
      if self._test_complete:
        break
      time.sleep(_CHECK_FIXTURE_COMPLETE_SECS)
    self.RemoveNetwork()

  def UploadAuxlog(self):
    """Uploads files which are sent from DUT by send_file command to
    shopfloor.
    """
    self.PrepareNetwork(False, _LABEL_WAITING_ETHERNET)
    factory.console.info('Start uploading logs...')
    self._ui.CallJSFunction('setMessage', _LABEL_UPLOAD_AUXLOG)
    shopfloor.UploadAuxLogs(self._auxlogs)

  def StartRun(self, event): #pylint: disable=W0613
    """Runs the testing flow after user press 'space'.

    Args:
      event: event from UI.
    """
    if self._use_shopfloor:
      self.InitAudioParameter()

    self.RunAudioServer()

    if self._use_shopfloor:
      self.UploadAuxlog()

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
