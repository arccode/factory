/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {TestCase} from '/src/tests/test_case.js';

export class InfoTest extends TestCase {
  constructor() {
    super();
    this.html = '/src/tests/info/info.html';
    this.name = 'Info';
    this.passTest = this.passTest.bind(this);
  }

  async setUp() {
    await this.setHTML();
    this.setEndTestPromise();
  }

  async runTest() {
    this.getCPUInfo();
    this.getMemoryInfo();
    this.getStorageInfo();
    document.getElementById('pass-test')
      .addEventListener('click', this.passTest);

    // The test requires human interaction, so we just wait for the test to end.
    const result = await this.waitEndTestResult();
    if (!result.success) {
      this.failTest(result.message);
    }
  }

  createListItem(value) {
    if (value) {
      const li = document.createElement('li');
      li.textContent = value;
      return li;
    }
  }

  getCPUInfo() {
    chrome.system.cpu.getInfo((info) => {
      if (!info) this.endTest(false, 'Cannot get CPU info');
      const divCPU = document.createElement('h3');
      divCPU.id = 'cpu';
      divCPU.textContent = 'CPU';
      divCPU.appendChild(
          this.createListItem('Number of processors: ' +
              info.numOfProcessors.toString()));
      divCPU.appendChild(this.createListItem('Arch name: '+ info.archName));
      divCPU.appendChild(this.createListItem('Model name: ' + info.modelName));
      if (info.temparature) {
        divCPU.appendChild(
            this.createListItem('Max temperature of CPU: ' +
                Math.max(info.temparature).toString()));
      }
      document.getElementById('info').appendChild(divCPU);
    });
  }

  getMemoryInfo() {
    chrome.system.memory.getInfo((info) => {
      if (!info) this.endTest(false, 'Cannot get Memory info');
      const divMemory = document.createElement('h3');
      divMemory.id = 'memory';
      divMemory.textContent = 'Memory';
      divMemory.appendChild(
          this.createListItem('Available capacity: ' +
              this.convertBytes(info.availableCapacity)));
      divMemory.appendChild(
          this.createListItem('Capacity: ' + this.convertBytes(info.capacity)));
      document.getElementById('info').appendChild(divMemory);
    });
  }

  getStorageInfo() {
    const createStorageInfo = (index, elem) => {
      const div = document.createElement('div');
      div.id =  'hard-disk ' + index.toString();
      div.appendChild(this.createListItem('Name: ' + elem.name));
      div.appendChild(
          this.createListItem('Capacity: ' +
              this.convertBytes(elem.capacity).toString()));
      return div;
    };

    chrome.system.storage.getInfo((info) => {
      if(!info) this.endTest(false, 'Cannot get Memory info');
      const divStorage = document.createElement('h3');
      divStorage.id = 'hard-disk';
      for (const [index, elem] of info.entries()) {
        if (elem.type === 'fixed') {
          divStorage.appendChild(createStorageInfo(index, elem));
        }
      }
      document.getElementById('info').appendChild(divStorage);
    });
  }

  convertBytes(bytes) {
    if (bytes === 0) return '0 Byte';
    const prefix = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
    const i = parseInt(Math.floor(Math.log(bytes) / Math.log(1024)));
    if (i > 8) return 'Out of Range';
    return Math.round(bytes / Math.pow(1024, i), 2) + ' ' + prefix[i];
  }

  passTest() {
    this.endTest(true);
  }

  endTest(success, message) {
    document.getElementById('pass-test')
      .removeEventListener('click', this.passTest);
    this.sendEndTestResult(success, message);
  }
}