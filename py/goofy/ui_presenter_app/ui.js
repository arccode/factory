// Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

var myWindowName = 'goofy_presenter';
var mySocket = null;
var macAddressList = [];
var connectedDongle = [];
var lock = false;

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

function countdownCallback(dongle_mac_address) {
  countdown_div = document.getElementById(dongle_mac_address + '_goofy-countdown');
  if (countdown[dongle_mac_address].timeout > 0) {
    countdown_div.innerText = countdown[dongle_mac_address].timeout + " seconds remaining";
    countdown[dongle_mac_address].timeout--;
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

function handleDisconnect(dongle_mac_address) {
  if (connectedDongle.indexOf(dongle_mac_address) != -1) {
    var index = macAddressList.indexOf(dongle_mac_address);
    if (lock) {
      var iframe = document.getElementById(dongle_mac_address + "_iframe");
      iframe.src = 'about:blank';
      iframe.onload = function() {
        $("#tabs").tabs("disable", '#' + dongle_mac_address);
      };
    } else {
      document.getElementById(dongle_mac_address).remove();
      document.getElementById(dongle_mac_address + "_list").remove();

      macAddressList.splice(index, 1);

      if (macAddressList.length == 0) {
        /* Instead of destroying the UI, just hide it in case we need it later. */
        setDisplay('tabs', 'none');
        setDisplay('goofy-logo', '');
        setDisplay('goofy-message-container', '');
      }
    }

    $('#tabs').tabs('refresh');
    connectedDongle.splice(connectedDongle.indexOf(dongle_mac_address), 1);

    var flag = false;
    if ($("#tabs").tabs('option', 'active') == index) {
      for (var i = index - 1; i >= 0; i--) {
        var address = macAddressList[i];
        if (connectedDongle.indexOf(address) != -1) {
          $('#tabs').tabs('option', 'active', i);
          flag = true;
          break;
        }
      }
      if (!flag) {
        for (var i = index; i < macAddressList.length; i++) {
          var address = macAddressList[i];
          if (connectedDongle.indexOf(address) != -1) {
            $('#tabs').tabs('option', 'active', i);
            break;
          }
        }
      }
    }
  }
}

function handleConnect(serverUrl, dongle_mac_address) {
  if (connectedDongle.indexOf(dongle_mac_address) == -1) {
    //TODO(tientzu): get dongle address, and start countdown
    stopCountdown();
    setInfo("Waiting for device...");

    connectedDongle.push(dongle_mac_address);

    if (macAddressList.length == 0) {
      setDisplay('tabs', '');
      setDisplay('goofy-logo', 'none');
      setDisplay('goofy-message-container', 'none');
    }

    if (lock) {
      if (macAddressList.indexOf(dongle_mac_address) == -1) {
        alert("Can't add device under lock.");
        return;
      } else {
        var iframe = document.getElementById(dongle_mac_address + "_iframe");
        iframe.src = serverUrl;
        iframe.onload = function() {
          var index = macAddressList.indexOf(dongle_mac_address);
          $("#tabs").tabs("enable", '#' + dongle_mac_address);
          $('#tabs').tabs('option', 'active', index);
          iframe.focus();
        };
      }
    } else {
      macAddressList.push(dongle_mac_address);

      var tabs = document.getElementById('tab-names');
      var newLi = document.createElement('li');
      newLi.id = dongle_mac_address + "_list";
      var newTab = document.createElement('a');
      newTab.id = dongle_mac_address + "_name";
      newTab.href = '#' + dongle_mac_address;
      newTab.innerHTML = "device";

      newLi.appendChild(newTab);
      tabs.appendChild(newLi);

      var tabContents = document.getElementById("tab-contents");
      var newTabContent = document.createElement('div');
      newTabContent.id = dongle_mac_address;
      var iframe = document.createElement("IFRAME");

      iframe.src = serverUrl;
      iframe.id = dongle_mac_address + "_iframe";
      iframe.onload = function() {
        var index = macAddressList.indexOf(dongle_mac_address);
        $('#tabs').tabs('refresh');
        $('#tabs').tabs('option', 'active', index);
        iframe.focus();
      };

      newTabContent.appendChild(iframe);
      tabContents.appendChild(newTabContent);

      if (dongle_mac_address == 'standalone'){
        /* in standalone mode, hide the tabs */
        logo.style.height = "100%";
        tabContents.style.height = "100%";
        setDisplay('tab-names', 'none');
      }
    }
  } else {
    /* successfully rebooted or reconnected after reboot fail */
    stopCountdown(dongle_mac_address);
    var iframe = document.getElementById(dongle_mac_address + "_iframe");
    iframe.src = serverUrl;
    iframe.onload = function() {
      var index = macAddressList.indexOf(dongle_mac_address);
      $("#tabs").tabs("enable", '#' + dongle_mac_address);
      $('#tabs').tabs('option', 'active', index);
      iframe.focus();
    };
  }

  setDisplay(dongle_mac_address + "_iframe", '');
  setDisplay(dongle_mac_address + "_logo", 'none');
  setDisplay(dongle_mac_address + "_goofy-countdown", 'none');
  setDisplay(dongle_mac_address + "_goofy-message", 'none');
}

function lockTabs() {
  for (var i = 0; i < macAddressList.length; i++) {
    var dongle_mac_address = macAddressList[i];
    var tab = document.getElementById(dongle_mac_address + "_name");
    tab.innerHTML = "device " + (i + 1);
  }
}

function unlockTabs() {
  for (var i = 0; i < macAddressList.length; i++) {
    var dongle_mac_address = macAddressList[i];
    if (connectedDongle.indexOf(dongle_mac_address) != -1) {
      var tab = document.getElementById(dongle_mac_address + "_name");
      tab.innerHTML = "device";
    } else {
      document.getElementById(dongle_mac_address).remove();
      document.getElementById(dongle_mac_address + "_list").remove();
      macAddressList.splice(i, 1);
      i--;
    }
  }
  if (macAddressList.length == 0) {
    /* Instead of destroying the UI, just hide it in case we need it later. */
    setDisplay('tabs', 'none');
    setDisplay('goofy-logo', '');
    setDisplay('goofy-message-container', '');
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

  $("#tabs").tabs();
  setDisplay('tabs', 'none');
  var button = document.getElementById('lock');
  button.onclick = function() {
    if (button.innerHTML == "Lock") {
      button.innerHTML = "Unlock";
      lock = true;
      lockTabs();
    } else {
      button.innerHTML = "Lock";
      lock = false;
      unlockTabs();
    }
  };

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
      handleDisconnect(message.dongle_mac_address);
    } else if (message.command == "CONNECT") {
      // Check the URL given by the backend and connect to it if
      // it's alive.
      checkDUT(message.url, message.dongle_mac_address);
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

      //TODO(tientzu): get dongle address, and start countdown
      startCountdown(message.message,
                     message.timeout,
                     message.end_message,
                     message.end_message_color);
    } else if (message.command == "STOP_COUNTDOWN") {
      // Aborts the current countdown.  Has no effect if there is no
      // countdown on-going.  Note that the message on the UI is not
      // cleared, so the backend must send "INFO" or "ERROR" to change
      // it.

      //TODO(tientzu): get dongle address, and stop countdown, removing tab
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
