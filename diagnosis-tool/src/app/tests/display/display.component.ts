/* Copyright 2018 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {Component, OnInit} from '@angular/core';

import {TestCase} from '../../interfaces/test-case';
import {TestRunService} from '../../test-run-service';

type TestResultState = 'UNTESTED'|'PASS'|'FAILD';
type TestScreenState = 'SHOW'|'HIDE';

/** Display test. */
@Component({
  selector: 'app-display',
  templateUrl: './display.component.html',
  styleUrls: ['./display.component.css']
})
export class DisplayComponent extends TestCase implements OnInit {
  constructor(private readonly testRunService: TestRunService) {
    super();
    this.keyDown = this.keyDown.bind(this);
    this.testTimeout = this.testTimeout.bind(this);
  }

  args: {[key: string]: any} = {};
  testList:
      {name: string, result: TestResultState, css: {[key: string]: any}}[] = [];
  testScreenState: TestScreenState = 'HIDE';
  runningTestIndex: number = 0;
  inTest: boolean = false;
  remainTime: number = 0;

  ngOnInit(): void {}

  setUp(args: {[key: string]: string}): void {
    this.args = args;
    this.init();
  }

  keyDown(e: KeyboardEvent) {
    if (e.code === 'Space') {
      this.testScreenState = this.testScreenState === 'HIDE' ? 'SHOW' : 'HIDE';
    } else if (e.code === 'Enter') {
      this.testList[this.runningTestIndex].result = 'PASS';
      if (this.runningTestIndex + 1 < this.testList.length) {
        this.runningTestIndex++;
      } else {
        this.endTest(true, '');
      }
    } else if (e.code === 'Escape') {
      this.endTest(
          false, `Faild on ${this.testList[this.runningTestIndex].name} test`);
    }
    this.setTest(this.testList[this.runningTestIndex].name);
  }

  runTest(): void {
    console.log(`${this.getTestName()}.runTest is called`);
  }

  getTestName(): string {
    return 'Display';
  }

  getBackgroundColor(item: string) {
    if (item.search('-gray-') != -1) {
      let color = item.slice(item.search('-gray-') + 6);
      return `rgba(${color}, ${color}, ${color})`;
    } else if (item.search('solid-') != -1) {
      return item.slice(item.search('solid-') + 6);
    } else {
      return 'transparent';
    }
  }

  setTest(test: string) {
    let element = document.getElementById('test');
    if (!element) return;
    if (this.testScreenState === 'HIDE') {
      element.style.backgroundColor = 'transparent';
      return;
    }
    element.style.backgroundColor = this.getBackgroundColor(test);
  }

  endTest(success: boolean, message: string) {
    this.inTest = false;
    document.removeEventListener('keydown', this.keyDown);
    this.testRunService.endTest(success, message);
  }

  testTimeout() {
    setTimeout(() => {
      this.remainTime -= 0.1;
      if (this.remainTime >= 0 && this.inTest) {
        this.testTimeout();
      } else if (this.inTest) {
        this.endTest(false, `Time out.`);
      }
    }, 100);
  }

  init() {
    this.testList = [];
    for (let i in this.args.items) {
      this.testList.push({
        name: this.args.items[i],
        result: 'UNTESTED',
        css: {'background-color': this.getBackgroundColor(this.args.items[i])}
      });
    }
    this.testScreenState = 'HIDE';
    this.runningTestIndex = 0;
    document.addEventListener('keydown', this.keyDown);
    if (this.args.idle_timeout) {
      this.remainTime = parseFloat(this.args.idle_timeout);
      this.testTimeout();
    }
    this.inTest = true;
  }
}

export const DISPLAY_ARGS_SPEC = [
  {
    name: 'items',
    help: 'test items list',
    default: [
      'solid-gray-170', 'solid-gray-127', 'solid-gray-63', 'solid-red',
      'solid-green', 'solid-blue'
    ],
    type: 'string[]',
    list: [
      'solid-gray-170',
      'solid-gray-127',
      'solid-gray-63',
      'solid-red',
      'solid-green',
      'solid-blue',
      'solid-white',
      'solid-gray',
      'solid-black',
    ]
  },
  {
    name: 'idle_timeout',
    help:
        'If given, the test would be start automatically, run for timeout seconds',
    default: null,
    type: 'number'
  }
];
