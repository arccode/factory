/* Copyright 2018 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {EventEmitter, Injectable} from '@angular/core';

import {TestResource} from './interfaces/test-resource';
import {TEST_COMPONENTS} from './test-list.resource';

/**
 * A service for test-list related states.
 */
// tslint:disable-next-line:no-unsafe-any
@Injectable()
export class TestListService {
  /** The test that is currently running. */
  private currentTest: string = '';

  /** Event emitter to send testSelected event. */
  testSelected: EventEmitter<string> = new EventEmitter();

  constructor() {}

  /** Get tests and their TestCase types. */
  getTestList(): {[testName: string]: TestResource} {
    return TEST_COMPONENTS;
  }

  /**
   * Set current test.
   *
   * If the current test is successfully changed, `testSelected` event will be
   * emitted.
   */
  setCurrentTest(test: string): void {
    if (this.currentTest !== '') {
      throw new Error('There is a current running test...');
    }

    if (!(test in TEST_COMPONENTS)) {
      throw new Error(`${test} is not a valid test`);
    }

    this.currentTest = test;
    this.testSelected.emit(test);
  }

  /** Get current test. */
  getCurrentTest(): string {
    return this.currentTest;
  }

  clearCurrentTest(): void {
    this.currentTest = '';
  }
}
