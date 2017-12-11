// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const StationSetup = window.test.invocation.goofy.StationSetup;
let isInEnter = false;
let update = undefined;

window.test.bindKey('ENTER', () => {
  if (isInEnter) {
    return;
  }
  if (update) {
    isInEnter = true;
    update(window.template).then((ret) => {
      if (ret.success) {
        window.test.pass();
      } else {
        isInEnter = false;
      }
    });
  }
});

(async () => {
  const needUpdate = await StationSetup.needUpdate();
  if (!needUpdate) {
    window.test.pass();
    return;
  }
  const ret = await StationSetup.run();
  update = ret.update;
  window.template.setState(goog.html.SafeHtml.unwrap(ret.html));
})();
