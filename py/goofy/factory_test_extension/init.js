// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const startFactoryPage = () => {
  chrome.runtime.sendMessage(null, 'StartFactoryPage', {}, (response) => {
    if (chrome.runtime.lastError || response !== true) {
      console.log(chrome.runtime.lastError, response);
      setTimeout(startFactoryPage, 100); // retry in 100 millisecond
    }
  });
};

startFactoryPage();
