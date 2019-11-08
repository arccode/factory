// Copyright 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.


const KIOSK_APP_ID = 'medehkfipnjknbpfgnjnhilclnpgnfmf';

// To use this extension, do:
//  chrome.runtime.sendMessage(<ID>, {name: <RPC_NAME>, args: <ARGS>},
//    function(result) { ... deal with the results ... });

chrome.runtime.onMessageExternal.addListener(
    (request, sender, sendResponse) => {
      if (request.name === 'CreateWindow') {
        chrome.windows.create(
            {'left': request.args.left, 'top': request.args.top},
            (win) => sendResponse(win));
        return true;  // indicate that we have async response.
      } else if (request.name === 'UpdateWindow') {
        chrome.windows.update(
            request.args.window_id, request.args.update_info,
            (win) => sendResponse(win));
        return true;
      } else if (request.name === 'RemoveWindow') {
        chrome.windows.remove(request.args.window_id, () => sendResponse(true));
        return true;
      } else if (request.name === 'QueryTabs') {
        chrome.tabs.query(
            {'windowId': request.args.window_id}, (tabs) => sendResponse(tabs));
        return true;
      } else if (request.name === 'UpdateTab') {
        chrome.tabs.update(
            request.args.tab_id, request.args.update_info,
            (tab) => sendResponse(tab));
        return true;
      } else if (request.name === 'TakeScreenshot') {
        chrome.tabs.captureVisibleTab(
            chrome.windows.WINDOW_ID_CURRENT, {format: 'png'},
            (url) => sendResponse({content : url, save_file : true}));
        return true;
      } else {  // Delegate the rest of the RPC calls to the kiosk app.
        chrome.runtime.sendMessage(KIOSK_APP_ID, request, sendResponse);
        return true;
      }
    });

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request === 'StartFactoryPage') {
    const promiseify = (func) => (...args) => new Promise((resolve) => {
      func(...args, (result) => resolve(result));
    });
    (async () => {
      const tabs = await promiseify(chrome.tabs.query)({url: sender.url});
      const tabId = tabs[0].id;
      // The debugger would detach itself when the tab is closed or the devtool
      // is opened.
      await promiseify(chrome.debugger.attach)({tabId}, '1.0');
      if (!chrome.runtime.lastError) {
        // Attach may fail because of the devtool is opened. Ignore that
        // case.
        await promiseify(chrome.debugger.sendCommand)(
            {tabId}, 'Network.enable');
      }
      await promiseify(chrome.tabs.update)(
          tabId, {url: 'http://localhost:4012'});
      sendResponse(true);
    })();
    return true;
  } else {
    window.console.log('Unknown RPC call', request);
  }
});

// Watch for created factory UI tabs, and reload them if:
// 1. The page is factory UI page (http://localhost:4012/...).
// 2. The page had been opened for less than 10 seconds.
// 3. Some request to static resource (/js/, /css/) returned with error.
// This would prevent most race condition while loading resources that can be
// solved by simple refreshing the tab. In particular, a race condition exists
// between the time index.html is loaded, goofy.js is loaded and the system
// detects external network dongle, which would cause the goofy.js request
// resulted with error ERR_NETWORK_CHANGED, causing goofy to be stucked in the
// loading page.

const tabLastLoadedTime = {};
const staticResourceRequestIds = new Set();
const MAX_RELOAD_TIME_MSEC = 10 * 1000;
const STATIC_RESOURCES = ['/js/', '/css/', '/images/'];

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'loading') {
    tabLastLoadedTime[tabId] = Date.now();
  }
});

const isFactoryStaticResource = (urlString) => {
  const url = new URL(urlString);
  return url.host === 'localhost:4012' &&
      (url.pathname === '/' ||
       STATIC_RESOURCES.some((prefix) => url.pathname.startsWith(prefix)));
};

// The debugger is attached in StartFactoryPage RPC call.
chrome.debugger.onEvent.addListener((source, method, params) => {
  let requestFailed = false;
  if (method === 'Network.requestWillBeSent') {
    if (isFactoryStaticResource(params.request.url)) {
      staticResourceRequestIds.add(params.requestId);
    }
  } else if (method === 'Network.requestServedFromCache') {
    staticResourceRequestIds.delete(params.requestId);
  } else if (method === 'Network.loadingFailed') {
    if (!staticResourceRequestIds.delete(params.requestId)) {
      return;
    }
    if (!params.canceled) {
      requestFailed = true;
    }
  } else if (method === 'Network.responseReceived') {
    if (!staticResourceRequestIds.delete(params.requestId)) {
      return;
    }
    if (params.response.status >= 400) {
      requestFailed = true;
    }
  }

  if (requestFailed) {
    const tabId = source.tabId;
    const lastLoadTime = tabLastLoadedTime[tabId];
    // The tabs.onUpdate event is fired after the error response to / is
    // received, so we also refresh the page if the lastLoadTime is not set.
    if (lastLoadTime && Date.now() - lastLoadTime > MAX_RELOAD_TIME_MSEC) {
      return;
    }
    console.log('request failed, reloading...', source, method, params);
    chrome.tabs.reload(tabId);
  }
});
