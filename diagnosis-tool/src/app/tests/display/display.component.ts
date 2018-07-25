/* Copyright 2018 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {Component, OnInit} from '@angular/core';

import {TestCase} from '../../interfaces/test-case';

/** Display test. */
@Component({
  selector: 'app-display',
  templateUrl: './display.component.html',
  styleUrls: ['./display.component.css']
})
export class DisplayComponent extends TestCase implements OnInit {
  constructor() {
    super();
  }

  ngOnInit(): void {}

  runTest(): void {
    console.log(`${this.getTestName()}.runTest is called`);
  }

  getTestName(): string {
    return 'Audio';
  }

  getArgsSpec(): object {
    return {};
  }
}
