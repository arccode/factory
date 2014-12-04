#!/usr/bin/python

# -*- coding: utf-8 -*-

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
    self.delta_lower_bound = int(self.config.Read('TouchSensors',
                                                  'DELTA_LOWER_BOUND'))
    self.delta_higher_bound = int(self.config.Read('TouchSensors',
                                                   'DELTA_HIGHER_BOUND'))

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

  def _Verify(self, data, touched_cols):
    """Verify sensor data.

    Returns:
      True if the sensor data are legitimate.
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
    return super(SensorServiceSamus, self)._Verify(data, touched_cols)


class SensorServiceRyu(BaseSensorService):
  """Sensor services for Ryu.

  On Ryu, the sensor data are provided by a user-level program f54test.
  """
  TOOL = 'f54test'
  TOOL_REMOTE_DIR = '/tmp'
  READ_CMD = 'sudo %s -r ' % os.path.join(TOOL_REMOTE_DIR, TOOL)
  REPORT_TYPE = {'deltas': 2, 'refs': 3}

  def __init__(self, ip, log=None):
    super(SensorServiceRyu, self).__init__(RYU, log=log)
    self.ip = ip
    self.num_rows = None
    self.num_cols = None

    self.tool = os.path.join(os.path.dirname(__file__),
                             'boards', self.board, self.TOOL)
    if self.InstallTool():
      self.log.info('Sucessfully installed the tool: %s' % self.tool)
    else:
      self.log.error('Failed to install the tool: %s' % self.tool)
      self.log.error('Restart the test to try again!')

    if self.InstallDriver():
      self.log.info('Sucessfully installed the touchscreen driver.')
    else:
      self.log.error('Failed to install the touchscreen driver.')

  def _CheckTool(self):
    """Check if the tool exists in the remote machine."""
    cmd = 'ls %s/%s' % (self.TOOL_REMOTE_DIR, self.TOOL)
    return SshCommand(self.ip, cmd, output=False)

  def InstallTool(self):
    """Install f54test tool on the target machine.."""
    return (self._CheckTool() or
            ScpCommand(self.ip, self.tool, self.TOOL_REMOTE_DIR))

  def InstallDriver(self):
    cmd_check_driver_installed = 'lsmod | grep i2c_hid'
    cmd_install_driver = 'modprobe i2c_hid'
    return (SshCommand(self.ip, cmd_check_driver_installed, output=False) or
            SshCommand(self.ip, cmd_install_driver, output=False))

  def CheckStatus(self):
    """Checks whether it could read the sensor data or not.

    Returns:
      True if could read sensor deltas values.
    """
    return len(self.Read('deltas')) > 0

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
    read_cmd = self.READ_CMD + str(self.REPORT_TYPE[category])
    out_data = []
    for line in SshCommand(self.ip, read_cmd).splitlines():
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

  def Verify(self, data):
    """Verify sensor data.

    Returns:
      True if the sensor data are legitimate.
    """
    touched_cols = range(self.num_cols)
    return super(SensorServiceRyu, self)._Verify(data, touched_cols)


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
