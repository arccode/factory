// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

chrome.runtime.onMessageExternal.addListener(
    function(request, sender, sendResponse) {
      if (request.name == 'GetDisplayInfo') {
        chrome.system.display.getInfo(sendResponse);
        return true;  // indicate that we have async response.
      } else {
        window.console.log("Unknown RPC call", request);
      }
    });

// To use this extension, do:
//  chrome.runtime.sendMessage(<ID>, {name: <RPC_NAME>, args: <ARGS>},
//    function(result) { ... deal with the results ... });
