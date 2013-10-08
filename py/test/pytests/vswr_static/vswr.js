// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

function emitSNEnterEvent() {
  sn = document.getElementById("sn");
  window.test.sendTestEvent("snenter", sn.value);
}

function showMessageBlock(id) {
  // Hide all message blocks under div#state.
  var state_block = document.getElementById("state");
  var states = state_block.children;
  for (var i = 0; i < states.length; ++i)
    states[i].style.display = "none";
  // Make the one specified message block visible.
  message = document.getElementById("state-" + id);
  if (message != undefined)
    message.style.display = "";
}
