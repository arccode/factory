/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {CameraTest} from '/src/tests/camera/camera.js';
import {DisplayTest} from '/src/tests/display/display.js';
import {TouchpadTest} from '/src/tests/touchpad/touchpad.js';
import {TouchscreenTest} from '/src/tests/touchscreen/touchscreen.js';
import {VideoTest} from '/src/tests/video/video.js';

export const TEST_COMPONENTS = [
  CameraTest,
  DisplayTest,
  TouchpadTest,
  TouchscreenTest,
  VideoTest
];
