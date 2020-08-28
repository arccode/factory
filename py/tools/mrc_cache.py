#!/usr/bin/env python3
#
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Read more details from go/dram-init-chromebook."""

import argparse
import logging

from cros.factory.device import device_utils
from cros.factory.utils.type_utils import Enum


ARCH = Enum(['x86', 'arm'])
MRC_CACHE_SECTIONS = (
    'RECOVERY_MRC_CACHE',  # For x86 recovery mode
    'RW_MRC_CACHE',  # For x86 normal mode
    'RW_DDR_TRAINING',  # For ARM (Mediatek)
    'RO_DDR_TRAINING',  # For ARM (Qualcomm)
)


def GetMRCSections(dut):
  with dut.temp.TempFile() as temp_file:
    dut.CheckCall('flashrom -p host -r %s -i FMAP' % temp_file, log=True)
    fmap_sections = dut.CheckOutput('dump_fmap -p %s' % temp_file, log=True)

  mrc_sections = []
  for section_info in fmap_sections.splitlines():
    section_name = section_info.split()[0]
    if section_name in MRC_CACHE_SECTIONS:
      mrc_sections.append(section_name)

  return mrc_sections


def EraseTrainingData(dut):
  mrc_sections = GetMRCSections(dut)
  if mrc_sections:
    cmd = ['flashrom', '-p', 'host', '-E']
    for section in mrc_sections:
      cmd += ['-i', section]
    dut.CheckCall(cmd, log=True)

  if 'RECOVERY_MRC_CACHE' in mrc_sections:
    # Set next boot to recovery mode to retrain RECOVERY_MRC_CACHE first.
    # And it'll reboot automatically and retrain RW_MRC_CACHE.
    dut.CheckCall('crossystem recovery_request=0xC4', log=True)


def VerifyTrainingData(dut):
  arch = dut.CheckOutput('crossystem arch').strip()
  # Currently we don't have a tool to verify training data on ARM platforms,
  # but the system should run memory test after DRAM calibration.
  if arch == ARCH.arm:
    return

  mrc_sections = GetMRCSections(dut)
  with dut.temp.TempFile() as temp_file:
    for section in mrc_sections:
      dut.CheckCall(
          'flashrom -p host -r /dev/null -i %s:%s' % (section, temp_file),
          log=True)
      dut.CheckCall('futility validate_rec_mrc %s' % temp_file, log=True)


def main():
  logging.basicConfig(level=logging.INFO)

  parser = argparse.ArgumentParser(
      description='MRC cache tool for memory training and verification.',
      formatter_class=argparse.RawDescriptionHelpFormatter)
  group = parser.add_mutually_exclusive_group()
  group.add_argument(
      '--erase',
      action='store_true',
      help='Erase old training data, you need to reboot to trigger retrain')
  group.add_argument(
      '--verify', action='store_true', help='Verify the training data')
  args = parser.parse_args()

  dut = device_utils.CreateDUTInterface()
  if args.erase:
    EraseTrainingData(dut)
  elif args.verify:
    VerifyTrainingData(dut)


if __name__ == '__main__':
  main()
