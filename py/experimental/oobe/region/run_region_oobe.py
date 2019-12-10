#!/usr/bin/env python3
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import logging

from cros.factory.test.l10n.regions import REGIONS
from cros.factory.utils.debug_utils import SetupLogging
from cros.factory.utils.process_utils import Spawn


DESCRIPTION = """Re-runs OOBE on a remote device with the given region.

This tool is useful for manually testing how OOBE behaves with VPD
settings for various regions. It clears local state on the remote
device and sets VPD RO values. It should be used only for testing.

Region configurations (py/l10/regions.py) on *this* device, not the
remote device, are used. The remote device need not have factory
software installed.
"""


def main():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('--no-multi', dest='multi', action='store_false',
                      help='Use only a single region (needed before R35)')
  parser.add_argument('host', metavar='HOST', help='Host to ssh to')
  parser.add_argument('region', metavar='CODE', help='Region code to use')
  args = parser.parse_args()
  SetupLogging(level=logging.INFO)

  vpd_command_args = '-s region=%s' % (REGIONS[args.region].region_code)

  Spawn(['ssh', args.host,
         'set -x; '
         # Stop the UI
         'stop ui; '
         # Update the VPD
         'vpd %s; '
         'dump_vpd_log --force; '
         # Delete local state to re-run OOBE
         'rm -rf /home/chronos /home/user; '
         # Restart the UI
         'start ui' % vpd_command_args],
        log=True, check_call=True)


if __name__ == '__main__':
  main()
