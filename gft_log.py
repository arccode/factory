#!/usr/bin/env python
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

""" gft_log.py: Creates the log for factory process.

    Check device_details.py for the required elements to generate.
"""

import re
import sys

import device_details
import gft_common
from gft_common import WarningMsg, VerboseMsg, DebugMsg, ErrorMsg, ErrorDie


def ParseVPDOutput(vpd_output):
  """ Converts "a"="b"\n list into [(a, b)] """
  vpd_list = {}
  for line in vpd_output.splitlines():
    matched = re.match('"(.*)"="(.*)"$', line.strip())
    if not matched:
      ErrorDie("Invalid VPD output: %s" % line)
    (name, value) = (matched.group(1), matched.group(2))
    if name in vpd_list:
      ErrorDie("Duplicated VPD entry: %s" % name)
    vpd_list[name] = value
  return vpd_list


def CreateDeviceLog(probed_components, vpd_source=None, verbose=True):
  """ Creates logs for current device.
      Collects hwid, vpd, probed components, and attach a timestamp.

  PARAMS:
      vpd_source: Optional input image for VPD values (None for system)
  """

  if vpd_source:
    vpd_cmd = '-f %s' % vpd_source
  else:
    vpd_cmd = ''

  device_log = {}
  device_log['hwid'] = gft_common.SystemOutput("crossystem hwid").strip()
  device_log['ro_vpd'] = ParseVPDOutput(
      gft_common.SystemOutput("vpd -i RO_VPD -l %s" % vpd_cmd,
                              progress_messsage="Reading RO VPD",
                              show_progress=verbose).strip())
  device_log['rw_vpd'] = ParseVPDOutput(
      gft_common.SystemOutput("vpd -i RW_VPD -l %s" % vpd_cmd,
                              progress_messsage="Reading RW VPD",
                              show_progress=verbose).strip())
  device_log['probed_components'] = dict(
      [(key, repr(value)) for key, value in probed_components.items()])

  # TODO(hungte) log the result of dev_vboot_debug
  # TODO(hungte) log and verify if rootfs hash is correct
  # TODO(hungte) add /var/log/factory.log, if available

  # TODO(hungte) wp_status is helpful but not required for current logs
  #device_log['wp_status'] = (
  #    'main: %s\nec: %s' %
  #    (gft_common.SystemOutput('flashrom -p internal:bus=spi --wp-status'),
  #     gft_common.SystemOutput('flashrom -p internal:bus=lpc --wp-status')))

  device_log['device_timestamp'] = gft_common.SystemOutput("date --utc").strip()
  return device_log


if __name__ == "__main__":
  # only load the hardware detection if we're in console.
  import gft_hwcomp
  import glob

  db_files = []
  for arg in sys.argv[1:]:
    db_files = db_files + glob.glob(arg)
  if not db_files:
    print "Usage: %s compdb_pattern" % sys.argv[0]
    sys.exit(1)
  hwcomp = gft_hwcomp.HardwareComponents(verbose=True)
  hwcomp.initialize()
  best_match = None
  for db_file in db_files:
    print "Matching for %s..." % db_file
    (probed, failure) = hwcomp.match_current_system(db_file)
    if not failure:
      best_match = probed
      break
  if not best_match:
    best_match = probed
  print hwcomp.pformat(best_match)
  device_log = CreateDeviceLog(best_match)
  print hwcomp.pformat(device_log)
  invalid_message = device_details.ValidateDetails(device_log)
  if invalid_message:
    ErrorMsg("Invalid device log: %s" % invalid_message)
  print "Encoded data: "
  print device_details.EncodeDetailsStr(device_log)
