/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {TestCase} from '/src/tests/test_case.js';
import {LoggingUtils} from '/src/utils/logging_utils.js';

export class BluetoothTest extends TestCase {
  constructor() {
    super();
    this.html = '/src/tests/bluetooth/bluetooth.html';
    this.name = 'Bluetooth';
    this.keyDown = this.keyDown.bind(this);
  }

  async setUp() {
    this.enteredTest = false;
    await this.setHTML();
    document.addEventListener('keydown', this.keyDown);
    this.setEndTestPromise();
  }

  async runTest() {
    // The test requires human interaction, so we just wait for the test to end.
    const result = await this.waitEndTestResult();
    if (!result.success) {
      this.failTest(result.message);
    }
  }

  async keyDown(e) {
    if (!this.enteredTest && e.key === ' ') {
      this.enteredTest = true;
      if (!navigator.bluetooth) {
        this.endTest(false, 'Bluetooth is not supported');
      } else {
        await this.connectingDevice();
      }
    } else if (this.enteredTest && e.key === 'q') {
      this.endTest(false, 'Mark failed by operator.');
    }
  }

  async connectingDevice() {
    try {
      const constraints = {
        acceptAllDevices: true,
        optionalServices: [BluetoothUUID.getService(0x1800)]
      };
      const device = await navigator.bluetooth.requestDevice(constraints);
      LoggingUtils.log(`Connecting to bluetooth device: ${device.name}.`);
      const server = await device.gatt.connect();
      LoggingUtils.log(`Disconnecting from bluetooth device: ${device.name}.`);
      await server.disconnect();
      this.endTest(true);
    } catch (error) {
      this.endTest(false, error);
    }
  }

  endTest(success, message) {
    document.removeEventListener('keydown', this.keyDown);
    this.sendEndTestResult(success, message);
  }
}