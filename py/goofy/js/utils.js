// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.utils');

/**
 * Returns a promise that resolves after a period of time.
 * @param {number} ms the millisecond of the delay.
 * @return {Promise}
 */
cros.factory.utils.delay = (ms) => new Promise((resolve) => {
  setTimeout(resolve, ms);
});
