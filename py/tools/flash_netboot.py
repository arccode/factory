#!/usr/bin/python -Bu
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A tool to flash netboot firmware."""

import argparse
import logging
import sys
import time

import factory_common  # pylint: disable=W0611
from cros.factory.system.flash_netboot import FlashNetboot
from cros.factory.utils.process_utils import Spawn


def main():
  logging.basicConfig(level=logging.INFO)

  parser = argparse.ArgumentParser(
      description="Flash netboot firmware with VPD preserved.")
  parser.add_argument('--image', '-i', help='Netboot firmware image',
                      default='/usr/local/factory/board/image.net.bin',
                      required=False)
  parser.add_argument('--yes', '-y', action='store_true',
                      help="Don't ask for confirmation")
  args = parser.parse_args()

  try:
    netboot_flasher = FlashNetboot(args.image)
  except ValueError as e:
    parser.error(e.message)

  sys.stdout.write(netboot_flasher.WarningMessage())

  if not args.yes:
    sys.stdout.write('*** Continue? [y/N] ')
    answer = sys.stdin.readline()
    if not answer or answer[0] not in 'yY':
      sys.exit('Aborting.')

  netboot_flasher.Run()

  sys.stdout.write('Rebooting.  See you on the other side!\n')
  Spawn(['reboot'], check_call=True)
  time.sleep(60)
  sys.exit('Unable to reboot.')  # Should never happen


if __name__ == '__main__':
  main()
