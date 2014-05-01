#!/bin/env python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for create_bundle module."""


import mock
import os
import shutil
import tempfile
import unittest

import factory_common   # pylint: disable=W0611
from cros.factory.factory_flow import create_bundle
from cros.factory.tools import build_board
from cros.factory.umpire.common import LoadBundleManifest


TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')

# pylint: disable=C0301
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
gs://chromeos-releases/canary-channel/daisy-spring/4262.140.0/debug-daisy-spring.tgz""")

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
gs://chromeos-releases/canary-channel/daisy-spring/3824.120.0/debug-daisy-spring.tgz""")


class CreateBundleUnittest(unittest.TestCase):
  """Unit tests for create_bundle module."""
  # pylint: disable=C0322, W0212

  def setUp(self):
    self.test_manifest = LoadBundleManifest(os.path.join(TEST_DATA_PATH,
                                                         'MANIFEST_test.yaml'))
    self.output_dir = tempfile.mkdtemp(prefix='create_bundle.')
    self.create_bundle = create_bundle.CreateBundle()
    self.create_bundle.options = type(
        'Namespace', (object,),
        {'board': build_board.BuildBoard('spring'),
         'output_dir': self.output_dir})
    self.create_bundle.Init()

  def tearDown(self):
    shutil.rmtree(self.output_dir)

  def testParseImageVersionToURLFromManifest(self):
    self.assertEquals(
        ('gs://chromeos-releases/canary-channel/daisy-spring/4131.73.0/'
         'chromeos_4131.73.0_daisy-spring_factory_canary-channel_premp.bin'),
        self.create_bundle._ParseImageVersionToURL(
            'factory_shim', 'from_manifest', manifest=self.test_manifest))

    self.assertEquals(
        ('gs://chromeos-releases/beta-channel/daisy-spring/4100.20.0/'
         'chromeos_4100.20.0_daisy-spring_recovery_beta-channel_premp.bin'),
        self.create_bundle._ParseImageVersionToURL(
            'release', 'from_manifest', manifest=self.test_manifest))

    self.assertEquals(
        ('gs://chromeos-releases/canary-channel/daisy-spring/3824.42.0/'
         'ChromeOS-firmware-R27-3824.42.0-daisy-spring.tar.bz2'),
        self.create_bundle._ParseImageVersionToURL(
            'netboot_firmware', 'from_manifest', manifest=self.test_manifest))

    self.assertEquals(
        ('gs://chromeos-releases/canary-channel/daisy-spring/4131.73.0/'
         'ChromeOS-factory-R29-4131.73.0-daisy-spring.zip'),
        self.create_bundle._ParseImageVersionToURL(
            'netboot_shim', 'from_manifest', manifest=self.test_manifest))

  def testParseImageVersionToURLFromVersionString(self):
    self.create_bundle._GetImageURL = mock.Mock()

    self.create_bundle._ParseImageVersionToURL('test', 'stablest')
    self.create_bundle._GetImageURL.assert_called_with('test')

    self.assertRaisesRegexp(
        create_bundle.CreateBundleError, r"Invalid version arg 'foo'",
        self.create_bundle._ParseImageVersionToURL, 'test', 'foo')

    self.create_bundle._ParseImageVersionToURL('test', 'canary')
    self.create_bundle._GetImageURL.assert_called_with(
        'test', channel='canary', version=None)

    self.create_bundle._ParseImageVersionToURL('test', 'canary/')
    self.create_bundle._GetImageURL.assert_called_with(
        'test', channel='canary', version=None)

    self.create_bundle._ParseImageVersionToURL('test', 'canary/1234')
    self.create_bundle._GetImageURL.assert_called_with(
        'test', channel='canary', version='1234')

    self.create_bundle._ParseImageVersionToURL('test', 'canary/1234.5')
    self.create_bundle._GetImageURL.assert_called_with(
        'test', channel='canary', version='1234.5')

    self.create_bundle._ParseImageVersionToURL('test', 'canary/1234.5.6')
    self.create_bundle._GetImageURL.assert_called_with(
        'test', channel='canary', version='1234.5.6')

    self.create_bundle._ParseImageVersionToURL('test', '1234')
    self.create_bundle._GetImageURL.assert_called_with(
        'test', channel=None, version='1234')

    self.create_bundle._ParseImageVersionToURL('test', '1234.5')
    self.create_bundle._GetImageURL.assert_called_with(
        'test', channel=None, version='1234.5')

    self.create_bundle._ParseImageVersionToURL('test', '1234.5.6')
    self.create_bundle._GetImageURL.assert_called_with(
        'test', channel=None, version='1234.5.6')


if __name__ == '__main__':
  unittest.main()
