// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

var active = 'loop_0';
var display_fa_utility = false;
var start_run = false;

window.onkeydown = function(event) {
  if (event.keyCode == 32 && start_run == false) {
    test.sendTestEvent("start_run",{});
    document.getElementById('msg-utility').style.display = 'none';
    start_run = true;
  }
}

//window.onload = function(event) {
//  test.sendTestEvent("start_run",{});
//}

function setMessage(msg) {
  document.getElementById("message").innerHTML = msg;
}

function testCommand(cmd) {
  if (active.length != 0)
    document.getElementById(active).checked = false;
  test.sendTestEvent("mock_command", {"cmd": cmd});
  active = cmd;
}

function restore() {
  if (active.length != 0)
    document.getElementById(active).checked = false;
  testCommand('loop_0');
  document.getElementById('loop_0').checked = true;
}

function toggleFAUtility() {
  if (display_fa_utility) {
    restore();
    document.getElementById('fa-utility').style.display = 'none';
    display_fa_utility = false;
    test.sendTestEvent("mock_command", {"cmd": 'reset'});
  } else {
    document.getElementById('fa-utility').style.display = 'block';
    display_fa_utility = true;
    setMessage('');
  }
}
