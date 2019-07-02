/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {TestState} from '/src/tests/test_state.js';
import {TEST_COMPONENTS} from '/src/test_list_resource.js';
import {LoggingUtils} from '/src/utils/logging_utils.js';

class DiagnosisTool {
  constructor() {
    this.html = '/src/diagnosis.html';

    /** Title of extension. */
    this.title = 'ChromeOS Diagnosis Tool';

    /** List of test case classes. */
    this.testList = TEST_COMPONENTS;

    /** Test currently running. */
    this.activeTest = '';
  }

  async start() {
    const response = await fetch(this.html);
    const html = await response.text();
    document.body.innerHTML = html;
    document.getElementById('test-list-title').innerText = this.title;
    this.setLog();
    this.setTestList();
  }

  /** Set event listener to update logs. */
  setLog() {
    const log = document.getElementById('log');
    document.addEventListener(LoggingUtils.eventType, (e) => {
      // Add some margin so that people don't need to scroll to the very bottom
      // to make sure scrolling works.
      const scrollAtBottom =
          (log.scrollTop >= log.scrollHeight - log.clientHeight - 10);
      log.innerText += (e.message + "\n");
      if (scrollAtBottom) {
        log.scrollTop = log.scrollHeight - log.clientHeight;
      }
    });
  }

  /** Set test list in HTML. */
  setTestList() {
    const ul = document.getElementById('tests');
    for (let i in this.testList) {
      // TODO(chenghan): Able to pass spec parameters to constructor.
      const test = new this.testList[i]();
      ul.appendChild(this.createTestItem(test));
    }
  }

  /** Create a button for a test. */
  createTestItem(test) {
    const testName = document.createElement('span');
    testName.innerText = test.getTestName();
    const testItem = document.createElement('li');
    testItem.appendChild(testName);
    testItem.classList.add('test-item');
    const onclick_func = () => {
      this.startTest(test);
    };
    testItem.onclick = onclick_func;
    test.setTestItem(testItem);
    test.setTestState(TestState.UNTESTED);
    return testItem;
  }

  /** Start test. */
  async startTest(test) {
    if (this.activeTest !== '') {
      console.log(`${this.activeTest} test is running.`);
      return;
    }
    this.activeTest = test.getTestName();
    console.log(`Starting ${this.activeTest} test.`);
    try {
      try {
        test.setTestState(TestState.ACTIVE);
        await test.setUp();
        await test.runTest();
        test.setTestState(TestState.PASSED);
        LoggingUtils.log(`${test.getTestName()} succeeded.`);
      } finally {
        test.tearDown();
      }
    } catch(error) {
      test.setTestState(TestState.FAILED);
      LoggingUtils.log(`${test.getTestName()} failed: ${error}`);
    }
    console.log(`Ending ${this.activeTest} test.`);
    this.activeTest = '';
  }
}

const diagTool = new DiagnosisTool();
diagTool.start();
