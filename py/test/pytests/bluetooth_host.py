# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Station-based Bluetooth scan and pair test, using hciconfig and hcitool.

Make the host machine discoverable, scan for the host MAC address from the
DUT, and make the host non-discoverable.
"""

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.device import component
from cros.factory.test.args import Arg
from cros.factory.test import factory
from cros.factory.utils import sync_utils


# HCI Commands. Need to fill the HCI device.
ENABLE_DEVICE_CMD = 'hciconfig %s up'
DISABLE_DEVICE_CMD = 'hciconfig %s down'
ENABLE_SCAN_CMD = 'hciconfig %s piscan'
DISABLE_SCAN_CMD = 'hciconfig %s noscan'

DEFAULT_RETRY_TIME = 3


class BluetoothScanTest(unittest.TestCase):

  ARGS = [
      Arg('max_retry_times', int,
          'The maximum number attempts to retry scanning or pairing before '
          'failure.',
          default=DEFAULT_RETRY_TIME),
      Arg('enable_pair', bool,
          'Set to True to enable pairing test.',
          optional=True, default=False),
      Arg('pre_command', str,
          'Command to be run before executing the test.  For example, this '
          'could be used to initialize Bluetooth module on the DUT.  '
          'Does not check output of the command.',
          optional=True, default=None),
      Arg('post_command', str,
          'Command to be run after executing the test.  For example, this '
          'could be used to unload a Bluetooth module on the DUT.  '
          'Does not check output of the command.',
          optional=True, default=None),
      Arg('host_hci_device', str,
          'The target hci device of the host station.',
          default='hci0'),
      Arg('dut_hci_device', str,
          'The target hci device of the DUT.',
          default='hci0'),
      ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.host = device_utils.CreateStationInterface()
    self.host_mac = None

  def tearDown(self):
    # Close host Bluetooth device.
    self.host.Call(DISABLE_SCAN_CMD % self.args.host_hci_device)
    self.host.Call(DISABLE_DEVICE_CMD % self.args.host_hci_device)
    # Close DUT Bluetooth device.
    self.dut.Call(DISABLE_DEVICE_CMD % self.args.dut_hci_device)
    if self.args.post_command:
      self.RunCommand(self.args.post_command, 'post-command')

  def runTest(self):
    if self.dut.link.IsLocal():
      self.fail('This pytest can only be run at station-based style.')
    # Setup host Bluetooth device.
    self.host.CheckCall(ENABLE_DEVICE_CMD % self.args.host_hci_device)
    self.host.CheckCall(ENABLE_SCAN_CMD % self.args.host_hci_device)
    self.host_mac = self.GetHostMAC()
    # Setup DUT Bluetooth device
    if self.args.pre_command:
      self.RunCommand(self.args.pre_command, 'pre-command')
    self.dut.CheckCall(ENABLE_DEVICE_CMD % self.args.dut_hci_device)

    # DUT scans the host station.
    self.assertTrue(
        sync_utils.Retry(self.args.max_retry_times, 0, None, self.ScanTask))
    if self.args.enable_pair:
      self.assertTrue(
          sync_utils.Retry(self.args.max_retry_times, 0, None, self.PairTask))

  def ScanTask(self):
    """Scans the Bluetooth devices and checks the host station is found."""
    scanned_macs = self.ScanDevicesFromDUT()
    factory.console.info('DUT scan results: %s', scanned_macs)
    return self.host_mac in scanned_macs

  def PairTask(self):
    """Connects with the Bluetooth devices of the host station."""
    CONNECT_CMD = 'hcitool cc --role=m %s' % self.host_mac
    DISCONNECT_CMD = 'hcitool dc %s' % self.host_mac
    CHECK_CONNECTION_CMD = 'hcitool con'

    self.dut.CheckCall(CONNECT_CMD)
    output = self.dut.CheckOutput(CHECK_CONNECTION_CMD).lower()
    factory.console.info('DUT connection: %s', output)
    ret = self.host_mac in output
    if ret:
      self.dut.Call(DISCONNECT_CMD)
    return ret

  def RunCommand(self, cmd, cmd_name):
    """Logs and runs the command."""
    factory.console.info('Running %s: %s', cmd_name, cmd)
    try:
      output = self.dut.CheckOutput(cmd)
    except component.CalledProcessError as e:
      factory.console.info('Exit code: %d', e.returncode)
    else:
      factory.console.info('Success. Output: %s', output)

  def ScanDevicesFromDUT(self):
    """Scans for nearby BT devices from the DUT.

    Returns:
      A list of MAC addresses.
    """
    # The output of the scan command:
    # Scanning ...
    #      01:02:03:04:05:06       Chromebook_0123
    #      01:02:03:04:05:07       Chromebook_4567
    SCAN_COMMAND = 'hcitool scan'
    output = self.dut.CheckOutput(SCAN_COMMAND)
    lines = output.splitlines()[1:]  # Skip the first line "Scanning ...".
    return [line.split()[0].lower() for line in lines]

  def GetHostMAC(self):
    """Gets the MAC address of the host station."""
    # Devices:
    # 	hci0	01:02:03:04:05:06
    host_mac = self.host.CheckOutput(
        'hcitool dev | grep hci0').split()[1].lower()
    factory.console.info('Host MAC: %s', host_mac)
    return host_mac
