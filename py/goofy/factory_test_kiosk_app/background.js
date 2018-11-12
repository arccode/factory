// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// To use this extension, do:
//  chrome.runtime.sendMessage(<ID>, {name: <RPC_NAME>, args: <ARGS>},
//    function(result) { ... deal with the results ... });

chrome.runtime.onMessageExternal.addListener(
    (request, sender, sendResponse) => {
      if (request.name === 'GetDisplayInfo') {
        chrome.system.display.getInfo(sendResponse);
        return true;
      } else if (request.name === 'SetDisplayProperties') {
        chrome.system.display.setDisplayProperties(
            request.args.id, request.args.info,
            () => { sendResponse(chrome.runtime.lastError); });
        return true;
      } else if (request.name === 'SetDisplayMirrorMode') {
        chrome.system.display.setMirrorMode(
            request.args.info,
            () => { sendResponse(chrome.runtime.lastError); });
        return true;
      } else {
        window.console.log('Unknown RPC call', request);
      }
    });
