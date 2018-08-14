/* Copyright 2018 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {
  Component,
  Input,
  OnChanges,
  OnInit,
  SimpleChanges
} from '@angular/core';

import {ArgSpec} from '../interfaces/test-resource';

@Component({
  selector: 'app-test-setting',
  templateUrl: './test-setting.component.html',
  styleUrls: ['./test-setting.component.css']
})
export class TestSettingComponent implements OnInit, OnChanges {
  args: object = {};
  @Input() argsSpec!: ArgSpec[];
  @Input() startTestCallback!: (args: object) => void;

  constructor() {}

  ngOnInit() {}

  ngOnChanges(changes: SimpleChanges) {
    if (changes.argsSpec.currentValue) {
      const obj: {[key: string]: string} = {};
      for (const element of this.argsSpec) {
        obj[element.name] = element.default;
      }
      this.args = obj;
    }
  }

  onStartTest() {
    this.startTestCallback(this.args);
  }
}
