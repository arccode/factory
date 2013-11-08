// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

(function() {
  window.addEventListener("keydown",
      function(e) {
        if (e.keyCode === 8 && e.target.nodeName === "BODY") {
          // Prevent backspace from returning us to the previous page.
          e.preventDefault();
        }
      }, true);
})();
