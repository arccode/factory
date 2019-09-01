#!/usr/bin/env python2
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A handy API to flash netboot with VPD presered.

Usage:
  netboot_flasher = FlashNetboot(image_filename, on_output=Prompt)
  Prompt(netboot_flasher.WarningMessage())
  // Prompt to continue.
  netboot_flasher.Run()
  // Reboot.
"""

import argparse
from contextlib import nested
import glob
import logging
import shutil
import subprocess
import sys
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.utils.file_utils import UnopenedTemporaryFile
from cros.factory.utils.process_utils import Spawn


DEFAULT_NETBOOT_FIRMWARE_PATH = '/usr/local/factory/board/image.net.bin'


class FlashNetboot(object):
  """Flashs netboot firmware.

  Args:
    image_file_patttern: Netboot firmware image. Allows file pattern which
        matches exactly one file.
    on_output: Output callback. Default None: output to stdout.
  """

  def __init__(self, image_file_pattern, on_output=None):
    self._on_output = on_output
    self._fw_main = None
    self._ro_vpd = None
    self._rw_vpd = None
    self._image = None

    images = glob.glob(image_file_pattern)
    if not images:
      raise ValueError('Firmware image %s does not exist' % image_file_pattern)
    if len(images) > 1:
      raise ValueError('Multiple firmware images %s exist' % image_file_pattern)
    self._image = images[0]

  def Run(self):
    """Flashs netboot firmware."""
    with nested(UnopenedTemporaryFile(prefix='fw_main.'),
                UnopenedTemporaryFile(prefix='vpd.ro.'),
                UnopenedTemporaryFile(prefix='vpd.rw.')) as files:
      self._fw_main, self._ro_vpd, self._rw_vpd = files
      self._PreserveVPD()
      shutil.copyfile(self._image, self._fw_main)
      self._PackVPD()
      self._FlashFirmware()

  def WarningMessage(self):
    return (
        '\n'
        '\n'
        '*** You are about to flash netboot firmware on this machine with:\n'
        '***   %s\n'
        '***\n'
        '*** This process is unrecoverable and this machine WILL need to\n'
        '*** go through network installation again.\n'
        '***\n'
        '*** Once this process starts, aborting it or powering off the\n'
        '*** machine may leave the machine in an unknown state.\n'
        '***\n' % self._image)

  def _Flashrom(self, params):
    cmd = ['flashrom', '-p', 'host'] + params
    if self._on_output is None:
      Spawn(cmd, log=True, check_call=True)
    else:
      p = Spawn(cmd, log=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
      for line in iter(p.stdout.readline, ''):
        self._on_output(line)

  def _PreserveSection(self, fw_main_file, section_file, section_name):
    """Reads out a firmware section.

    Args:
      fw_main_file: The dummy file served as full firmware image to flashrom.
      section_file: The file where the firmware section is saved to.
      section_name: The name of the section to read out.
    """
    logging.info('Saving %s to %s', section_name, section_file)
    self._Flashrom(['-r', fw_main_file,
                    '-i', '%s:%s' % (section_name, section_file)])

  def _PreserveVPD(self):
    self._PreserveSection(self._fw_main, self._rw_vpd, 'RW_VPD')
    self._PreserveSection(self._fw_main, self._ro_vpd, 'RO_VPD')

  def _PackVPD(self):
    logging.info('Packing RO/RW VPD into %s', self._fw_main)
    Spawn(['futility', 'load_fmap', self._fw_main, 'RO_VPD:%s' % self._ro_vpd,
           'RW_VPD:%s' % self._rw_vpd], check_call=True)

  def _FlashFirmware(self):
    logging.info('Flashing firmware %s...', self._fw_main)
    self._Flashrom(['-w', self._fw_main])


def main():
  logging.basicConfig(level=logging.INFO)

  parser = argparse.ArgumentParser(
      description='Flash netboot firmware with VPD preserved.')
  parser.add_argument('--image', '-i', help='Netboot firmware image',
                      default=DEFAULT_NETBOOT_FIRMWARE_PATH,
                      required=False)
  parser.add_argument('--yes', '-y', action='store_true',
                      help="Don't ask for confirmation")
  parser.add_argument('--no-reboot', dest='reboot', default=True,
                      action='store_false', help="Don't reboot after flashrom")
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

  if args.reboot:
    sys.stdout.write('Rebooting.  See you on the other side!\n')
    Spawn(['reboot'], check_call=True)
    time.sleep(60)
    sys.exit('Unable to reboot.')  # Should never happen


if __name__ == '__main__':
  main()
