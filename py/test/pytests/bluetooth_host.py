# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Station-based Bluetooth scan and pair test, using hciconfig and hcitool.

Make the host machine discoverable, scan for the host MAC address from the
DUT, and make the host non-discoverable.
"""

import collections
import os
import unittest

from cros.factory.device import device_types
from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.utils.arg_utils import Arg
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
          default=False),
      Arg('pre_command', str,
          'Command to be run before executing the test.  For example, this '
          'could be used to initialize Bluetooth module on the DUT.  '
          'Does not check output of the command.',
          default=None),
      Arg('post_command', str,
          'Command to be run after executing the test.  For example, this '
          'could be used to unload a Bluetooth module on the DUT.  '
          'Does not check output of the command.',
          default=None),
      Arg('host_hci_device', str,
          'The target hci device of the host station. Set to None to bind'
          'on all interfaces, or set to "hci0" to bind only on specified'
          'interfaces.',
          default=None),
      Arg('dut_hci_device', str,
          'The target hci device of the DUT.',
          default='hci0'),
      Arg('dut_hci_num_response', int,
          'Maximum number of inquiry responses for scanning.',
          default=None),
  ]

  HostDeviceType = collections.namedtuple(
      'HostDevice', ['interface', 'address'])

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.host = device_utils.CreateStationInterface()

    if self.args.host_hci_device is None:
      self.host_interfaces = self._GetHostInterfaces()
    else:
      self.host_interfaces = [self.args.host_hci_device]

    # The host device to be used for pairing test
    # This will be filled up after scan test is completed
    self.host_device_to_pair = None

  def tearDown(self):
    # Close host Bluetooth device.
    for host_interface in self.host_interfaces:
      self.host.Call(DISABLE_SCAN_CMD % host_interface)
      self.host.Call(DISABLE_DEVICE_CMD % host_interface)

    # Close DUT Bluetooth device.
    self.dut.Call(DISABLE_DEVICE_CMD % self.args.dut_hci_device)
    if self.args.post_command:
      self.RunCommand(self.args.post_command, 'post-command')

  def runTest(self):
    if self.dut.link.IsLocal():
      self.fail('This pytest can only be run at station-based style.')

    # Setup host Bluetooth device.
    for host_interface in self.host_interfaces:
      self.host.CheckCall(ENABLE_DEVICE_CMD % host_interface)
      self.host.CheckCall(ENABLE_SCAN_CMD % host_interface)

    # Setup DUT Bluetooth device
    if self.args.pre_command:
      self.RunCommand(self.args.pre_command, 'pre-command')
    self.dut.CheckCall(ENABLE_DEVICE_CMD % self.args.dut_hci_device)

    # Get addresses of host devices
    # Note: We can only get addresses after devices are enabled
    host_devices = self._GetHostDevicesInfo(self.host_interfaces)

    # DUT scans the host station.
    self.assertTrue(
        sync_utils.Retry(self.args.max_retry_times, 0, None,
                         lambda: self.ScanTask(host_devices)))

    if self.args.enable_pair:
      self.assertTrue(
          sync_utils.Retry(self.args.max_retry_times, 0, None,
                           self.PairTask))

  def ScanTask(self, host_devices):
    """Scans the Bluetooth devices and checks the host station is found."""
    scanned_macs = self.ScanDevicesFromDUT()
    session.console.info('DUT scan results: %s', scanned_macs)

    for dev in host_devices:
      if dev.address in scanned_macs:
        self.host_device_to_pair = dev
        session.console.info('DUT successfully scanned host device: ' +
                             str(dev))
        return True

    return False

  def PairTask(self):
    """Connects with the Bluetooth devices of the host station."""

    host_mac = self.host_device_to_pair.address
    CONNECT_CMD = 'hcitool cc --role=m %s' % host_mac
    DISCONNECT_CMD = 'hcitool dc %s' % host_mac
    CHECK_CONNECTION_CMD = 'hcitool con'

    self.dut.CheckCall(CONNECT_CMD)
    output = self.dut.CheckOutput(CHECK_CONNECTION_CMD).lower()
    session.console.info('DUT tried to connect by %s with output %s',
                         CONNECT_CMD, output)
    ret = host_mac in output
    if ret:
      self.dut.Call(DISCONNECT_CMD)
    return ret

  def RunCommand(self, cmd, cmd_name):
    """Logs and runs the command."""
    session.console.info('Running %s: %s', cmd_name, cmd)
    try:
      output = self.dut.CheckOutput(cmd)
    except device_types.CalledProcessError as e:
      session.console.info('Exit code: %d', e.returncode)
    else:
      session.console.info('Success. Output: %s', output)

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
    if self.args.dut_hci_num_response is not None:
      SCAN_COMMAND += ' --numrsp=%d' % self.args.dut_hci_num_response
    output = self.dut.CheckOutput(SCAN_COMMAND)
    lines = output.splitlines()[1:]  # Skip the first line "Scanning ...".
    return [line.split()[0].lower() for line in lines]

  def _GetHostInterfaces(self):
    # Three options can get all bluetooth devices on host:
    # 1. hciconfig
    # 2. hcitool dev
    #    Does NOT contains interfaces which are down
    #    For example: hciconfig hci0 down
    # 3. list files under /sys/class/bluetooth

    # Here we choose to use option (3), since
    # 1. Output of option (1) is hard to parse, and the format might
    #    get changed in a future image
    # 2. Option (2) does NOT contains interface which are 'down'
    #    For example, after 'hciconfig hci0 down', it vanished from
    #    the output of 'hcitool dev'

    interfaces = os.listdir('/sys/class/bluetooth')
    session.console.info(
        'Find bluetooth devices from /sys/class/bluetooth: ' +
        str(interfaces))
    return interfaces

  def _GetHostDevicesInfo(self, interfaces):
    """Gets the devices and BD addresses of the host devices."""

    # The output of the hcitool command:
    # Devices:
    # 	hci0	01:02:03:04:05:06
    # 	hci1	10:20:30:40:50:60
    HCITOOL_CMD = 'hcitool dev'

    # Skip the first line "Devices:".
    devices_lines = self.host.CheckOutput(HCITOOL_CMD).splitlines()[1:]

    host_devices = []
    for device_line in devices_lines:
      device = device_line.split()
      host_device = self.HostDeviceType(
          device[0].lower(),
          device[1].lower())

      if host_device.interface not in interfaces:
        continue

      session.console.info('Host interface: ' + str(host_device))
      host_devices.append(host_device)

    return host_devices
