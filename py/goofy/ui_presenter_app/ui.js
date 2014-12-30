// Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

var myWindowName = 'goofy_presenter';
var connected = false;
var lastUuid = null;
var mySocket = null;

var countdown = {
  timeout: null,
  end_msg: null,
  end_msg_color: null,
  interval_id: null
};

function setMessage(msg, color) {
  msg_div = document.getElementById('goofy-message')
  msg_div.innerText = msg;
  msg_div.style.color = color;
}

function setInfo(msg) {
  setMessage(msg, "black");
}

function setError(msg) {
  setMessage(msg, "red");
}

function setDisplay(id, display) {
  document.getElementById(id).style.display = display;
}

function stopCountdown() {
  if (countdown.interval_id == null)
    return;
  window.clearInterval(countdown.interval_id);
  countdown.interval_id = null;
  setDisplay("goofy-countdown", "none");
}

function countdownCallback() {
  countdown_div = document.getElementById('goofy-countdown');
  if (countdown.timeout > 0) {
    countdown_div.innerText = countdown.timeout + " seconds remaining";
    setDisplay("goofy-countdown", "");
    countdown.timeout--;
  } else {
    stopCountdown();
    setMessage(countdown.end_msg, countdown.end_msg_color);
  }
}

function startCountdown(msg, timeout, end_msg, end_msg_color) {
  if (countdown.interval_id)
    stopCountdown();
  setInfo(msg);
  countdown.timeout = timeout;
  countdown.end_msg = end_msg;
  countdown.end_msg_color = end_msg_color;
  countdown.interval_id = window.setInterval(countdownCallback, 1000);
  countdownCallback();
}

function handleDisconnect() {
  if (connected) {
    /* Instead of destroying the UI, just hide it in case we need it later. */
    setDisplay('goofy-content', 'none');
    setDisplay('goofy-logo', '');
    setDisplay('goofy-message-container', '');
    connected = false;
  }
}

function handleConnect(serverUrl, serverUuid) {
  if (!connected) {
    /* Now that a device is connected, restore message and stop countdown. */
    stopCountdown();
    setInfo("Waiting for device...");

    var content = document.getElementById('goofy-content');
    /*
     * Only re-open the UI if it's not from the same session from the last
     * connection.
     */
    if (serverUuid != lastUuid) {
      content.src = serverUrl;
      lastUuid = serverUuid;
    }
    setDisplay('goofy-content', '');
    content.focus();
    setDisplay('goofy-logo', 'none');
    setDisplay('goofy-message-container', 'none');
    connected = true;
  }
}

function checkDUT(serverUrl, serverUuid) {
  var xmlHttp = new XMLHttpRequest();

  xmlHttp.timeout = 3000; /* ms */
  xmlHttp.ontimeout = handleDisconnect;
  xmlHttp.onerror = handleDisconnect;
  xmlHttp.onreadystatechange = function() {
    if (xmlHttp.readyState != 4)
      return;
    if (xmlHttp.status && xmlHttp.status < 400) {
      mySocket.send("OK");
      handleConnect(serverUrl, serverUuid);
    } else {
      mySocket.send("ERROR");
    }
  }

  xmlHttp.open("GET", serverUrl, true);
  xmlHttp.send(null);
}

function connectWebSocket() {
  // GoofyPresenter talks to us through port 4010. This port is only
  // used for communication between GoofyPresenter and the UI presenter
  // extension.
  mySocket = new WebSocket('ws://127.0.0.1:4010/');

  mySocket.onclose = function(e) {
    console.log("Web socket connection failed. Retry in 3 seconds...");
    setError("UI presenter backend disconnected. Retrying...");
    window.setTimeout(connectWebSocket, 3000);
  };
  mySocket.onmessage = function(e) {
    console.log("Server says:", e.data);
    message = JSON.parse(e.data);
    if (message.command == "DISCONNECT") {
      handleDisconnect();
    } else if (message.command == "CONNECT") {
      // Check the URL given by the backend and connect to it if
      // it's alive.
      checkDUT(message.url, message.uuid);
    } else if (message.command == "INFO") {
      // Show info message.
      setInfo(message.str);
    } else if (message.command == "ERROR") {
      // Show error message in red.
      setError(message.str);
    } else if (message.command == "START_COUNTDOWN") {
      // Start a countdown timer.  The argument is a JSON object with the
      // following attribute:
      //   message: Text to show during countdown.
      //   timeout: Timeout value in seconds.
      //   end_message: Text to show when countdown ends.
      //   end_message_color: The color of end_message.
      // An example for wait for the DUT to reboot:
      //   START_COUNTDOWN: {"message": "Waiting for DUT to reboot...",
      //                     "timeout": 180,
      //                     "end_message": "Reboot test failed!",
      //                     "end_message_color": "red"}
      startCountdown(message.message,
                     message.timeout,
                     message.end_message,
                     message.end_message_color);
    } else if (message.command == "STOP_COUNTDOWN") {
      // Aborts the current countdown.  Has no effect if there is no
      // countdown on-going.  Note that the message on the UI is not
      // cleared, so the backend must send "INFO" or "ERROR" to change
      // it.
      stopCountdown();
    } else {
      console.log("Unknown command:", e.data);
    }
  };
  mySocket.onopen = function(e) {
    console.log("Opened web socket");
    setInfo("Waiting for device...");
  };
  mySocket.onerror = function(e) { console.log(e); };
}

if (window.name != myWindowName) {
  window.name = myWindowName;
  location.reload();
} else {
  document.addEventListener('DOMContentLoaded', connectWebSocket);
}
