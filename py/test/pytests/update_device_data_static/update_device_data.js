// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const sendSelectValue = (id, eventType) => {
  const ele = document.getElementById(id);
  window.test.sendTestEvent(eventType, ele.selectedOptions[0].value);
};

const sendInputValue = (id, eventType) => {
  const ele = document.getElementById(id);
  window.test.sendTestEvent(eventType, ele.value);
};

const exports = {
  sendSelectValue,
  sendInputValue
};
for (const key of Object.keys(exports)) {
  window[key] = exports[key];
}
