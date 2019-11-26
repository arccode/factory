# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Fingerprint MCU utilities"""

from __future__ import print_function

import logging
import re


class FpmcuError(Exception):
  """Fpmcu device exception class."""
  pass


class FpmcuDevice(object):
  # Select the Fingerprint MCU cros_ec device
  CROS_FP_ARG = "--name=cros_fp"
  # Regular expression for parsing ectool output.
  RO_VERSION_RE = re.compile(r'^RO version:\s*(\S+)\s*$', re.MULTILINE)
  RW_VERSION_RE = re.compile(r'^RW version:\s*(\S+)\s*$', re.MULTILINE)
  FPINFO_MODEL_RE = re.compile(
      r'^Fingerprint sensor:\s+vendor.+model\s+(\S+)\s+version', re.MULTILINE)
  FPINFO_ERRORS_RE = re.compile(r'^Error flags:\s*(\S*)$', re.MULTILINE)

  def __init__(self, dut):
    self._dut = dut

  def FpmcuCommand(self, command, *args):
    """Execute a host command on the fingerprint MCU

    Args:
      command: the name of the ectool command.

    Returns:
      Command text output.
    """
    cmdline = ['ectool', self.CROS_FP_ARG, command] + list(args)
    result = self._dut.CheckOutput(cmdline)
    return result.strip() if result is not None else ''

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

  def GetSensorId(self):
    """Retrieve the sensor identifier

    Returns:
      An integer representing the sensor ID.
    """
    info = self.FpmcuCommand('fpinfo')
    match_model = self.FPINFO_MODEL_RE.search(info)
    if match_model is None:
      raise FpmcuError('Unable to retrieve Sensor info (%s)' % info)
    logging.info('ectool fpinfo:\n%s\n', info)
    model = int(match_model.group(1), 16)

    # Check error flags
    match_errors = self.FPINFO_ERRORS_RE.search(info)
    if match_errors is None:
      raise FpmcuError('Sensor error flags not found.')
    else:
      flags = match_errors.group(1)
      if flags != '':
        raise FpmcuError('Sensor failure: %s' % flags)

    return model
