#!/usr/bin/env python2

# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import time

import serial

import factory_common  # pylint: disable=unused-import
from cros.factory.test.utils import serial_utils


class ArduinoController(serial_utils.SerialDevice):
  """Used to communicate with fixture with Arduino microcontroller.

  An optional ready_delay_secs is used that Arduino Uno is reset for
  each connection and it takes about 2 seconds to reboot. It is better
  to wait before any action.

  For Arduino code, it looks like:

  int targetPin = 12;

  void setup()  {
    Serial.begin(9600);
    pinMode(targetPin, OUTPUT);
    digitalWrite(targetPin, LOW);
  }

  void loop() {
    if (Serial.available() > 0) {
      int cmd = Serial.read();
      switch (cmd) {
      case 'H':
        digitalWrite(targetPin, HIGH);
        Serial.write('H');
        break;
      case 'L':
        digitalWrite(targetPin, LOW);
        Serial.write('L');
        break;
      case 1:
        Serial.write(1);
        break;
      case 2:
        Serial.write(2);
        break;
      case 3:
        Serial.write(3);
        break;
      default:
        Serial.write('X');  // unsupport
      }
    }
  }
  """

  def __init__(self, send_receive_interval_secs=0.5, retry_interval_secs=0.2,
               log=True, ready_delay_secs=2.0):
    """Constructor.

    Besides parameters in parent's ctor, it adds ready_delay_secs which is
    used to wait for Arduino to boot after reset.
    """
    super(ArduinoController, self).__init__(
        send_receive_interval_secs=send_receive_interval_secs,
        retry_interval_secs=retry_interval_secs, log=log)
    self._ready_delay_secs = ready_delay_secs

  def __del__(self):
    self.Disconnect()

  def Connect(self, **kwargs):
    """Opens a serial connection.

    After connection establish, it waits for ready_delay_secs as Arduino
    is reset for each connection, which takes a while to reboot. After that, it
    pings the Arduino board to make sure it works.

    Args:
      driver: driver name of the target serial connection. Used to look up port
          if port is not specified. Default 'cdc_acm'.
      port, baudrate, bytesize, parity, stopbits, timeout, writeTimeout: See
          serial.Serial().

    Raises:
      SerialException on errors.
    """
    if 'driver' not in kwargs:
      kwargs['driver'] = 'cdc_acm'

    super(ArduinoController, self).Connect(**kwargs)
    time.sleep(self._ready_delay_secs)

    if not self.Ping():
      self.Disconnect()
      raise serial.SerialException('Ping Arduino (port %s) failed' % self._port)

  def Ping(self, retry=0):
    """Pings Arduino. Used for handshaking.

    It sends command '1', '2', '3' and expects response '1', '2', '3',
    respectively. For the command '1', we can retry N times (to wait for
    Arduino ready). But for command "2" and "3", Arduino should response
    as expected without retry.

    Args:
      retry: number of retry.
    """
    return (self.SendExpectReceive(chr(1), chr(1), retry=retry) and
            self.SendExpectReceive(chr(2), chr(2)) and
            self.SendExpectReceive(chr(3), chr(3)))

  def Reset(self, wait_ready=True):
    """Resets Arduino controller.

    Args:
      wait_ready: True to wait for ready_delay_secs after reset.
    """
    # Pull down DTR can reset Arduino Uno.
    self._serial.setDTR(False)
    time.sleep(0.05)
    self._serial.setDTR(True)
    if wait_ready:
      time.sleep(self._ready_delay_secs)


class ArduinoDigitalPinController(ArduinoController):
  """Simple Arduino digital pin controller.

  This class is intended to be used with arduino_digital_pin_controller.ino. If
  you want to customize more on the Arduino firmware, please see the comments
  in arduino_digital_pin_controller.ino for more info.

  So if you want to modify this class such that its command format would
  change, be sure to update arduino_digital_pin_controller.ino as well.
  """

  def __init__(self, send_receive_interval_secs=0.5, retry_interval_secs=0.2,
               log=True, ready_delay_secs=2.0):
    """Constructor."""
    super(ArduinoDigitalPinController, self).__init__(
        send_receive_interval_secs, retry_interval_secs, log, ready_delay_secs)

  def SetPin(self, pin, level_high=True):
    """Sets a pin to HIGH or LOW.

    Args:
      pin: The Arduino pin number. For Arduino UNO, it should be 2-13.
      level_high: True for HIGH, False for LOW.
    """
    command = chr(pin) + ('H' if level_high else 'L')
    if not self.SendExpectReceive(command, command):
      raise serial.SerialException('Send command "chr(%d) %s" failed' % (
          ord(command[0]), command[1]))


def _Blink(arduino, times=1, interval_secs=0.1):
  """Blinks LED light in Arduino board.

  This is an example of how to use ArduinoController object.
  """
  for nth in range(times):
    if nth:
      time.sleep(interval_secs)

    if not arduino.SendExpectReceive('H', 'H', retry=2):
      raise Exception('Failed to send command "H"')

    time.sleep(interval_secs)

    if not arduino.SendExpectReceive('L', 'L', retry=2):
      raise Exception('Failed to send command "L"')


def main():
  logging.basicConfig(level=logging.INFO)
  arduino = ArduinoController()
  arduino.Connect()
  _Blink(arduino, times=3, interval_secs=0.5)
  arduino.Reset()


if __name__ == '__main__':
  main()
