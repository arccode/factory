# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import contextlib
import logging
import re
import subprocess

from cros.factory.hwid_extractor import ap_firmware
from cros.factory.hwid_extractor import cr50
from cros.factory.hwid_extractor import rlz
from cros.factory.hwid_extractor import servod

# SuzyQ usb device id.
CR50_USB = '18d1:5014'
CR50_LSUSB_CMD = ['lsusb', '-vd', CR50_USB]
CR50_LSUSB_SERIAL_RE = r'iSerial +\d+ (\S+)\s'

RLZ_DATA = rlz.RLZData()


def _ScanCCDDevices():
  """Use `lsusb` to get iSerial attribute of CCD devices.

  Returns:
    Serial name of the first found CCD device, in uppercase.
  """
  logging.info('Scan serial names of CCD devices')
  try:
    output = subprocess.check_output(CR50_LSUSB_CMD, encoding='utf-8')
  except subprocess.CalledProcessError:
    return None
  serials = re.findall(CR50_LSUSB_SERIAL_RE, output)
  if not serials:
    # iSerial should be listed in the output. If not, the user may not have
    # permission to get iSerial.
    raise RuntimeError(
        'Cannot get CCD serial number. Maybe running with sudo ?')
  if len(serials) > 1:
    raise RuntimeError('Working with multiple devices is not supported.')
  logging.info('Serial name of CCD devices: %s', serials)
  return serials[0].upper()


@contextlib.contextmanager
def _GetCr50FromServod(*args, **kargs):
  """Start Servod and return a Cr50 interface.

  Each time Servod stops, the ccd devices `/dev/ttyUSB*` won't show up unless
  users replug the SuzyQ cable. Run Servod and get the uart device through
  dut-control make things simpler.

  Returns:
    A Cr50 interface.
  """
  with servod.Servod(*args, **kargs) as dut_control:
    cr50_pty = dut_control.GetValue('cr50_uart_pty')
    # Disable the timestamp to make output of the console cleaner.
    dut_control.Run(['cr50_uart_timestamp:off'])
    yield cr50.Cr50(cr50_pty)


def Scan():
  """Scan and read the status of a device.

  Returns:
    A Dict contains the device status.
  Raises:
    RuntimeError if no device was found, or there are multiple devices connected
    to the host.
  """
  cr50_serial_name = _ScanCCDDevices()
  if not cr50_serial_name:
    raise RuntimeError('No device was found.')
  with _GetCr50FromServod(serial_name=cr50_serial_name) as dut_cr50:
    rlz_code = dut_cr50.GetRLZ()
    is_testlab_enabled = dut_cr50.GetTestlabState() == cr50.TestlabState.ENABLED
    if is_testlab_enabled:
      # Force CCD to be opened. This make sure that if testlab is enabled, the
      # CCD is always non-restricted.
      is_restricted = dut_cr50.ForceOpen()
    else:
      is_restricted = dut_cr50.IsRestricted()
    return {
        'cr50SerialName': cr50_serial_name,
        'rlz': rlz_code,
        'referenceBoard': RLZ_DATA.Get(rlz_code),
        'challenge': dut_cr50.GetChallenge() if is_restricted else None,
        'isRestricted': is_restricted,
        'isTestlabEnabled': is_testlab_enabled,
    }


def ExtractHWIDAndSerialNumber(cr50_serial_name, board):
  """Extract info from device.

  Args:
    cr50_serial_name: The serial name of the cr50 usb device.
    board: The name of board of the device.
  Returns:
    hwid, serial_number. The value may be None.
  """
  with servod.Servod(serial_name=cr50_serial_name, board=board) as dut_control:
    return ap_firmware.ExtractHWIDAndSerialNumber(board, dut_control)


def Unlock(cr50_serial_name, authcode):
  """Unlock the device.

  Args:
    cr50_serial_name: The serial name of the cr50 usb device.
    authcode: The authcode to unlock the device.
  Returns:
    True if unlock successfully.
  """
  with _GetCr50FromServod(serial_name=cr50_serial_name) as dut_cr50:
    return dut_cr50.Unlock(authcode)


def Lock(cr50_serial_name):
  """Lock the device.

  Args:
    cr50_serial_name: The serial name of the cr50 usb device.
  Returns:
    True if lock successfully.
  """
  with _GetCr50FromServod(serial_name=cr50_serial_name) as dut_cr50:
    return dut_cr50.Lock()


def EnableTestlab(cr50_serial_name):
  """Enable testlab.

  Args:
    cr50_serial_name: The serial name of the cr50 usb device.
  Returns:
    True if enable successfully.
  """
  with _GetCr50FromServod(serial_name=cr50_serial_name) as dut_cr50:
    return dut_cr50.EnableTestlab()


def DisableTestlab(cr50_serial_name):
  """Disable testlab.

  Args:
    cr50_serial_name: The serial name of the cr50 usb device.
  Returns:
    True if disable successfully.
  """
  with _GetCr50FromServod(serial_name=cr50_serial_name) as dut_cr50:
    return dut_cr50.DisableTestlab()
