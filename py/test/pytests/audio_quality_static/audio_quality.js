// Copyright 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

let active = 'loop_0';
let display_fa_utility = false;

const testCommand = (cmd) => {
  if (active) {
    document.getElementById(active).checked = false;
  }
  window.test.sendTestEvent('mock_command', {'cmd': cmd});
  active = cmd;
};

const restore = () => {
  testCommand('loop_0');
  document.getElementById('loop_0').checked = true;
};

const toggleFAUtility = () => {
  if (display_fa_utility) {
    restore();
    document.getElementById('fa-utility').style.display = 'none';
    display_fa_utility = false;
    window.test.sendTestEvent('mock_command', {'cmd': 'reset'});
  } else {
    document.getElementById('fa-utility').style.display = 'block';
    display_fa_utility = true;
    document.getElementById('message').innerHTML = '';
  }
};

const exports = {
  testCommand,
  restore,
  toggleFAUtility
};
for (const key of Object.keys(exports)) {
  window[key] = exports[key];
}
