// Copyright 2021 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * @typedef {{
 *  cr50SerialName: string,
 *  referenceBoard: (string|null),
 *  challenge: (string|null),
 *  isRestricted: boolean,
 *  isTestlabEnabled: (boolean|null),
 * }}
 */
let ScanData;
/**
 * @typedef {{
 *  hwid: string,
 *  sn: string,
 * }}
 */
let ExtractData;
/**
 * @typedef {{
 *  supportedBoards: (!Array<string>),
 * }}
 */
let SupportedBoardsData;
/**
 * @typedef {{
 *  success: (boolean|undefined),
 * }}
 */
let ActionResult;
/**
 * @typedef {{
 *  extractAfterUnlocked: boolean,
 *  lockAfterExtracted: boolean,
 *  hartURL: string,
 * }}
 */
let Config;
/**
 * @typedef {{
 *  supportedBoards: (!Array<string>|undefined),
 *  scanData: (!ScanData|undefined),
 *  extractData: (!ExtractData|undefined),
 *  errorData: (!Object|undefined),
 *  isLoading: (boolean|undefined),
 *  message: (string|undefined),
 *  input_authcode: (string|undefined),
 *  input_config_board: (string|undefined),
 *  input_config_extractAfterUnlocked: (boolean|undefined),
 *  input_config_lockAfterExtracted: (boolean|undefined),
 *  input_config_hartURL: (string|undefined),
 * }}
 */
let State;


const state /** State */ = {};


/**
 * @param {State} newState
 */
const setStateAndRender = (newState) => {
  if (!('message' in newState)) {
    newState.message = undefined;
  }
  if (!('isLoading' in newState)) {
    newState.isLoading = false;
  }
  if (!('errorData' in newState)) {
    newState.errorData = undefined;
  }
  Object.assign(state, newState);
  try {
    render(/** @type{!Node} */ (document.getElementById('root')));
  } catch (error) {
    console.error(error);
    alert(error);
  }
};

/**
 * @param {string} path
 * @param {Object=} data
 * @return {Object}
 */
const fetchAPI = async (path, data = {}) => {
  try {
    const resp = await fetch(path, /** @type{!RequestInit} */ ({
                               method: 'POST',
                               headers: {'Content-Type': 'application/json'},
                               body: JSON.stringify(data)
                             }));
    const resData = await resp.json();
    if (resp.status === 200) return resData;
    setStateAndRender({errorData: resData});
    return null;
  } catch (error) {
    setStateAndRender({errorData: {error: error.toString()}});
    return null;
  }
};

/**
 * @param {boolean|undefined} value
 * @param {string} trueText
 * @param {string} trueColor
 * @param {string} falseText
 * @param {string} falseColor
 * @return {Node}
 */
const getBooleanText = (value, trueText, trueColor, falseText, falseColor) => {
  const ele = document.createElement('span');
  if (value === undefined) {
    ele.innerText = 'undefined';
  } else {
    ele.innerText = value ? trueText : falseText;
    ele.style.color = value ? trueColor : falseColor;
  }
  return ele;
};

/**
 * @param {!Node} ele
 * @param {!Object<string,(string|!Node)>} data
 */
const renderTable = (ele, data) => {
  if (!data) return;
  const table = ele.appendChild(document.createElement('table'));
  table.style = 'border: 1px solid black; margin: 5px';
  for (let key in data) {
    const style = 'border: 1px solid black; padding: 5px';
    const tr = table.appendChild(document.createElement('tr'));
    const tdKey = tr.appendChild(document.createElement('td'));
    tdKey.style = style;
    tdKey.innerText = key;
    const tdValue = tr.appendChild(document.createElement('td'));
    tdValue.style = style;
    if (!data[key]) continue;
    if (typeof data[key] === 'string') {
      tdValue.innerText = data[key];
    } else {
      tdValue.appendChild(/** @type{!Node} */ (data[key]));
    }
  }
};

/**
 * @param {!Node} ele
 * @param {string} text
 * @param {!Function} onclick
 */
const renderButton = (ele, text, onclick) => {
  const btn = ele.appendChild(document.createElement('button'));
  if (state.isLoading) {
    text += ' (Loading...)';
  }
  btn.innerText = text;
  btn.onclick = onclick;
  btn.disabled = state.isLoading;
  btn.style = 'margin: 5px; padding: 5px';
};

/**
 * @param {!Node} ele
 * @param {string} text
 * @param {string=} type
 */
const renderText = (ele, text, type = 'span') => {
  const span = ele.appendChild(document.createElement(type));
  span.innerText = text;
  if (type[0] == 'h') {
    const hr = ele.appendChild(document.createElement('hr'));
    hr.style = 'margin: -10px 0 20px 0;';
  } else {
    span.style = 'margin: 5px; padding: 5px;';
  }
};

/**
 * @param {Event=} event
 */
const handleScan = async (event) => {
  setStateAndRender({isLoading: true, message: 'Scanning...'});
  const scanData = /** @type{ScanData} */ (await fetchAPI('/scan'));
  if (!scanData) return;
  let message = undefined;
  if (scanData.isRestricted && !scanData.challenge) {
    message = 'Cannot generate rma challenge!!! Try again.';
  }
  setStateAndRender({
    scanData,
    extractData: undefined,
    message,
    input_authcode: undefined,
  });
};

/**
 * @param {!Node} ele
 */
const renderScan = (ele) => {
  renderText(ele, 'Scan the device', 'h4');
  renderButton(ele, 'Scan', handleScan);
  if (!state.scanData) return;
  const {
    cr50SerialName,
    rlz,
    referenceBoard,
    isRestricted,
    isTestlabEnabled,
  } = state.scanData;
  renderTable(ele, {
    'Cr50 Serial Name': cr50SerialName,
    'RLZ Code': rlz,
    'Reference Board': getBooleanText(
        state.supportedBoards.indexOf(referenceBoard) != -1,
        `${referenceBoard} (Supported)`, 'green',
        `${referenceBoard} (Not Supported)`, 'red'),
    'CCD State':
        getBooleanText(isRestricted, 'Locked', 'red', 'Opened', 'green'),
    'Testlab State':
        getBooleanText(isTestlabEnabled, 'Enabled', 'green', 'Disabled', 'red'),
  });
};

/**
 * @param {!Node} ele
 */
const render = (ele) => {
  while (ele.firstChild) {
    ele.removeChild(ele.lastChild);
  }
  renderText(ele, 'HWID Extractor', 'h2');
  if (state.message) {
    renderText(ele, state.message, 'p');
  }
  if (state.errorData) {
    renderTable(ele, state.errorData);
  }
  renderScan(ele);
};

/**
 * GetConfig
 */
const GetConfigAndRender = async () => {
  const newState = {};
  let resp = await fetch('/supported_boards.json');
  if (resp.ok) {
    const data = /** @type{SupportedBoardsData} */ (await resp.json());
    newState.supportedBoards = data.supportedBoards;
  }
  setStateAndRender(newState);
};

/**
 * Onload
 */
window.onload = async () => {
  await GetConfigAndRender();
};
