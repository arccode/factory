/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {DisplayTest} from '/src/tests/display/display.js';
import {TouchpadTest} from '/src/tests/touchpad/touchpad.js';
import {TouchscreenTest} from '/src/tests/touchscreen/touchscreen.js';

export const TEST_COMPONENTS = [
  DisplayTest,
  TouchpadTest,
  TouchscreenTest
];
