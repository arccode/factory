// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Send a test event when an element with attribute data-test-event is clicked.
document.addEventListener('click', (event) => {
  const target = event.target.closest('[data-test-event]');
  if (target) {
    window.test.sendTestEvent(target.dataset.testEvent);
    event.stopPropagation();
    event.preventDefault();
  }
});
