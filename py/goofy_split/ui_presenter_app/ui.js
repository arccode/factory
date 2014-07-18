// Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

var connected = false;

function stripXFrameOptions() {
  chrome.webRequest.onHeadersReceived.addListener(
    function(info) {
      var headers = info.responseHeaders;
      for (var i = headers.length - 1; i >= 0; --i) {
        var header = headers[i].name.toLowerCase();
        if (header == 'x-frame-options' || header == 'frame-options') {
          headers.splice(i, 1); // Remove header
        }
      }
      return {responseHeaders: headers};
    },
    {
      urls: [ '*://*/*' ], // Pattern to match all http(s) pages
      types: [ 'sub_frame' ]
    },
    ['blocking', 'responseHeaders']
  );
}

function setDisplay(id, display) {
  document.getElementById(id).style.display = display;
}

function handleDisconnect() {
  if (connected) {
    document.getElementById('goofy-content').src = "about:blank";
    setDisplay('goofy-logo', '');
    setDisplay('goofy-message-container', '');
    connected = false;
  }
}

function handleConnect(serverUrl) {
  if (!connected) {
    document.getElementById('goofy-content').src = serverUrl;
    setDisplay('goofy-logo', 'none');
    setDisplay('goofy-message-container', 'none');
    connected = true;
  }
}

function checkDUT(serverUrl) {
  var xmlHttp = new XMLHttpRequest();

  xmlHttp.timeout = 3000; /* ms */
  xmlHttp.ontimeout = handleDisconnect;
  xmlHttp.onerror = handleDisconnect;
  xmlHttp.onreadystatechange = function() {
    if (xmlHttp.readyState != 4)
      return;
    if (xmlHttp.status && xmlHttp.status < 400)
      handleConnect(serverUrl);
  }

  xmlHttp.open("GET", serverUrl, true);
  xmlHttp.send(null);
}

function connectWebSocket() {
  // GoofyPresenter talks to us through port 4010. This port is only
  // used for communication between GoofyPresenter and the UI presenter
  // extension.
  var my_socket = new WebSocket('ws://127.0.0.1:4010/');

  my_socket.onclose = function(e) {
    console.log("Web socket connection failed. Retry in 3 seconds...");
    window.setTimeout(connectWebSocket, 3000);
  };
  my_socket.onmessage = function(e) {
    console.log("Server says:", e.data);
    if (e.data == "DISCONNECT")
      handleDisconnect();
    else
      checkDUT(e.data);
  };
  my_socket.onopen = function(e) { console.log("Opened web socket"); };
  my_socket.onerror = function(e) { console.log(e); };
}

stripXFrameOptions();
document.addEventListener('DOMContentLoaded', connectWebSocket);
