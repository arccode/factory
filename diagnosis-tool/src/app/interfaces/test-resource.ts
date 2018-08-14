/* Copyright 2018 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

import {Type} from '@angular/core';
import {TestCase} from './test-case';

export interface ArgSpec {
  name: string,
  help: string,
  default: any,
  type: string
};

export interface TestResource {
  component: Type<TestCase>;
  argsSpec: ArgSpec[];
}
