// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const createNumMismatchResult = (data, approxMatch, probedResults) => {
  const title = document.getElementById('verify-component-mismatch-label');
  title.classList.remove('hidden');
  const numMismatch = document.getElementById('verify-component-mismatch');
  data.forEach(([compCls, expectedNum, compNames]) => {
    const content = document.createElement('div');
    const contentTitle = document.createElement('h2');
    contentTitle.appendChild(document.createTextNode(compCls));
    content.appendChild(contentTitle);
    const contentResult = document.createElement('div');
    contentResult.classList.add('verify-component-mismatch-result');
    const contentText = document.createElement('p');
    contentText.appendChild(document.createTextNode(
        `Expected ${expectedNum} component(s)`));
    contentText.appendChild(document.createElement('br'));
    contentText.appendChild(document.createTextNode(
        `Found ${compNames.length} component(s):`));
    contentResult.appendChild(contentText);
    const contentListBody = document.createElement('ul');
    compNames.forEach((compName) => {
      const contentList = document.createElement('li');
      contentList.appendChild(document.createTextNode(compName));
      contentListBody.appendChild(contentList);
    });
    contentResult.appendChild(contentListBody);
    if (approxMatch) {
      createApproxMatchResult(contentResult, probedResults[compCls]);
    }
    content.appendChild(contentResult);
    numMismatch.appendChild(content);
  });
};

const createApproxMatchResult = (contentResult, compInfo) => {
  const approxText = document.createElement('p');
  approxText.appendChild(document.createTextNode(
      'Found almost matched components(s):'));
  contentResult.appendChild(approxText);
  compInfo.forEach((comp) => {
    if (!comp.perfect_match) {
      const approxResult = document.createElement('div');
      const approxCompName = document.createElement('h2');
      approxCompName.appendChild(document.createTextNode(comp['name']));
      approxResult.appendChild(approxCompName);
      const approxListBody = document.createElement('ul');
      const rules = comp.approx_match.rule;
      for (const rule in rules) {
        if (!rules[rule].result) {
          const approxList = document.createElement('li');
          approxList.appendChild(document.createTextNode(
              `${rule}: ${rules[rule].info}, found: ${comp.values[rule]}`));
          approxListBody.append(approxList);
        }
      }
      approxResult.appendChild(approxListBody);
      contentResult.appendChild(approxResult)
    }
  });
}

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
