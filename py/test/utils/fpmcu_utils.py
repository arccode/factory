# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Fingerprint MCU utilities"""

import logging
import re
import subprocess


class FpmcuError(Exception):
  """Fpmcu device exception class."""


class FpmcuDevice:
  # Select the Fingerprint MCU cros_ec device
  CROS_FP_ARG = "--name=cros_fp"
  # Regular expression for parsing ectool output.
  RO_VERSION_RE = re.compile(r'^RO version:\s*(\S+)\s*$', re.MULTILINE)
  RW_VERSION_RE = re.compile(r'^RW version:\s*(\S+)\s*$', re.MULTILINE)
  FPINFO_MODEL_RE = re.compile(
      r'^Fingerprint sensor:\s+vendor.+model\s+(\S+)\s+version', re.MULTILINE)
  FPINFO_VENDOR_RE = re.compile(
      r'^Fingerprint sensor:\s+vendor\s+(\S+)\s+product', re.MULTILINE)
  FPINFO_ERRORS_RE = re.compile(r'^Error flags:\s*(\S*)$', re.MULTILINE)

  def __init__(self, dut):
    self._dut = dut

  def FpmcuCommand(self, command, *args, encoding='utf-8'):
    """Execute a host command on the fingerprint MCU

    Args:
      command: the name of the ectool command.

    Returns:
      Command text output.
    """
    cmdline = ['ectool', self.CROS_FP_ARG, command] + list(args)
    process = self._dut.Popen(
        cmdline, encoding=encoding,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if encoding is not None:
      stdout = stdout.strip()
    if process.returncode != 0:
      raise FpmcuError('cmd: %r, returncode: %d, stdout: %r, stderr: %r' % (
          cmdline, process.returncode, stdout, stderr.strip()))
    return stdout

  def GetFpmcuFirmwareVersion(self):
    """Get fingerprint MCU firmware version

    Returns:
      A tuple (ro_ver, rw_ver) for RO and RW frimware versions.
    """
    fw_version = self.FpmcuCommand("version")
    match_ro = self.RO_VERSION_RE.search(fw_version)
    match_rw = self.RW_VERSION_RE.search(fw_version)
    if match_ro is not None:
      match_ro = match_ro.group(1)
    if match_rw is not None:
      match_rw = match_rw.group(1)
    return match_ro, match_rw

  def GetFpSensorInfo(self):
    """Retrieve the fingerprint sensor identifiers

    Returns:
      An tuple (vendor_id, sensor_id) of two strings
      representing vendor ID and sensor ID.
    """
    info = self.FpmcuCommand('fpinfo')
    match_vendor = self.FPINFO_VENDOR_RE.search(info)
    match_model = self.FPINFO_MODEL_RE.search(info)

    if match_vendor is None or match_model is None:
      raise FpmcuError('Unable to retrieve Sensor info (%s)' % info)
    logging.info('ectool fpinfo:\n%s\n', info)

    # Check error flags
    match_errors = self.FPINFO_ERRORS_RE.search(info)
    if match_errors is None:
      raise FpmcuError('Sensor error flags not found.')

    flags = match_errors.group(1)
    if flags != '':
      raise FpmcuError('Sensor failure: %s' % flags)

    return (match_vendor.group(1), match_model.group(1))
