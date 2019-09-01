#!/usr/bin/env python2


# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A simple XML RPC server manipulating sys fs data.

Note: this module does not have any dependency on factory stuffs so that
      it could be run as a pure server e.g. on a Beagle Bone.
"""

from __future__ import print_function

import ConfigParser
import logging
import os
import re
import SimpleXMLRPCServer
import sys
import time

import touchscreen_calibration_utils as utils


# List the supported boards below
SAMUS = 'samus'
RYU = 'ryu'
RUSH_RYU = 'rush_ryu'


class Error(Exception):
  pass


REMOTE_COMMAND_FLAGS = [
    '-i', os.path.join(os.path.dirname(__file__), '.test_rsa'),
    '-o', 'UserKnownHostsFile=/dev/null',
    '-o', 'StrictHostKeyChecking=no',
]


def SshCommand(ip, cmd, output=True):
  """Execute a remote command through ssh."""
  remote_args = ['ssh', 'root@%s' % ip] + REMOTE_COMMAND_FLAGS + [cmd]
  cmd_str = ' '.join(remote_args)
  if output:
    return utils.SimpleSystemOutput(cmd_str)
  else:
    return utils.IsSuccessful(utils.SimpleSystem(cmd_str))


def ScpCommand(ip, filename, remote_path):
  """Execute a remote command through ssh."""
  remote_args = (['scp'] + REMOTE_COMMAND_FLAGS +
                 ['-p', filename, 'root@%s:%s' % (ip, remote_path)])
  return utils.IsSuccessful(utils.SimpleSystem(' '.join(remote_args)))


class TSConfig(object):
  """Manage the touchscreen config data."""

  def __init__(self, board):
    config_filepath = os.path.join(os.path.dirname(__file__),
                                   'boards', board, '%s.conf' % board)
    if not os.path.isfile(config_filepath):
      raise Error('The config file does not exist: ' + config_filepath)

    self.parser = ConfigParser.ConfigParser()
    try:
      with open(config_filepath) as f:
        self.parser.readfp(f)
    except Exception:
      raise Error('Failed to read config file: %s.' % config_filepath)

  def Read(self, section, option):
    """Read config data."""
    if (self.parser.has_section(section) and
        self.parser.has_option(section, option)):
      return self.parser.get(section, option)
    return None

  def GetItems(self, section):
    """Get section items."""
    return self.parser.items(section)


class BaseSensorService(object):
  """A base class to provide sensor relalted services."""

  def __init__(self, board, log=None):
    self.board = board
    self.config = TSConfig(board)
    self.log = log
    kernel_module_name = self.config.Read('Misc', 'kernel_module_name')
    self.kernel_module = utils.KernelModule(kernel_module_name)
    self.delta_lower_bound = int(
        self.config.Read('TouchSensors', 'DELTA_LOWER_BOUND'))
    self.delta_higher_bound = int(
        self.config.Read('TouchSensors', 'DELTA_HIGHER_BOUND'))
    self.delta_untouched_higher_bound = int(
        self.config.Read('TouchSensors', 'DELTA_UNTOUCHED_HIGHER_BOUND'))
    self.normalized_deviation_threshold = float(
        self.config.Read('TouchSensors', 'NORMALIZED_DEVIATION_THRESHOLD'))
    self.normalized_edge_deviation_threshold = float(
        self.config.Read('TouchSensors', 'NORMALIZED_EDGE_DEVIATION_THRESHOLD'))

  def CheckStatus(self):
    """Checks if the touchscreen sensor data object is present.

    Returns:
      True if the sensor data object is present.
    """
    raise NotImplementedError(
        'Should implement the CheckStatus() method in the subclass.')

  def Read(self, category):
    """Implementation of sensor reading method.

    Returns:
      Sensor data: a list of lists of row sensor data
    """
    raise NotImplementedError(
        'Should implement the Read() method in the subclass.')

  def VerifyRefs(self, data):
    """Verify sensor refs data.

    This checks the uniformity of the refs data.

    mean = the sum of all refs data divided by the number of sensors
    deviation = ref_value_of_a_sensor - mean
    normalized_deviation = abs(deviation) / mean

    Returns:
      True if the sensor refs data are legitimate.
    """
    def IsEdge(row, col):
      return (row == 0 or row == max_row_number or
              col == 0 or col == max_col_number)

    test_pass = True
    failed_sensors = []
    min_value = float('inf')
    max_value = float('-inf')
    mean = (float(sum([sum(row_data) for row_data in data])) /
            sum([len(row_data) for row_data in data]))
    max_row_number = len(data) - 1
    max_col_number = len(data[0]) - 1
    for row, row_data in enumerate(data):
      for col, value in enumerate(row_data):
        min_value = min(min_value, value)
        max_value = max(max_value, value)
        normalized_deviation = abs(value - mean) / mean
        if IsEdge(row, col):
          threshold = self.normalized_edge_deviation_threshold
        else:
          threshold = self.normalized_deviation_threshold
        if normalized_deviation > threshold:
          failed_sensors.append((row, col, value))
          test_pass = False
    return test_pass, failed_sensors, min_value, max_value

  def VerifyDeltasUntouched(self, data):
    """Verify sensor deltas data before the panel is touched.

    Returns:
      True if the sensor deltas data are legitimate.
    """
    test_pass = True
    failed_sensors = []
    min_value = float('inf')
    max_value = float('-inf')
    for row, row_data in enumerate(data):
      for col, value in enumerate(row_data):
        min_value = min(min_value, value)
        max_value = max(max_value, value)
        if abs(value) > self.delta_untouched_higher_bound:
          failed_sensors.append((row, col, value))
          test_pass = False
    return test_pass, failed_sensors, min_value, max_value

  def _VerifyDeltasTouched(self, data, touched_cols):
    """Verify sensor deltas data when the panel is touched.

    Returns:
      True if the sensor deltas data are legitimate.
    """
    test_pass = True
    failed_sensors = []
    min_value = float('inf')
    max_value = float('-inf')
    for row, row_data in enumerate(data):
      for col in touched_cols:
        value = row_data[col]
        min_value = min(min_value, value)
        max_value = max(max_value, value)
        if value < self.delta_lower_bound or value > self.delta_higher_bound:
          failed_sensors.append((row, col, value))
          test_pass = False
    return test_pass, failed_sensors, min_value, max_value

  def PreRead(self):
    """An optional method to invoke before reading sensor data.

    Returns:
      True if execution is correct.
    """
    return True

  def PostRead(self):
    """An optional method to invoke after reading sensor data.

    Returns:
      True if execution is correct.
    """
    return True

  def PreTest(self):
    """A method to invoke before conducting the test."""
    if not self.kernel_module.IsLoaded():
      self.kernel_module.Insert()
      time.sleep(1)
    return True

  def PostTest(self):
    """An optional method to invoke after conducting the test."""
    return True


class SensorServiceSamus(BaseSensorService):
  """Sensor services for Samus.

  On Samus, the sensor data are manipulated through sys fs and kernel debug fs.
  """

  def __init__(self, log=None):
    super(SensorServiceSamus, self).__init__(SAMUS, log=log)
    self.num_rows = int(self.config.Read('TouchSensors', 'NUM_ROWS'))
    self.num_cols = int(self.config.Read('TouchSensors', 'NUM_COLS'))

    # Get sys/debug fs data (1) from samus.conf, or (2) parsing sys fs.
    self.sysfs_entry = self.config.Read('Sensors', 'sysfs_entry')
    if self.sysfs_entry is None:
      self.sysfs_entry = utils.GetSysfsEntry()
    self.debugfs = self.config.Read('Sensors', 'debugfs')
    if self.debugfs is None:
      self.debugfs = utils.GetDebugfs()

  def PreRead(self):
    """A method to invoke before reading sensor data."""
    return self.WriteSysfsSection('PreRead')

  def PostRead(self):
    """A method to invoke after reading sensor data."""
    return self.WriteSysfsSection('PostRead')

  def PostTest(self):
    """A method to invoke after conducting the test."""
    return self.kernel_module.Remove()

  def _Make_Symlink(self, target, link_name):
    """Make the symlink to the target."""
    if not os.path.isfile(target):
      self.log.error('The target does not exist: %s' % target)
      return False
    else:
      cmd_make_symlink = 'ln -s -f %s %s' % (target, link_name)
      return utils.IsSuccessful(utils.SimpleSystem(cmd_make_symlink))

  def _TouchFileUpdate(self, config_filename, link_name, update_fw=True):
    """Update touch firmware or configuraiton per update_fw flag."""
    target_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'boards', self.board, config_filename)
    link_path = os.path.join('/lib/firmware', link_name)
    filename = 'update_fw' if update_fw else 'update_config'
    sysfs_update_interface = os.path.join(os.path.dirname(self.sysfs_entry),
                                          filename)
    cmd_update = 'echo 1 > %s' % sysfs_update_interface
    self.log.info('Begin touch auto update:  %s' % cmd_update)
    if self._Make_Symlink(target_path, link_path):
      result = utils.IsSuccessful(utils.SimpleSystem(cmd_update))
      time.sleep(1)
      return result
    return False

  def WriteSysfsSection(self, section):
    """Write a section of values to sys fs."""
    self.log.info('Write Sys fs section: %s', section)
    try:
      self.log.info('Write Sys fs section: %s', section)
      section_items = self.config.GetItems(section)
    except Exception:
      self.log.info('No items in Sys fs section: %s', section)
      section_items = []
      return False

    for command, description in section_items:
      self.log.info('  %s: %s', command, description)
      if command.startswith('update_'):
        if description == 'None':
          continue
        # Try to auto update the touch firmware/configuration
        config_filename, link_name = description.split()
        if not self._TouchFileUpdate(config_filename, link_name,
                                     update_fw=command.endswith('_fw')):
          self.log.error('Failed to update touch fw/cfg: ', str(section_items))
          return False
      elif not self.WriteSysfs(command):
        # Try to update the configuration registers.
        return False
    return True

  def CheckStatus(self):
    """Checks if the touchscreen sysfs object is present.

    Returns:
      True if sysfs_entry exists
    """
    return bool(self.sysfs_entry) and os.path.exists(self.sysfs_entry)

  def WriteSysfs(self, content):
    """Writes to sysfs.

    Args:
      content: the content to be written to sysfs
    """
    try:
      with open(self.sysfs_entry, 'w') as f:
        f.write(content)
    except Exception as e:
      self.log.info('WriteSysfs failed to write %s: %s' % (content, e))
      return False

    time.sleep(0.1)
    return True

  def Read(self, category):
    """Reads touchscreen sensors raw data.

    Args:
      category: could be 'deltas' or 'refs'.

    Returns:
      the list of raw sensor values
    """
    debugfs = '%s/%s' % (self.debugfs, category)
    with open(debugfs) as f:
      # The debug fs content is composed of num_rows, where each row
      # contains (num_cols * 2) bytes of num_cols consecutive sensor values.
      num_bytes_per_row = self.num_cols * 2
      out_data = []
      for _ in range(self.num_rows):
        row_data = f.read(num_bytes_per_row)
        values = []
        for i in range(self.num_cols):
          # Correct endianness
          s = row_data[i * 2 + 1] + row_data[i * 2]
          val = int(s.encode('hex'), 16)
          # Correct signed value
          if val > 32768:
            val = val - 65535
          values.append(val)
        out_data.append(values)
    return out_data

  def Verify(self, data):
    """Verify sensor data.

    Returns:
      True if the sensor data are legitimate.
    """
    # There are 3 columns of metal fingers on the probe. The touched_cols are
    # derived through experiments. The values may vary from board to board.
    touched_cols = [1, 35, 69]
    return super(SensorServiceSamus, self)._VerifyDeltasTouched(data,
                                                                touched_cols)


class SensorServiceRyu(BaseSensorService):
  """Sensor services for Ryu.

  On Ryu, the sensor data are provided by a user-level program f54test.
  """
  # Refer to the vendor developer guide for details of the various report types.
  REPORT_TYPE = {'deltas': 2, 'refs': 3,
                 'trx_opens': 24, 'trx_gnd_shorts': 25, 'trx-shorts': 26}
  EXPECTED_VALUES = {
      'trx_opens':
          [0x00, 0x00, 0xfc, 0xff, 0xff, 0xff, 0xff, 0xff, 0x1f, 0x00, 0x00],
      'trx_gnd_shorts':
          [0x00, 0x00, 0xfc, 0xff, 0xff, 0xff, 0xff, 0xff, 0x1f, 0x00, 0x00],
      'trx-shorts':
          [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]}

  def __init__(self, ip, dut, remote_bin_root='', remote_data_dir='', tool='',
               fw_update_tool='', hid_tool='', fw_file='', install_flag=True,
               log=None):
    super(SensorServiceRyu, self).__init__(RYU, log=log)
    self.ip = ip
    self.dut = dut
    self.remote_bin_root = remote_bin_root
    self.remote_data_dir = remote_data_dir
    self.tool = tool
    self.fw_update_tool = fw_update_tool
    self.hid_tool = hid_tool
    self.fw_file = fw_file

    self.remote_tool_bin_dir = os.path.join(self.remote_bin_root, 'bin')
    self.src_dir = os.path.join(os.path.dirname(__file__), 'boards', self.board)
    self.read_cmd_prefix = '%s -r ' % self._GetToolPath(tool)
    self.check_cmd = 'test -e %s'
    self.num_rows = None
    self.num_cols = None

    if install_flag:
      self.dut.Call('mount -o remount,rw ' + self.remote_bin_root)
      if self.InstallFiles():
        self.log.info('Sucessfully installed files.')
      else:
        self.log.error('Failed to install files.')
      self.Read('deltas')
      self.status_flag = self.num_rows is not None and self.num_cols is not None
    else:
      self.status_flag = True

  def _GetToolPath(self, filename):
    """Return the filepath of a binary tool."""
    return os.path.join(self.remote_tool_bin_dir, filename)

  def _GetDataPath(self, filename):
    """Return the filepath of a data file."""
    return os.path.join(self.remote_data_dir, filename)

  def _CheckFileExistence(self, filepath):
    """Check if the file exists in the DUT."""
    return utils.IsSuccessful(self.dut.Call(self.check_cmd % filepath))

  def InstallFiles(self):
    """Install the tools and the data file on the remote machine."""
    return (self._InstallFile(self.remote_tool_bin_dir, self.tool) and
            self._InstallFile(self.remote_tool_bin_dir, self.fw_update_tool) and
            self._InstallFile(self.remote_tool_bin_dir, self.hid_tool) and
            self._InstallFile(self.remote_data_dir, self.fw_file))

  def _InstallFile(self, dst_dir, filename):
    """Install the file on the remote machine."""
    dst_filepath = os.path.join(dst_dir, filename)
    # If the filename is '' or the dst_filepath already exists, just return.
    if not filename or self._CheckFileExistence(dst_filepath):
      return True

    src_filepath = os.path.join(self.src_dir, filename)
    with open(src_filepath) as f:
      self.dut.WriteFile(dst_filepath, f.read())
    return True

  def CalibrateBaseline(self):
    """Do baseline calibration."""
    return len(self.Read('deltas')) > 0

  def CheckStatus(self):
    """Checks whether it could read the sensor data or not.

    Returns:
      True if could read sensor deltas values.
    """
    return self.status_flag

  def GetSensorDimensions(self):
    """Get the numbers of rows and columns.

    Returns:
      (num_rows, num_cols): the numbers of rows and columns
    """
    return (self.num_rows, self.num_cols)

  def _ReadRawData(self, category):
    """Read the output from execution on DUT()."""
    read_cmd = self.read_cmd_prefix + str(self.REPORT_TYPE[category])
    return self.dut.CheckOutput(read_cmd)

  def Read(self, category):
    """Reads touchscreen sensors raw data.

    The sensor data look like

    tx = 36
    rx = 51
    -4   -2   0    -1   -2   -2  ...........
    -1    5   1    -3    1   -1  ...........
    ........................................

    Resetting...
    Reset completed.

    """
    out_data = []
    for line in self._ReadRawData(category).splitlines():
      if line.startswith('tx'):
        _, value = line.split('=')
        self.num_rows = int(value)
      elif line.startswith('rx'):
        _, value = line.split('=')
        self.num_cols = int(value)
      elif line.startswith('Reset'):
        continue
      elif self.num_cols is None:
        continue
      else:
        values = line.split()
        if len(values) == self.num_cols:
          out_data.append(map(int, values))
    return out_data

  def VerifyDeltasTouched(self, data):
    """Verify sensor data when the panel is touched.

    Returns:
      True if the sensor data are legitimate.
    """
    touched_cols = range(self.num_cols)
    return super(SensorServiceRyu, self)._VerifyDeltasTouched(data,
                                                              touched_cols)

  def ReadTRx(self, category):
    """Read TRx test data.

    Report type 24: TRx opens.
    Report type 25: TRx-Gnd shorts.
    Report type 26: TRx shorts.
    Refer to the vendor's developer guide for details.

    Args:
      category: correspoding to the report type of f54test

    Returns:
      a list of bytes
    """
    out_data = []
    for line in self._ReadRawData(category).splitlines():
      if ':' in line:
        _, value_str = line.split(':')
        out_data.append(int(value_str, 16))
    return out_data

  def VerifyTRx(self, data, category):
    """Condcut TRx open/short tests.

    Report type 24: TRx opens. All bits should read '1' to pass.
    Report type 25: TRx-Gnd shorts. All bits should read '1' to pass.
    Report type 26: TRx shorts. All bits should read '0' to pass.

    The correct output of the report types 24 and 25 should look like
    000: 0x00
    001: 0x00
    002: 0xfc
    003: 0xff
    004: 0xff
    005: 0xff
    006: 0xff
    007: 0xff
    008: 0x1f
    009: 0x00
    010: 0x00

    The correct output of the report type 26 should look like
    000: 0x00
    001: 0x00
    002: 0x00
    003: 0x00
    004: 0x00
    005: 0x00
    006: 0x00
    007: 0x00
    008: 0x00
    009: 0x00
    010: 0x00

    Refer to the vendor's developer guide for details.

    Returns:
      True if the data are legitimate.
    """
    expected_values = self.EXPECTED_VALUES.get(category)
    if expected_values is None:
      raise Error('The "%s" is not supported in EXPECTED_VALUES.' % category)
    return data == expected_values

  def FlashFirmware(self, fw_version, fw_config):
    """Flash a touch firmware to the device.

    Flashing a new firmware must be followed by resetting the
    touch device. Otherwise, the touch device does not work.
    """
    existing_fw_version, existing_fw_config = self.ReadFirmwareVersion()
    if existing_fw_version == fw_version and existing_fw_config == fw_config:
      msg = 'Existing fw %s:%s is already the target one. No flashing needed.'
      self.log.info(msg % (existing_fw_version, existing_fw_config))
      return True

    cmd_update = '%s -f -d /dev/hidraw0 %s' % (
        self._GetToolPath(self.fw_update_tool),
        self._GetDataPath(self.fw_file))
    self.log.info('flashing a new firmware %s:%s...' % (fw_version, fw_config))
    return utils.IsSuccessful(self.dut.Call(cmd_update))

  def ReadFirmwareVersion(self):
    """Read whether the firmware version and config are correct."""
    fw_version = None
    fw_config = None
    read_cmd = '%s -o /dev/hidraw0' % self._GetToolPath(self.hid_tool)
    for line in self.dut.CheckOutput(read_cmd).splitlines():
      if ':' in line:
        name, value = [elm.strip() for elm in line.split(':')]
        if name == 'Build ID':
          fw_version = value
        elif name == 'Config ID':
          fw_config = value
    return (fw_version, fw_config)

  def PostTest(self):
    """A method to invoke after conducting the test.

    Re-calibrate the baseline after the metal mesh is lifted up.
    """
    flag = self.CalibrateBaseline()
    self.log.info('Calibrate the baseline: %s' % str(flag))
    return flag


def GetSensorServiceClass(board):
  """Get the proper SensorService subclass for the specified board."""
  SENSORS_CLASS_DICT = {
      SAMUS: SensorServiceSamus,
      RYU: SensorServiceRyu,
      RUSH_RYU: SensorServiceRyu,
  }
  board_sensors = SENSORS_CLASS_DICT.get(board)
  if board_sensors:
    return board_sensors
  raise Error('Failed to get sensor service subclass for %s.' % board)


def RunXMLRPCSysfsServer(addr, board, log=logging):
  """A helper function to create and run the xmlrpc server to serve sensors
  data.
  """

  def _IsServerRunning():
    """Check if the server is running."""
    filename = os.path.basename(__file__)
    # Exclude the one with 'sudo python ....' which is only a shell.
    re_pattern = re.compile(r'(?<!sudo)\s+python.+' + filename)
    count = 0
    for line in utils.SimpleSystemOutput('ps aux').splitlines():
      result = re_pattern.search(line)
      if result:
        count += 1
    return count > 1

  _, port = addr
  if _IsServerRunning():
    print('XMLRPCServer(%s) has been already running....' % str(addr))
  else:
    if not utils.IsDestinationPortEnabled(port):
      utils.EnableDestinationPort(port)
      log.info('The destination port %d is enabled.' % port)

    server = SimpleXMLRPCServer.SimpleXMLRPCServer(addr)
    # Set allow_dotted_names=True since SensorService has an object,
    board_sensors = GetSensorServiceClass(board)
    # i.e. kernel_module, as its member. This flag helps register
    # the functions in kernel_module as well.
    server.register_instance(board_sensors(log), allow_dotted_names=True)
    print('XMLRPCServer(%s) serves sys fs data forever....' % str(addr))
    server.serve_forever()


def _ParseAddr(addr_str):
  """Parse the address string into (ip, port) pair."""
  result = re.search(r'(.+):(\d+)', addr_str)
  if not result:
    _Usage()
  ip = result.group(1)
  port = int(result.group(2))
  return (ip, port)


def _Usage():
  """Print the usage."""
  prog = sys.argv[0]
  print('Usage: ./%s ip:port board' % prog)
  print('E.g.:  ./%s 192.168.10.20:8000 ryu' % prog)
  print('       ./%s localhost:8000 samus' % prog)
  sys.exit(1)


if __name__ == '__main__':
  if len(sys.argv) != 3:
    _Usage()
  RunXMLRPCSysfsServer(_ParseAddr(sys.argv[1]), sys.argv[2])
