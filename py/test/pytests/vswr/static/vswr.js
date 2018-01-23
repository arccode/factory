// Copyright 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

window.showMessageBlock = (id) => {
  // Hide all message blocks under div#state.
  const state_block = document.getElementById('state');
  for (const ele of state_block.children) {
    ele.style.display = 'none';
  }
  // Make the one specified message block visible.
  const message = document.getElementById('state-' + id);
  if (message) {
    message.style.display = '';
  }
};
