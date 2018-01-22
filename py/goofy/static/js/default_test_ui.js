// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const test = window.test;
const invocation = test.invocation;
const goofy = invocation.goofy;
const testEntry = goofy.pathTestMap[invocation.path];

const startTime = Date.now();

goog.dom.safe.setInnerHtml(
    document.getElementById('test-info-title'),
    cros.factory.i18n.i18nLabel(testEntry.label));

// Return JSON stringify result, with indentation and all keys in sorted order.
const prettyJSON = (obj) => {
  const getAllKeys = (o) => {
    const keys = [];
    if (Array.isArray(o)) {
      for (const item of o) {
        keys.push(...getAllKeys(item));
      }
    } else if (o !== null && typeof o === 'object') {
      // We assume that the passed in object only contains primitive (number,
      // string, boolean, null), arrays and simple object (mapping) with string
      // keys (That is, the "object" defined in JSON standard). So the typeof
      // check is good enough.
      for (const [k, v] of Object.entries(o)) {
        keys.push(k);
        keys.push(...getAllKeys(v));
      }
    }
    return keys;
  };
  return JSON.stringify(obj, getAllKeys(obj).sort(), 2);
};

const data = {
  path: invocation.path,
  invocation: invocation.uuid,
  pytest: testEntry.pytest_name,
  'original-args': prettyJSON(testEntry.args),
  'resolved-args': 'Loading...'
};

for (const key of Object.keys(data)) {
  document.getElementById('test-info-' + key).innerText = data[key];
}

(async () => {
  while (true) {
    const element = document.getElementById('test-info-time');
    // If the element no longer exists, assume that we've been overriden by
    // actual test UI.
    if (!element) {
      return;
    }
    goog.dom.safe.setInnerHtml(
        element, cros.factory.i18n.i18nLabel(_('{seconds} seconds', {
          seconds: Math.floor((Date.now() - startTime) / 1000)
        })));
    await cros.factory.utils.delay(1000);
  }
})();

(async () => {
  while (true) {
    const element = document.getElementById('test-info-resolved-args');
    // If the element no longer exists, assume that we've been overriden by
    // actual test UI.
    if (!element) {
      return;
    }

    const resolvedArgs =
        await goofy.sendRpc('GetInvocationResolvedArgs', invocation.uuid);
    // The arguments is resolved (in invocation.py) after UI is initialized (in
    // goofy.py), so it might not be ready when this is run. Retry if we got
    // null.
    if (resolvedArgs) {
      element.innerText = prettyJSON(resolvedArgs);
      break;
    }
    await cros.factory.utils.delay(100);
  }
})();

const toggleButton =
    goog.ui.decorate(document.getElementById('test-info-args-toggle'));
goog.events.listen(
    toggleButton, goog.ui.Component.EventType.ACTION, (event) => {
      document.getElementById('test-info-args-container')
          .classList.toggle('show-original', event.target.isChecked());
    });

// Show this page after a short amount of delay, to minimize the flash on the
// screen if the real test UI overrides this.
window.setTimeout(() => {
  const element = document.getElementById('test-info-container');
  if (element) {
    goog.style.setStyle(element, 'visibility', 'visible');
  }
}, 500);
