#!/usr/bin/env python3
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for gsutil module."""


import logging
import unittest
from unittest import mock

from cros.factory.tools import gsutil


# pylint: disable=line-too-long
FAKE_GS_LS_OUTPUT = (
    """gs://chromeos-releases/canary-channel/daisy-spring/4262.1.0/
gs://chromeos-releases/canary-channel/daisy-spring/4262.10.0/
gs://chromeos-releases/canary-channel/daisy-spring/4262.2.0/
gs://chromeos-releases/canary-channel/daisy-spring/5457.0.0/
gs://chromeos-releases/canary-channel/daisy-spring/5460.0.0/""").splitlines()

FAKE_GS_BUILDS_OUTPUT_FACTORY_BRANCH = (
    """gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/ChromeOS-R29-4262.140.0-daisy-spring.zip
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/ChromeOS-factory-R29-4262.140.0-daisy-spring.instructions
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/ChromeOS-factory-R29-4262.140.0-daisy-spring.instructions.json
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/ChromeOS-factory-R29-4262.140.0-daisy-spring.zip
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/ChromeOS-firmware-R29-4262.140.0-daisy-spring.instructions
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/ChromeOS-firmware-R29-4262.140.0-daisy-spring.instructions.json
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/ChromeOS-firmware-R29-4262.140.0-daisy-spring.tar.bz2
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/ChromeOS-recovery-R29-4262.140.0-daisy-spring.instructions
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/ChromeOS-recovery-R29-4262.140.0-daisy-spring.instructions.json
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/ChromeOS-recovery-R29-4262.140.0-daisy-spring.tar.xz
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/ChromeOS-test-R29-4262.140.0-daisy-spring.tar.xz
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/au-generator.zip
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos-hwqual-daisy_spring-R29-4262.140.0.tar.bz2
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos_4262.140.0_daisy-spring_factory_canary-channel_mp.bin
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos_4262.140.0_daisy-spring_factory_canary-channel_mp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos_4262.140.0_daisy-spring_factory_canary-channel_mp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos_4262.140.0_daisy-spring_firmware-spring.rw_canary-channel_mp.bin
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos_4262.140.0_daisy-spring_firmware-spring.rw_canary-channel_mp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos_4262.140.0_daisy-spring_firmware-spring.rw_canary-channel_mp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos_4262.140.0_daisy-spring_firmware-spring_canary-channel_mp.bin
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos_4262.140.0_daisy-spring_firmware-spring_canary-channel_mp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos_4262.140.0_daisy-spring_firmware-spring_canary-channel_mp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos_4262.140.0_daisy-spring_recovery_canary-channel_mp.bin
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos_4262.140.0_daisy-spring_recovery_canary-channel_mp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/chromeos_4262.140.0_daisy-spring_recovery_canary-channel_mp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/debug-daisy-spring.tgz"""
).splitlines()

FAKE_GS_BUILDS_OUTPUT_FIRMWARE_BRANCH = (
    """
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/ChromeOS-firmware-R27-3824.120.0-daisy-spring-spring-mp.instructions
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/ChromeOS-firmware-R27-3824.120.0-daisy-spring-spring-mp.instructions.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/ChromeOS-firmware-R27-3824.120.0-daisy-spring.instructions
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/ChromeOS-firmware-R27-3824.120.0-daisy-spring.instructions.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/ChromeOS-firmware-R27-3824.120.0-daisy-spring.tar.bz2
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-daisy.rw_canary-channel_mp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-daisy.rw_canary-channel_mp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-daisy.rw_canary-channel_mp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-daisy.rw_canary-channel_premp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-daisy.rw_canary-channel_premp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-daisy.rw_canary-channel_premp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-daisy_canary-channel_mp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-daisy_canary-channel_mp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-daisy_canary-channel_mp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-daisy_canary-channel_premp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-daisy_canary-channel_premp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-daisy_canary-channel_premp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-smdk5250.rw_canary-channel_mp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-smdk5250.rw_canary-channel_mp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-smdk5250.rw_canary-channel_mp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-smdk5250.rw_canary-channel_premp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-smdk5250.rw_canary-channel_premp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-smdk5250.rw_canary-channel_premp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-smdk5250_canary-channel_mp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-smdk5250_canary-channel_mp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-smdk5250_canary-channel_mp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-smdk5250_canary-channel_premp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-smdk5250_canary-channel_premp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-smdk5250_canary-channel_premp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-snow.rw_canary-channel_mp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-snow.rw_canary-channel_mp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-snow.rw_canary-channel_mp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-snow.rw_canary-channel_premp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-snow.rw_canary-channel_premp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-snow.rw_canary-channel_premp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-snow_canary-channel_mp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-snow_canary-channel_mp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-snow_canary-channel_mp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-snow_canary-channel_premp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-snow_canary-channel_premp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-snow_canary-channel_premp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-spring.rw_canary-channel_mp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-spring.rw_canary-channel_mp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-spring.rw_canary-channel_mp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-spring.rw_canary-channel_premp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-spring.rw_canary-channel_premp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-spring.rw_canary-channel_premp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-spring_canary-channel_mp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-spring_canary-channel_mp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-spring_canary-channel_mp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-spring_canary-channel_premp.bin
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-spring_canary-channel_premp.bin.json
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/chromeos_3824.120.0_daisy-spring_firmware-spring_canary-channel_premp.bin.md5
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/debug-daisy-spring.tgz"""
).splitlines()


class GsutilUnittest(unittest.TestCase):
  """Unit tests for gsutil module."""

  def setUp(self):
    self.gsutil = gsutil.GSUtil('daisy-spring')
    self.gs_url_pattern = self.gsutil.GetGSPrefix('canary')

  @mock.patch.object(gsutil.GSUtil, 'LS',
                     return_value=FAKE_GS_LS_OUTPUT)
  def testGetLatestBuildPath(self, mock_ls):
    self.assertEqual(
        'gs://chromeos-releases/canary-channel/daisy-spring/5460.0.0/',
        self.gsutil.GetLatestBuildPath('canary'))
    mock_ls.assert_called_with(self.gs_url_pattern)

    self.assertEqual(
        'gs://chromeos-releases/canary-channel/daisy-spring/4262.10.0/',
        self.gsutil.GetLatestBuildPath('canary', '4262'))
    mock_ls.assert_called_with(self.gs_url_pattern)

  @mock.patch.object(gsutil.GSUtil, 'LS',
                     return_value=FAKE_GS_BUILDS_OUTPUT_FACTORY_BRANCH)
  def testGetBinaryURI(self, mock_ls):
    gs_dir = 'gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/'

    self.assertEqual(
        gs_dir + 'ChromeOS-factory-R29-4262.140.0-daisy-spring.zip',
        self.gsutil.GetBinaryURI(gs_dir, self.gsutil.IMAGE_TYPES.factory))
    mock_ls.assert_called_with(gs_dir)

    self.assertEqual(
        gs_dir + 'ChromeOS-firmware-R29-4262.140.0-daisy-spring.tar.bz2',
        self.gsutil.GetBinaryURI(gs_dir, self.gsutil.IMAGE_TYPES.firmware))

    self.assertEqual(
        gs_dir + 'ChromeOS-recovery-R29-4262.140.0-daisy-spring.tar.xz',
        self.gsutil.GetBinaryURI(gs_dir, self.gsutil.IMAGE_TYPES.recovery))
    mock_ls.assert_called_with(gs_dir)

    self.assertEqual(
        gs_dir + 'chromeos_4262.140.0_daisy-spring_' +
        'factory_canary-channel_mp.bin',
        self.gsutil.GetBinaryURI(gs_dir, self.gsutil.IMAGE_TYPES.factory,
                                 key='mp'))
    mock_ls.assert_called_with(gs_dir)

    self.assertEqual(
        gs_dir + 'chromeos_4262.140.0_daisy-spring_' +
        'recovery_canary-channel_mp.bin',
        self.gsutil.GetBinaryURI(gs_dir, self.gsutil.IMAGE_TYPES.recovery,
                                 key='mp'))
    mock_ls.assert_called_with(gs_dir)

    self.assertEqual(
        gs_dir + 'ChromeOS-test-R29-4262.140.0-daisy-spring.tar.xz',
        self.gsutil.GetBinaryURI(gs_dir, self.gsutil.IMAGE_TYPES.test))
    mock_ls.assert_called_with(gs_dir)

  @mock.patch.object(gsutil.GSUtil, 'LS',
                     return_value=FAKE_GS_BUILDS_OUTPUT_FIRMWARE_BRANCH)
  def testGetBinaryURIForFirmware(self, mock_ls):
    gs_dir = 'gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/'

    self.assertEqual(
        gs_dir + 'chromeos_3824.120.0_daisy-spring_' +
        'firmware-spring_canary-channel_mp.bin',
        self.gsutil.GetBinaryURI(gs_dir, self.gsutil.IMAGE_TYPES.firmware,
                                 key='mp'))
    mock_ls.assert_called_with(gs_dir)

  def testParseURI(self):
    obj = self.gsutil.ParseURI(
        'gs://chromeos-releases/canary-channel/daisy-spring/3824.72.0/'
        'ChromeOS-firmware-R27-3824.72.0-daisy-spring.tar.bz2')
    self.assertEqual(
        ('canary', 'daisy_spring', '3824.72.0', 'firmware', None),
        (obj.channel, obj.board, obj.image_version, obj.image_type, obj.key))

    obj = self.gsutil.ParseURI(
        'gs://chromeos-releases/canary-channel/daisy-spring/4262.453.0/'
        'chromeos_4262.453.0_daisy-spring_factory_canary-channel_mp-v2.bin')
    self.assertEqual(
        ('canary', 'daisy_spring', '4262.453.0', 'factory', 'mp-v2'),
        (obj.channel, obj.board, obj.image_version, obj.image_type, obj.key))


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  unittest.main()
