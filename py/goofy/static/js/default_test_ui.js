// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const test = window.test;
const invocation = test.invocation;
const goofy = invocation.goofy;
const testEntry = goofy.pathTestMap[invocation.path];
const _ = cros.factory.i18n.translation;

let startTime = Date.now();

goog.dom.safe.setInnerHtml(
    document.getElementById('test-info-title'),
    cros.factory.i18n.i18nLabel(testEntry.label));

const data = {
  path: invocation.path,
  invocation: invocation.uuid,
  pytest: testEntry.pytest_name,
  args: JSON.stringify(testEntry.args, null, 2)
};

for (const key of Object.keys(data)) {
  goog.dom.setTextContent(
      document.getElementById('test-info-' + key), data[key]);
}

const tick = () => {
  const element = document.getElementById('test-info-time');
  // If the element no longer exists, assume that we've been overriden by
  // actual test UI.
  if (!element) {
    return;
  }
  goog.dom.safe.setInnerHtml(
      element,
      cros.factory.i18n.i18nLabel(cros.factory.i18n.stringFormat(
          _('{seconds} seconds'),
          {seconds: Math.floor((Date.now() - startTime) / 1000)})));
  window.setTimeout(tick, 1000);
};

tick();

// Show this page after a short amount of delay, to minimize the flash on the
// screen if the real test UI overrides this.
window.setTimeout(() => {
  const element = document.getElementById('test-info-container');
  if (element) {
    goog.style.setStyle(element, 'visibility', 'visible');
  }
}, 500);
