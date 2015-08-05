// Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

var myWindowName = 'goofy_presenter';
var mySocket = null;
var macAddressList = [];
var connectedDongle = [];
var lock = false;

var countdown = {}

function setMessage(msg, color, dongle_mac_address) {
  // if the dongle_mac_address is undefined, set msg to default UI message
  if (dongle_mac_address) {
    msg_div = document.getElementById(dongle_mac_address + '_goofy-message')
  } else {
    msg_div = document.getElementById('goofy-message')
  }

  msg_div.innerText = msg;
  msg_div.style.color = color;
}

function setInfo(msg, dongle_mac_address) {
  setMessage(msg, "black", dongle_mac_address);
}

function setError(msg, dongle_mac_address) {
  setMessage(msg, "red", dongle_mac_address);
}

function setDisplay(id, display) {
  document.getElementById(id).style.display = display;
}

function stopCountdown(dongle_mac_address) {
  if (!(dongle_mac_address in countdown))
    return;
  window.clearInterval(countdown[dongle_mac_address].interval_id);
  delete countdown[dongle_mac_address];
}

function countdownCallback(dongle_mac_address) {
  countdown_div = document.getElementById(dongle_mac_address
                                          + '_goofy-countdown');
  if (countdown[dongle_mac_address].timeout > 0) {
    countdown_div.innerText = countdown[dongle_mac_address].timeout
                              + " seconds remaining";
    countdown[dongle_mac_address].timeout--;
  } else {
    setMessage(countdown[dongle_mac_address].end_msg,
               countdown[dongle_mac_address].end_msg_color,
               dongle_mac_address);
    countdown_div.innerText = "";
    stopCountdown(dongle_mac_address);
  }
}

function startCountdown(msg, dongle_mac_address, timeout, end_msg,
                        end_msg_color) {
  if (dongle_mac_address in countdown)
    stopCountdown(dongle_mac_address);

  setInfo(msg, dongle_mac_address);

  var iframe = document.getElementById(dongle_mac_address + "_iframe");
  iframe.src = 'about:blank';

  countdown[dongle_mac_address] = {
    timeout: null,
    end_msg: null,
    end_msg_color: null,
    interval_id: null
  };
  countdown[dongle_mac_address].timeout = timeout;
  countdown[dongle_mac_address].end_msg = end_msg;
  countdown[dongle_mac_address].end_msg_color = end_msg_color;
  countdown[dongle_mac_address].interval_id = window.setInterval(function() {
    countdownCallback(dongle_mac_address);
  }, 1000);
  countdownCallback(dongle_mac_address);

  setDisplay(dongle_mac_address + '_countdown-container', '');
  setDisplay(dongle_mac_address + '_iframe', 'none');
}

function handleDisconnect(dongle_mac_address) {
  if (dongle_mac_address in countdown)
    return

  if (connectedDongle.indexOf(dongle_mac_address) != -1) {
    var index = macAddressList.indexOf(dongle_mac_address);
    if (lock) {
      var iframe = document.getElementById(dongle_mac_address + "_iframe");
      iframe.src = 'about:blank';
      iframe.onload = function() {
        $("#tabs").tabs("disable", '#' + dongle_mac_address);
      };
      var tab = document.getElementById(dongle_mac_address + "_list");
      tab.style.backgroundColor = "#fff";
    } else {
      document.getElementById(dongle_mac_address).remove();
      document.getElementById(dongle_mac_address + "_list").remove();

      macAddressList.splice(index, 1);

      if (macAddressList.length == 0) {
        /* Instead of destroying UI, just hide it in case we need it later. */
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
    /* new device connected */
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
      newTabContent.className = 'goofy-content';
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

      /* for countdown message */
      var logo = document.createElement('div');
      logo.className = "goofy-countdown-logo";

      var countdownMessage = document.createElement('div');
      countdownMessage.className = "countdown-message";
      countdownMessage.id = dongle_mac_address + "_goofy-message";

      var goofyCountdown = document.createElement('div');
      goofyCountdown.className = "goofy-countdown";
      goofyCountdown.id = dongle_mac_address + "_goofy-countdown";

      /* for vertical align */
      var centerAligned = document.createElement('div');
      centerAligned.className = "center-aligned";

      var countdownContainer = document.createElement('div');
      countdownContainer.id = dongle_mac_address + "_countdown-container";

      countdownContainer.appendChild(logo);
      countdownContainer.appendChild(centerAligned);
      countdownContainer.appendChild(countdownMessage);
      countdownContainer.appendChild(goofyCountdown);

      newTabContent.appendChild(countdownContainer);
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
  setDisplay(dongle_mac_address + "_countdown-container", 'none');
}

function updateTabColor(dongle_mac_address, all_pass) {
  var tab = document.getElementById(dongle_mac_address + "_list");
  if (all_pass) {
    tab.style.background = '#C8FFC8';
  } else {
    tab.style.backgroundColor = '#FFC8C8';
  }
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
    /* Instead of destroying UI, just hide it in case we need it later. */
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
      //   dongle_mac_address: dongle mac address of the DUT to reboot.
      //   timeout: Timeout value in seconds.
      //   end_message: Text to show when countdown ends.
      //   end_message_color: The color of end_message.
      // An example for wait for the DUT to reboot:
      //   START_COUNTDOWN: {"message": "Waiting for DUT to reboot...",
      //                     "dongle_mac_address": "00:f7:6f:6e:d2:f8",
      //                     "timeout": 180,
      //                     "end_message": "Reboot test failed!",
      //                     "end_message_color": "red"}

      startCountdown(message.message,
                     message.dongle_mac_address,
                     message.timeout,
                     message.end_message,
                     message.end_message_color);
    } else if (message.command == "STOP_COUNTDOWN") {
      // Aborts the specific countdown.  Has no effect if the specific
      // countdown is not on-going.

      stopCountdown(message.dongle_mac_address);
    } else if (message.command == "UPDATE_STATUS") {
      // When a DUT finish tests, update the color of its tab.
      updateTabColor(message.dongle_mac_address, message.all_pass);
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
