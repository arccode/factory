// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const createNumMismatchResult = (data) => {
  const title = document.getElementById('verify-component-mismatch-label');
  title.classList.remove('hidden');
  const numMismatch = document.getElementById('verify-component-mismatch');
  data.forEach(([comp_cls, expected_num, comp_names]) => {
    const content = document.createElement('div');
    const contentTitle = document.createElement('h2');
    contentTitle.appendChild(document.createTextNode(comp_cls));
    content.appendChild(contentTitle);
    const contentResult = document.createElement('div');
    contentResult.classList.add('verify-component-mismatch-result');
    const contentText = document.createElement('p');
    contentText.appendChild(document.createTextNode(
        `Expected ${expected_num} component(s)`));
    contentText.appendChild(document.createElement('br'));
    contentText.appendChild(document.createTextNode(
        `Found ${comp_names.length} component(s):`));
    contentResult.appendChild(contentText);
    const contentListBody = document.createElement('ul');
    comp_names.forEach((comp_name) => {
      const contentList = document.createElement('li');
      contentList.appendChild(document.createTextNode(comp_name));
      contentListBody.appendChild(contentList);
    });
    contentResult.appendChild(contentListBody);
    content.appendChild(contentResult);
    numMismatch.appendChild(content);
  });
};

const createNotSupportedResult = (data) => {
  const title = document.getElementById('verify-component-not-supported-label');
  title.classList.remove('hidden');
  const notSupported = document.getElementById(
      'verify-component-not-supported');
  notSupported.classList.remove('hidden');
  const tableBody = notSupported.querySelector('tbody');
  data.forEach((arr) => {
    const row = document.createElement('tr');
    arr.forEach((txt) => {
      const td = document.createElement('td');
      td.appendChild(document.createTextNode(txt));
      row.appendChild(td);
    });
    tableBody.appendChild(row);
  });
};

const setFailedMessage = () => {
  const probingMessage = document.getElementById('verify-component-probe');
  probingMessage.classList.add('hidden');
  const failedMessage = document.getElementById('verify-component-failed');
  failedMessage.classList.remove('hidden');
};

const exports = {
  createNumMismatchResult,
  createNotSupportedResult,
  setFailedMessage,
};

for (const key of Object.keys(exports)) {
  window[key] = exports[key];
}
