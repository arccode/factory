# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Device detail reports for factory process."""


import os
import tempfile
import time
import uuid

import crosfw
from common import Shell, YamlWrite


# Update this if any field names (or formats) have been changed.
REPORT_VERSION = 6


def Create(log_path):
  """Creates a detail report for current device.

  Collects hwid, vpd, and attach a timestamp.

  Args:
    log_path: Filename of log to include in the report.

  Returns:
    The created report filename.
  """
  report = {}

  # TODO(tammo): Consider adding /var/log/messages* and /etc/lsb-release.

  # TODO(hungte) we may also add in future:
  #   rootfs hash, dump_kernel_config, lsb-release from release image,
  #   gooftool version, result of dev_vboot_debug,
  #   /var/log/factory.log and any other customized data

  # General information
  report['version'] = '%s' % REPORT_VERSION

  # System Hardware ID
  report['hwid'] = Shell('crossystem hwid').stdout.strip()
  report['platform_name'] = Shell('mosys platform name').stdout.strip()

  # crossystem reports many system configuration data
  report['crossystem'] = Shell('crossystem').stdout.strip().splitlines()

  # Vital Product Data
  main_fw_file = crosfw.LoadMainFirmware().GetFileName()
  vpd_cmd = '-f %s' % main_fw_file
  report['ro_vpd'] = Shell('vpd -i RO_VPD -l %s' % vpd_cmd).stdout.splitlines()
  report['rw_vpd'] = Shell('vpd -i RW_VPD -l %s' % vpd_cmd).stdout.splitlines()

  # Firmware write protection status
  # TODO(hungte) Replace by crosfw.Flashrom.
  ec_wp_status = Shell(
      'flashrom -p internal:bus=lpc --get-size 2>/dev/null && '
      'flashrom -p internal:bus=lpc --wp-status || '
      'echo "EC is not available."').stdout
  bios_wp_status = Shell(
      'flashrom -p internal:bus=spi --wp-status').stdout

  wp_status_message = 'main: %s\nec: %s' % (bios_wp_status, ec_wp_status)
  report['wp_status'] = wp_status_message.splitlines()

  # Cellular status
  modem_status = Shell('modem status').stdout
  report['modem_status'] = modem_status.splitlines()

  # Verbose log. Should be prepared before the last step.
  if log_path is not None:
    report['verbose_log'] = open(log_path).read().splitlines()

  # Finally, attach a timestamp. This must be the last entry.
  report['device_timestamp'] = time.strftime('%Y%m%d-%H%M%S', time.gmtime())

  filename = os.path.join(tempfile.gettempdir(), uuid.uuid4().hex)
  open(filename, 'w').write(YamlWrite(report))
  return filename
