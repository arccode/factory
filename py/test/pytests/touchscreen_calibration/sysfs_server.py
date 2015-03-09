#!/usr/bin/python

# -*- coding: utf-8 -*-

# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
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
import sys
import time
import SimpleXMLRPCServer

import touchscreen_calibration_utils as utils


class Error(Exception):
  pass


class SysfsConfig(object):
  """Manage the sys fs config data."""
  SYSFS_CONFIG = 'sysfs.conf'

  def __init__(self):
    config_filepath = os.path.join(os.path.dirname(__file__), self.SYSFS_CONFIG)
    self.parser = ConfigParser.ConfigParser()
    try:
      with open(config_filepath) as f:
        self.parser.readfp(f)
    except Exception:
      raise Error('Failed to read sysfs config file: %s.' % config_filepath)

  def Read(self, section, option):
    """Read config data."""
    if (self.parser.has_section(section) and
        self.parser.has_option(section, option)):
      return self.parser.get(section, option)
    return None

  def GetItems(self, section):
    """Get section items."""
    return self.parser.items(section)


class Sysfs(object):
  """Communicates with the touchscreen on system."""

  def __init__(self, log=None):
    self.log = log
    self.config = SysfsConfig()
    self.num_rows = int(self.config.Read('TouchSensors', 'NUM_ROWS'))
    self.num_cols = int(self.config.Read('TouchSensors', 'NUM_COLS'))
    kernel_module_name = self.config.Read('Misc', 'kernel_module_name')
    self.kernel_module = utils.KernelModule(kernel_module_name)

    # Get sys/debug fs data (1) from sysfs.conf, or (2) parsing sys fs.
    self.sysfs_entry = self.config.Read('Sysfs', 'sysfs_entry')
    if self.sysfs_entry is None:
      self.sysfs_entry = utils.GetSysfsEntry()
    self.debugfs = self.config.Read('Sysfs', 'debugfs')
    if self.debugfs is None:
      self.debugfs = utils.GetDebugfs()

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
      if not self.WriteSysfs(command):
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


def RunXMLRPCSysfsServer(addr, log=logging):
  """A helper function to create and run the xmlrpc server to serve sysfs data.
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
    # Set allow_dotted_names=True since Sysfs has an object,
    # i.e. kernel_module, as its member. This flag helps register
    # the functions in kernel_module as well.
    server.register_instance(Sysfs(log), allow_dotted_names=True)
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
  print('Usage: ./%s ip:port' % prog)
  print('E.g.:  ./%s 192.168.10.20:8000' % prog)
  print('       ./%s localhost:8000' % prog)
  sys.exit(1)


if __name__ == '__main__':
  if len(sys.argv) != 2:
    _Usage()
  RunXMLRPCSysfsServer(_ParseAddr(sys.argv[1]))
