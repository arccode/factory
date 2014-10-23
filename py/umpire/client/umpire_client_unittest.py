#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for UmpireClient."""


import logging
import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory import system
from cros.factory.tools import build_board
from cros.factory.umpire.client.umpire_client import UmpireClientInfo

class MockBuildBoard(object):
  """Mocked BuildBoard which always return 'test' as full_name."""
  full_name = 'test'


mock_build_board = MockBuildBoard()


class MockSystemInfo(object):
  """Mocked SystemInfo class."""
  def __init__(self, serial_number, mlb_serial_number, firmware_version,
               ec_version, pd_version, stage, eth_macs, wlan0_mac,
               factory_image_version, release_image_version,
               hwid_database_version, factory_md5sum):
    self.serial_number = serial_number
    self.mlb_serial_number = mlb_serial_number
    self.firmware_version = firmware_version
    self.ec_version = ec_version
    self.pd_version = pd_version
    self.stage = stage
    self.eth_macs = eth_macs
    self.wlan0_mac = wlan0_mac
    self.factory_image_version = factory_image_version
    self.release_image_version = release_image_version
    self.hwid_database_version = hwid_database_version
    self.factory_md5sum = factory_md5sum

mock_system_info_1 = MockSystemInfo(
    serial_number='DEV001',
    mlb_serial_number='MLB001',
    firmware_version='fw_001',
    ec_version='ec_001',
    pd_version='pd_001',
    stage='SMT',
    eth_macs={'eth0': 'EE:EE:EE:EE:EE:00', 'eth1': 'EE:EE:EE:EE:EE:01'},
    wlan0_mac='FF:FF:FF:FF:FF:00',
    factory_image_version='factory_001',
    release_image_version='release_001',
    hwid_database_version='hwid_001',
    factory_md5sum='md5_001')

# Uses a different serial_number than mock_system_info_1.
mock_system_info_2 = MockSystemInfo(
    serial_number='DEV002',
    mlb_serial_number='MLB001',
    firmware_version='fw_001',
    ec_version='ec_001',
    pd_version='pd_001',
    stage='SMT',
    eth_macs={'eth0': 'EE:EE:EE:EE:EE:00', 'eth1': 'EE:EE:EE:EE:EE:01'},
    wlan0_mac='FF:FF:FF:FF:FF:00',
    factory_image_version='factory_001',
    release_image_version='release_001',
    hwid_database_version='hwid_001',
    factory_md5sum='md5_001')

# Uses a different eth0 MAC address than mock_system_info_2.
mock_system_info_3 = MockSystemInfo(
    serial_number='DEV002',
    mlb_serial_number='MLB001',
    firmware_version='fw_001',
    ec_version='ec_001',
    pd_version='pd_001',
    stage='SMT',
    eth_macs={'eth0': 'EE:EE:EE:EE:EE:02', 'eth1': 'EE:EE:EE:EE:EE:01'},
    wlan0_mac='FF:FF:FF:FF:FF:00',
    factory_image_version='factory_001',
    release_image_version='release_001',
    hwid_database_version='hwid_001',
    factory_md5sum='md5_001')

# Uses a different factory_image than mock_system_info_3.
mock_system_info_4 = MockSystemInfo(
    serial_number='DEV002',
    mlb_serial_number='MLB001',
    firmware_version='fw_001',
    ec_version='ec_001',
    pd_version='pd_001',
    stage='SMT',
    eth_macs={'eth0': 'EE:EE:EE:EE:EE:02', 'eth1': 'EE:EE:EE:EE:EE:01'},
    wlan0_mac='FF:FF:FF:FF:FF:00',
    factory_image_version='factory_002',
    release_image_version='release_001',
    hwid_database_version='hwid_001',
    factory_md5sum='md5_001')


# The output string of X-Umpire-DUT for mock_system_info_1.
# Note that the keys are sorted.
OUTPUT_X_UMPIRE_DUT = (
    'board=test; ec=ec_001; firmware=fw_001; '
    'mac.eth0=EE:EE:EE:EE:EE:00; mac.eth1=EE:EE:EE:EE:EE:01; '
    'mac.wlan0=FF:FF:FF:FF:FF:00; mlb_sn=MLB001; pd=pd_001; sn=DEV001; stage=SMT')


# The return value of GetDUTInfoComponents.
OUTPUT_GET_UPDATE_DUT_INFO = {
    'x_umpire_dut': {
        'sn': 'DEV001',
        'mlb_sn': 'MLB001',
        'board': 'test',
        'firmware': 'fw_001',
        'ec': 'ec_001',
        'pd': 'pd_001',
        'mac.eth0': 'EE:EE:EE:EE:EE:00',
        'mac.eth1': 'EE:EE:EE:EE:EE:01',
        'mac.wlan0': 'FF:FF:FF:FF:FF:00',
        'stage': 'SMT'},
    'components': {
        'rootfs_test': 'factory_001',
        'rootfs_release': 'release_001',
        'firmware_ec': 'ec_001',
        'firmware_bios': 'fw_001',
        'firmware_pd': 'pd_001',
        'hwid': 'hwid_001',
        'device_factory_toolkit': 'md5_001'}}


class UmpireClientInfoTest(unittest.TestCase):
  """Tests UmpireClient"""
  def setUp(self):
    """Setups mox and mock umpire_client_info used in tests."""
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(system, 'SystemInfo')
    self.mox.StubOutWithMock(build_board, 'BuildBoard')
    # pylint: disable=E1101
    build_board.BuildBoard().MultipleTimes().AndReturn(
        mock_build_board)

  def tearDown(self):
    """Clean up for each test."""
    self.mox.UnsetStubs()

  def testGetXUmpireDUT(self):
    """Inits an UmpireClientInfo and checks GetXUmpireDUT."""
    system.SystemInfo().AndReturn(
        mock_system_info_1)

    self.mox.ReplayAll()

    client_info = UmpireClientInfo()
    output_x_umpire_dut = client_info.GetXUmpireDUT()
    self.assertEqual(
        output_x_umpire_dut, OUTPUT_X_UMPIRE_DUT)

    self.mox.VerifyAll()
    logging.debug('Done')

  def testGetDUTInfoComponents(self):
    """Inits an UmpireClientInfo and checks GetDUTInfoComponents."""
    system.SystemInfo().AndReturn(
        mock_system_info_1)
    system.SystemInfo().AndReturn(
        mock_system_info_1)

    self.mox.ReplayAll()

    client_info = UmpireClientInfo()
    output_get_update_dut_info = client_info.GetDUTInfoComponents()
    self.assertEqual(
        output_get_update_dut_info, OUTPUT_GET_UPDATE_DUT_INFO)

    self.mox.VerifyAll()
    logging.debug('Done')

  def testUpdate(self):
    """Inits an UmpireClientInfo and checks Update."""
    system.SystemInfo().AndReturn(
        mock_system_info_1)
    # There is update.
    system.SystemInfo().AndReturn(
        mock_system_info_2)
    # There is no update.
    system.SystemInfo().AndReturn(
        mock_system_info_2)
    # There is update.
    system.SystemInfo().AndReturn(
        mock_system_info_3)
    # There is update in system info, but not for X-Umpire-DUT.
    system.SystemInfo().AndReturn(
        mock_system_info_4)

    self.mox.ReplayAll()
    client_info = UmpireClientInfo()
    self.assertEqual(client_info.Update(), True)
    self.assertEqual(client_info.Update(), False)
    self.assertEqual(client_info.Update(), True)
    self.assertEqual(client_info.Update(), False)

    self.mox.VerifyAll()
    logging.debug('Done')

if __name__ == '__main__':
  logging.basicConfig(
      format='%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s',
      level=logging.DEBUG)
  unittest.main()
