/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
export class LoggingUtils {
  static log(message) {
    console.log(message);
    const e = new Event(LoggingUtils.eventType);
    e.message = message;
    document.dispatchEvent(e);
  }
}

LoggingUtils.eventType = 'diagnosis:log';
