# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import logging
import re
import serial
import time
import xmlrpclib

import factory_common  # pylint: disable=W0611

from cros.factory.test.fixture import bft_fixture
from cros.factory.test import serial_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils.type_utils import Enum

_RE_INA_VOLTAGE = re.compile(r'^\s*Bus voltage\s+:\s+\w+\s+=>\s+(-?\d+)\s+mV',
                             re.MULTILINE)
_RE_INA_CURRENT = re.compile(r'^\s*Current\s+:\s+\w+\s+=>\s+(-?\d+)\s+mA',
                             re.MULTILINE)
_RE_I2C_READ = re.compile(r'^\s*0x\w\w \[(\d+)\]', re.MULTILINE)


def _ChangeBit(byte, offset, bit_value):
  """Changes a bit of given offset.

  Args:
    byte: Input byte value in integer. Should be 0 ~ 255.
    offset: Bit offset needed to change.
    bit_value: Changed bit value. Should be 0 or 1.

  Returns:
    Modified byte value in integer.
  """
  if bit_value:
    return byte | (1 << offset)
  else:
    return byte & ~(1 << offset)


class DolphinBFTFixture(bft_fixture.BFTFixture):
  """Control interfaces of Plankton for Dolphin BFT fixture.

  It controls Plankton-Raiden boards by serial connection to test DUT Raiden
  ports. The testing ports (1 Raiden + 1 USB Type-A) will be paired to proceed
  Raiden testing sequence.
  """
  # pylint: disable=W0223
  # There are methods of abstract in class 'BFTFixture' but is not overridden.

  # Devices on Plankton-Raiden to be engaged/disengaged.
  Device = Enum(
      ['CHARGE_5V', 'CHARGE_12V', 'CHARGE_20V',
       'USB2', 'USB3', 'DP', 'ADB_HOST', 'DEFAULT'])

  # dev means charge-to-device.
  DEVICE_COMMAND = {
      Device.CHARGE_5V  : ['5v'],
      Device.CHARGE_12V : ['12v'],
      Device.CHARGE_20V : ['20v'],
      # Set dp/usb mux to dp to block usb 3.0 signal and remain only usb 2.0
      Device.USB2       : ['dp', 'dev'],
      Device.USB3       : ['usb', 'dev'],
      Device.DP         : ['dp', 'dev'],
      # For ADB target device, provide power to target device as engaging host
      # connection.
      Device.ADB_HOST   : ['5v'],
      # DEFAULT status: USB3.0/DP unplugged
      # 5v: set charge-to-device off (USB3.0 unplugged)
      # usb: set USB3.0/DP switch to usb (DP unplugged)
      Device.DEFAULT    : ['5v', 'usb']}

  _LIST_CHARGE = [Device.CHARGE_5V, Device.CHARGE_12V, Device.CHARGE_20V]
  _LIST_USB = [Device.USB2, Device.USB3]

  _WAIT_USB3_NEGOTIATE_SECS = 1  # Waits for USB3 signal negotiation.

  # The devices IO-expander I2C addresses refer to are not in DUT.
  # _I2C_ADDR_MINI is for Dolphin Mini configuration which is reachable by USB
  #   serial.
  # _I2C_ADDR_LEFT and _I2C_ADDR_RIGHT are for Dolphin Whale configuration which
  #   are reachable by serial over XMLRPC proxy.
  _I2C_ADDR_MINI = '0x40'
  _I2C_ADDR_LEFT = '0x42'
  _I2C_ADDR_RIGHT = '0x4e'


  def __init__(self):
    super(DolphinBFTFixture, self).__init__()
    # Plankton-raiden information. Obtained from Init()
    self._plankton_conn = None
    self._i2c_address = None
    self._use_proxy = False
    self._raiden_index = None

  def Init(self, **port_params):
    """Initializes Dolphin fixture connection.

    It pairs under-testing raiden path to USB Type-A serial control.

    Args:
      **port_params: parameters for Plankton-Raiden connection.
          1. Dolphin(Whale) parameters:
          required fields:
          - dolphin_host: Name or IP address of dolphin server host.
          - dolphin_port: TCP port on which dolphin server is listening on.
          - raiden_index: corresponding serial index on dolphin server.

          2. Dolphin Mini parameters:
          required fields:
          - usb_serial_params: A dict of parameters for making a serial
              connection.
          - product_id: A string for Plankton FTDI product ID.

          optional fields:
          - auto_pairing: True to make serial connection to the /dev/path
              where its driver equals to the specified driver in
              usb_serial_params.
          - plankton_conn_index: Like auto_pairing, but limit the serach
              range for physical USB port location, e.g. 1-1.

    Raises:
      BFTFixtureException: Can't detect tty* serial port for Plankton.
    """
    # Dolphin(Whale) initialization
    if 'dolphin_host' in port_params:
      remote = 'http://%s:%s' % (
          port_params['dolphin_host'], port_params['dolphin_port'])
      self._plankton_conn = xmlrpclib.ServerProxy(
          remote, verbose=False, allow_none=True)
      self._use_proxy = True
      self._raiden_index = port_params['raiden_index']
      self._i2c_address = (self._I2C_ADDR_LEFT if self._raiden_index == 0
                           else self._I2C_ADDR_RIGHT)
      # Initialize serial connection on server first
      self._plankton_conn.InitConnection(self._raiden_index)
      self.SetDefault('set default')
      self.SetOutputBufferChannel(0)  # channel 0: command only
      return

    # Dolphin Mini initialization
    self._ProbeFTDIDriver(port_params['product_id'])
    self._i2c_address = self._I2C_ADDR_MINI
    self._use_proxy = False

    serial_params = copy.deepcopy(port_params['usb_serial_params'])

    serial_driver = serial_params.get('driver')
    serial_conn_index = port_params.get('plankton_conn_index')
    if serial_conn_index:
      serial_path = serial_utils.FindTtyByPortIndex(serial_conn_index,
                                                    serial_driver)
      if not serial_path:
        raise bft_fixture.BFTFixtureException(
            'No serial device with driver %r detected at port index %s' %
            (serial_driver, serial_conn_index))
      serial_params['port'] = serial_path

    elif 'auto_pairing' in port_params:
      serial_path = serial_utils.FindTtyByDriver(serial_driver)
      if not serial_path:
        raise bft_fixture.BFTFixtureException(
            'No serial device with driver %r detected' % serial_driver)
      serial_params['port'] = serial_path

    print 'connect to ' + serial_params['port']
    self._plankton_conn = serial_utils.SerialDevice()
    self._plankton_conn.Connect(**serial_params)
    # Waits for serial connection stable.
    time.sleep(1)
    self.SetDefault('set default')
    self.SetOutputBufferChannel(0)  # channel 0: command only

  def Disconnect(self):
    """Disconnects fixture. Close serial connection of Plankton-Raiden."""
    if not self._use_proxy and self._plankton_conn:
      self._plankton_conn.Disconnect()

  def SetDeviceEngaged(self, device, engage):
    """Engages/disengages a device.

    Issues a command to BFT fixture to engage/disenage a device.
    The device can be either a peripheral device of the board or a
    device of the fixture.

    Args:
      device: device defined in BFTFixture.Device.
      engage: True to engage; False to disengage.

    Raises:
      BFTFixtureException: Unsupported action detected.
    """
    action_str = '%s device %s' % ('engage' if engage else 'disengage',
                                   device)
    logging.info(action_str)

    if device not in self.DEVICE_COMMAND:
      raise bft_fixture.BFTFixtureException(
          'Unsupported action: ' + action_str)

    if engage:
      if device in self._LIST_USB:
        time.sleep(self._WAIT_USB3_NEGOTIATE_SECS)
      for command in self.DEVICE_COMMAND[device]:
        self._Send('usbc_action ' + command, action_str)
    else:
      # Disengage Charge = set fixture charge to device.
      if device in self._LIST_CHARGE:
        self._Send('usbc_action dev', action_str)
      else:
        # Disengage USB3.0/DP = set fixture to default setting.
        if device in self._LIST_USB:
          time.sleep(self._WAIT_USB3_NEGOTIATE_SECS)
        self.SetDefault(action_str)

  def Ping(self):
    """Uses 'version' command for pinging."""
    self._Send('version', 'ping device')

  def SetDefault(self, action_str):
    """Resets default functions on Plankton board.

    Make sure USB3.0/DP function off in default stage.

    Args:
      action_str: Action description.
    """
    for command in self.DEVICE_COMMAND[self.Device.DEFAULT]:
      self._Send('usbc_action ' + command, action_str)

  def SetIOExpanderToDefault(self, default_value, readback=False):
    """Sets IO expander values for default settings.

    Args:
      default_value: A string in hex of 1-byte default value. ex. '0x80'
      readback: Set True to check if input register equals to default value
          after writing output registers.
    """
    time.sleep(1)
    self._I2CWrite('0x01', default_value)  # Write default value
    self._I2CWrite('0x02', '0x00')  # Reset all polarity
    self._I2CWrite('0x03', '0x00')  # Set all output mode
    if readback:
      byte = self._I2CRead('0x00')  # Readback input value
      if byte != int(default_value, 16):
        raise bft_fixture.BFTFixtureException(
            'Readout mismatch %s (expect: %s)' % (byte, default_value))

  def SetUSBMuxFlip(self, flip_wait_secs):
    """Sets USB3 engagement with MUX flip.

    Args:
      flip_wait_secs: Wait interval in seconds before mux flip.
    """
    self.SetDeviceEngaged('USB3', 'set mux flip')
    time.sleep(flip_wait_secs)
    self._Send('usbc_action flip', 'set mux flip')

  def SetFakeDisconnection(self, disconnect_secs):
    """Sets Raiden signal fake disconnected for an interval.

    Args:
      disconnect_secs: Disconnection interval in seconds.
    """
    disconnect_msecs = 1000 * disconnect_secs
    self._Send('fake_disconnect 0 %d' % disconnect_msecs,
               'set fake disconnection %d secs' % disconnect_secs)

  def SetOutputBufferChannel(self, channel):
    """Specifies channel for Plankton output messages.

    Args:
      channel: Channel index.
    """
    self._Send('chan %d' % channel, 'set output channel to %d' % channel)

  def SetUSBHubChargeStatus(self, enable):
    """Sets Plankton charge or not to device on USB hub.

    Args:
      enable: True for charging; False for not charging.
    """
    USB_DN_PWREN_OFFSET = 0  # Offset of downstream USB power enable bit.
    bit_value = 1 if enable else 0
    byte = self._I2CRead('0x01')  # Change output value
    self._I2CWrite('0x01', '0x%2x' % _ChangeBit(
        byte, USB_DN_PWREN_OFFSET, bit_value))
    byte = self._I2CRead('0x03')  # Change IO config
    self._I2CWrite('0x03', '0x%2x' % _ChangeBit(
        byte, USB_DN_PWREN_OFFSET, bit_value))

  def ResetUSBHub(self, wait_before_reset_secs=1, wait_after_reset_secs=1):
    """Toggles reset signal of Plankton USB Hub.

    Args:
      wait_before_reset_secs: Waiting seconds before reset sequence.
      wait_after_reset_secs: Waiting seconds after reset sequence.
    """
    time.sleep(wait_before_reset_secs)  # Wait for hub signal stable
    self._Send('hub_reset', 'Reset USB Hub')
    time.sleep(wait_after_reset_secs)  # Wait for USB recovering

  def ReadINAValues(self):
    """Sends INA command and read back voltage and current value.

    Returns:
      A dict which contains 'voltage' (in mV) and 'current' (in mA) data.
    """
    self._Send('ina 0', 'read INA current')
    time.sleep(0.1)  # Wait for message output
    read_output = self._Recv(0, 'read output')
    logging.info('read_output = %r', read_output)
    read_current = _RE_INA_CURRENT.findall(read_output)
    read_voltage = _RE_INA_VOLTAGE.findall(read_output)
    if read_current and read_voltage:
      return dict(current=int(read_current[0]), voltage=int(read_voltage[0]))
    else:
      raise bft_fixture.BFTFixtureException('Cannot read INA values')

  def _I2CWrite(self, reg_address, value):
    """Writes IO expander register through I2C interface.

    Args:
      reg_address: A string in hex of 1-byte register address. ex. '0x01'
      value: A string in hex of 1-byte write value. ex. '0x80'
    """
    logging.info('Write I2C = i2cxfer w 1 %s %s %s',
                 self._i2c_address, reg_address, value)
    self._Send('i2cxfer w 1 %s %s %s' % (self._i2c_address, reg_address, value),
               'I2C write %s %s = %s' % (self._i2c_address, reg_address, value))

  def _I2CRead(self, reg_address):
    """Reads IO expander register through I2C interface.

    Args:
      reg_address: A string in hex of 1-byte register address. ex. '0x01'

    Returns:
      Register value in integer.
    """
    self._Recv(0, 'clean buffer')
    self._Send('i2cxfer r 1 %s %s' % (self._i2c_address, reg_address),
               'I2C read %s %s' % (self._i2c_address, reg_address))
    time.sleep(0.1)  # Wait for message output
    read_output = self._Recv(0, 'read output')
    logging.info('Read I2C = %r', read_output)
    read_object = _RE_I2C_READ.findall(read_output)
    if read_object:
      return int(read_object[0])
    else:
      raise bft_fixture.BFTFixtureException('Cannot read I2C value')

  def _Send(self, command, fail_message):
    """Sends a command to BFT Fixture.

    Args:
      command: String command.
      fail_message: Error message to prepend to BFTFixtureException.

    Raises:
      BFTFixtureException: Serial command timeout.
    """
    if self._use_proxy:  # Dolphin(Whale)
      try:
        self._plankton_conn.Send(self._raiden_index, command)
      except Exception as e:
        raise bft_fixture.BFTFixtureException(
            'Dolphin: Send %s command %s failed: %s' %
            (fail_message, command, e))
    else:  # Dolphin Mini
      try:
        self._plankton_conn.Send(command + '\n')
      except serial.SerialTimeoutException as e:
        raise bft_fixture.BFTFixtureException(
            'Dolphin Mini: Send %s command %s timeout: %s' %
            (fail_message, command, e))

  def _Recv(self, byte, fail_message):
    """Receives a response from BFT fixture.

    Args:
      byte: Number of bytes to be received. 0 means receiving what already in
          the input buffer.
      fail_message: error message to prepend to BFTFixtureException.

    Returns:
      The response.

    Raises:
      BFTFixtureException: Serial command timeout.
    """
    if self._use_proxy:  # Dolphin(Whale)
      try:
        binary_packet = self._plankton_conn.Receive(self._raiden_index, byte)
        return binary_packet.data
      except Exception as e:
        raise bft_fixture.BFTFixtureException(
            'Dolphin: Receive %s failed: %s' % (fail_message, e))
    else:  # Dolphin Mini
      try:
        return self._plankton_conn.Receive(byte)
      except serial.SerialTimeoutException as e:
        raise bft_fixture.BFTFixtureException(
            'Dolphin Mini: Receive %s timeout: %s' % (fail_message, e))

  def _ProbeFTDIDriver(self, product_id):
    """Modprobe FTDI driver manually.

    Args:
      product_id: Product ID for FTDI driver.
    """
    process_utils.Spawn(['modprobe', 'ftdi_sio'], call=True)
    id_string = '18d1 %s' % product_id
    if not any(
        l.startswith(id_string) for l in file_utils.ReadLines(
            '/sys/bus/usb-serial/drivers/ftdi_sio/new_id')):
      file_utils.WriteWithSudo('/sys/bus/usb-serial/drivers/ftdi_sio/new_id',
                               id_string)
    # Waits for procfs update.
    time.sleep(1)
