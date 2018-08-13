/* Copyright 2018 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {Component, OnInit} from '@angular/core';
import {TestCase} from '../../interfaces/test-case';

/** Touchscreen Test */
@Component({
  selector: 'app-touchscreen',
  templateUrl: './touchscreen.component.html',
  styleUrls: ['./touchscreen.component.css']
})
export class TouchscreenComponent extends TestCase implements OnInit {
  constructor() {
    super();
  }

  args: {[key: string]: string} = {};

  setUp(args: {[key: string]: string}): void {
    this.args = args;
  }

  ngOnInit(): void {}

  runTest(): void {
    console.log(`${this.getTestName()}.runTest is called`);
  }

  getTestName(): string {
    return 'Touchscreen';
  }
}

export const TOUCHSCREEN_ARGS_SPEC = [
  {
    name: 'xSegments',
    help: 'Number of segments in x-axis.',
    default: 5,
    type: 'number'
  },
  {
    name: 'ySegments',
    help: 'Number of segments in y-axis.',
    default: 5,
    type: 'number'
  },
  {
    name: 'timeout',
    help: 'Timeout',
    default: 30,
    type: 'number'
  }
];
