/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

chrome.browserAction.onClicked.addListener((tab) => {
  chrome.tabs.create({'url': 'src/index.html'});
});