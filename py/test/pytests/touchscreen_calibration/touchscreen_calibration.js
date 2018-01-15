// Copyright 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const RED = '#F55';
const GREEN = '#5F5';

const toggleDebugPanel = () => {
  document.getElementById('debug-panel').classList.toggle('hidden');
};

const snEntered = () => {
  const sn = document.getElementById('sn').value;
  if (sn.length > 0) {
    window.test.sendTestEvent('StartCalibration', {sn});
    document.getElementById('sn').value = '';
    document.getElementById('display-area').innerHTML = '';
  } else {
    window.test.alert(_('Please enter SN'));
  }
};

const fillInSerialNumber = (sn) => {
  const elm = document.getElementById('sn');
  elm.value = sn;
  elm.style.backgroundColor = GREEN;
};

const displayDebugData = (data) => {
  const displayArea = document.getElementById('display-area');
  displayArea.innerHTML = '';
  const max = Math.max(...data.map((row) => Math.max(...row)));
  const min = Math.min(...data.map((row) => Math.min(...row)));

  for (const rowData of data) {
    const row = document.createElement('div');
    for (const value of rowData) {
      const cell = document.createElement('span');
      const scaledValue = Math.floor(255 * (value - min) / (max - min));
      cell.innerHTML = '__';
      cell.style.backgroundColor = heatMap(scaledValue);
      cell.style.fontSize = '0.7em';
      row.appendChild(cell);
    }
    displayArea.insertBefore(row, displayArea.childNodes[0]);
  }
};

const heatMap = (val) => {
  let r = 0;
  let g = 0;
  let b = 0;
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
  return `rgb(${r},${g},${b})`;
};

const setStatus = (id, status, success) => {
  const elm = document.getElementById(id);
  elm.innerText = status;
  elm.style.backgroundColor = success ? GREEN : RED;
};

const setControllerStatus = (status) =>
    setStatus('controller-status', status ? 'Detected' : 'Undetected', status);

const setTouchscreenStatus = (status) =>
    setStatus('touchscreen-status', status ? 'Detected' : 'Undetected', status);

const showProbeState = (state) => setStatus('probe-state', state, true);

const setHostNetworkStatus = (ip) =>
    setStatus('host-network-status', ip, ip === 'False');

const setBBNetworkStatus = (ip) =>
    setStatus('bb-network-status', ip, ip === 'False');

const setShopfloorNetworkStatus = (ip) =>
    setStatus('shopfloor-network-status', ip, ip === 'False');

window.test.sendTestEvent('RefreshFixture');
window.test.sendTestEvent('RefreshTouchscreen');

document.getElementById('sn').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    snEntered();
  }
});
document.getElementById('sn-button').addEventListener('click', snEntered);

const exports = {
  toggleDebugPanel,
  fillInSerialNumber,
  displayDebugData,
  setControllerStatus,
  setTouchscreenStatus,
  showProbeState,
  setHostNetworkStatus,
  setBBNetworkStatus,
  setShopfloorNetworkStatus
};
for (const key of Object.keys(exports)) {
  window[key] = exports[key];
}
