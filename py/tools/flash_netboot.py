#!/usr/bin/python -Bu
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import argparse
from contextlib import nested
import glob
import logging
import sys
import time

import factory_common  # pylint: disable=W0611
from cros.factory.utils.file_utils import UnopenedTemporaryFile
from cros.factory.utils.process_utils import Spawn


def PreserveSection(fw_main_file, section_file, section_name):
  """Reads out a firmware section.

  Args:
    fw_main_file: The dummy file served as full firmware image to flashrom.
    section_file: The file where the firmware section is saved to.
    section_name: The name of the section to read out.
  """
  logging.info('Saving %s to %s', section_name, section_file)
  Spawn(['flashrom', '-r', fw_main_file, '-i',
         '%s:%s' % (section_name, section_file)],
        log=True, check_call=True)


def RestoreSection(fw_main_file, section_file, section_name):
  """Writes a firmware section.

  Args:
    fw_main_file: The dummy file served as full firmware image to flashrom.
    section_file: The file containing the data to write.
    section_name: The name of the section to write.
  """
  logging.info('Restoring %s from %s', section_name, section_file)
  Spawn(['flashrom', '-w', fw_main_file, '-i',
         '%s:%s' % (section_name, section_file)],
        log=True, check_call=True)


def PreserveVPD(fw_main, ro_vpd, rw_vpd):
  PreserveSection(fw_main, rw_vpd, 'RW_VPD')
  PreserveSection(fw_main, ro_vpd, 'RO_VPD')


def RestoreVPD(fw_main, ro_vpd, rw_vpd):
  RestoreSection(fw_main, rw_vpd, 'RW_VPD')
  RestoreSection(fw_main, ro_vpd, 'RO_VPD')


def FlashFirmware(fw_image):
  logging.info('Flashing firmware %s...', fw_image)
  Spawn(['flashrom', '-w', fw_image], log=True, check_call=True)


def main():
  parser = argparse.ArgumentParser(
      description="Flash netboot firmware with VPD preserved.")
  parser.add_argument('--image', '-i', help='Netboot firmware image',
                      default='/usr/local/factory/board/nv_image*.bin',
                      required=False)
  parser.add_argument('--yes', '-y', action='store_true',
                      help="Don't ask for confirmation")
  args = parser.parse_args()

  images = glob.glob(args.image)
  if not images:
    parser.error('Firmware image %s does not exist' % args.image)
  if len(images) > 1:
    parser.error('Multiple firmware images %s exist' % images)
  image = images[0]

  logging.basicConfig(level=logging.INFO)

  sys.stdout.write(
      ('\n'
       '\n'
       '*** You are about to flash netboot firmware on this machine with:\n'
       '***   %s\n'
       '***\n'
       '*** This process is unrecoverable and this machine WILL need to\n'
       '*** go through network installation again.\n'
       '***\n'
       '*** Once this process starts, aborting it or powering off the\n'
       '*** machine may leave the machine in an unknown state.\n'
       '***\n') % image)

  if not args.yes:
    sys.stdout.write('*** Continue? [y/N] ')
    answer = sys.stdin.readline()
    if not answer or answer[0] not in 'yY':
      sys.exit('Aborting.')

  with nested(UnopenedTemporaryFile(prefix='fw_main.'),
              UnopenedTemporaryFile(prefix='vpd.ro.'),
              UnopenedTemporaryFile(prefix='vpd.rw.')) as files:
    PreserveVPD(*files)
    FlashFirmware(image)
    RestoreVPD(*files)

  sys.stdout.write('Rebooting.  See you on the other side!\n')
  Spawn(['reboot'], check_call=True)
  time.sleep(60)
  sys.exit('Unable to reboot.')  # Should never happen

if __name__ == '__main__':
  main()
