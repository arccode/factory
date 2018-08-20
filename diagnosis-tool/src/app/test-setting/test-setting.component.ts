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
  args: {[key: string]: any} = {};
  @Input() argsSpec!: ArgSpec[];
  @Input() startTestCallback!: (args: object) => void;

  constructor() {}

  ngOnInit() {}

  ngOnChanges(changes: SimpleChanges) {
    if (changes.argsSpec.currentValue) {
      const obj: {[key: string]: any} = {};
      for (const element of this.argsSpec) {
        obj[element.name] = element.default;
      }
      this.args = obj;
    }
  }

  isArray(object: any): boolean {
    return Array.isArray(object);
  }

  getNotChosen(arg: any): any[] {
    if (!arg.list) {
      return [];
    }
    return arg.list.filter((option: any) => {
      return this.args[arg.name].indexOf(option) === -1;
    });
  }

  choose(event: Event, name: string, item: string): void {
    let index = this.args[name].indexOf(item);
    if (index != -1) {
      this.args[name].splice(index, 1);
    } else {
      this.args[name].push(item);
    }
    event.preventDefault();
  }

  onStartTest() {
    this.startTestCallback(this.args);
  }
}
