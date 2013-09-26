// Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

window.onload = init();
window.onkeydown = function(event){
  switch(event.keyCode) {
    case 68: // Hotkey d
      var debugPanel = document.getElementById("debug-panel");
      var v = debugPanel.style.visibility;
      if (v.toLowerCase() == "visible" || v == "") {
        debugPanel.style.visibility = "hidden";
      } else {
        debugPanel.style.visibility = "visible";
      }
      break;
    default:
      break;
  }
}

function snEntered(event) {
  if (event.keyCode == 13) {
    var sn = document.getElementById('sn').value;
    if (sn.length > 0) {
      test.sendTestEvent('StartCalibration',
          {'sn': document.getElementById('sn').value});
      document.getElementById('sn').value = "";
      document.getElementById('display-area').innerHTML = "";
    } else {
      alert("Please enter SN 请输入序号");
    }
  }
}

function init() {
  test.sendTestEvent('RefreshFixture', {});
  test.sendTestEvent('RefreshTouchscreen', {});
}

function displayDebugData(data) {
  var data = eval(data)
  var displayArea = document.getElementById('display-area');
  displayArea.innerHTML = "";
  var max = -1;
  var min = -1;

  for (var i = 0; i < data.length; i++) {
    for (var j = 0; j < data[i].length; j++) {
      if (min == -1 || min > data[i][j]) {
        min = data[i][j];
      }
      if (max == -1 || max < data[i][j]) {
        max = data[i][j];
      }
    }
  }

  for (var i = 0; i < data.length; i++) {
    var row = document.createElement('div');
    for (var j = 0; j < data[i].length; j++) {
      var cell = document.createElement('span');
      var value = data[i][j];
      value = Math.floor(255 * (value - min) / (max - min));
      cell.innerHTML = "__";
      cell.style.backgroundColor = heatMap(value);
      cell.style.fontSize = "0.8em";
      row.appendChild(cell);
    }
    displayArea.insertBefore(row, displayArea.childNodes[0]);
  }
}

function heatMap(val) {
  r = 0;
  g = 0;
  b = 0;
  if (val <= 255 && val >= 235) {
    r = val;
    g = (255 - val) * 12;
  } else if (val <= 234 && val >= 200) {
    r = 255 - (234 - val) * 8;
    g = 255;
  } else if (val <= 199 && val >= 150) {
    g = 255;
    b = (199 - val) * 5;
  } else if (val <= 149 && val >= 100) {
    g = 255 - (149 - val) * 5;
    b = 255;
  } else {
    b = 255;
  }
  return "rgb(" + r + "," + g + "," + b + ")";
}

function showMessage(data) {
  alert(data);
}

function setControllerStatus(status) {
  var elm = document.getElementById('controller-status')
  elm.innerText = status ? 'Detected' : 'Undetected';
  elm.style.backgroundColor = status ? '#5F5' : '#F55';
}

function setTouchscreenStatus(status) {
  var elm = document.getElementById('touchscreen-status');
  elm.innerText = status ? 'Detected' : 'Undetected';
  elm.style.backgroundColor = status ? '#5F5' : '#F55';
}
