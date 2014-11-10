// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

chrome.runtime.onMessageExternal.addListener(
    function(request, sender, sendResponse) {
      if (request.name == 'GetDisplayInfo') {
        chrome.system.display.getInfo(sendResponse);
        return true;  // indicate that we have async response.
      } else if (request.name == 'CreateWindow') {
        chrome.windows.create(
            {'left': request.args.left, 'top': request.args.top},
            function(win) { sendResponse(win); });
        return true;
      } else if (request.name == 'UpdateWindow') {
        chrome.windows.update(
            request.args.window_id, request.args.update_info,
            function(win) { sendResponse(win); });
        return true;
      } else if (request.name == 'RemoveWindow') {
        chrome.windows.remove(
            request.args.window_id,
            function() { sendResponse(true); });
        return true;
      } else if (request.name == 'QueryTabs') {
        chrome.tabs.query(
            {'windowId': request.args.window_id},
            function(tabs) { sendResponse(tabs); });
        return true;
      } else if (request.name == 'UpdateTab') {
        chrome.tabs.update(
            request.args.tab_id, request.args.update_info,
            function(tab) { sendResponse(tab); });
        return true;
      } else {
        window.console.log("Unknown RPC call", request);
      }
    });

// To use this extension, do:
//  chrome.runtime.sendMessage(<ID>, {name: <RPC_NAME>, args: <ARGS>},
//    function(result) { ... deal with the results ... });
