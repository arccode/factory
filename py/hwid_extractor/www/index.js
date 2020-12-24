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
