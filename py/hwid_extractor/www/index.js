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


const challengeOrigin = 'https://chromeos.google.com';
const challengeURL = `${challengeOrigin}/partner/console/cr50reset`;
const allDevicesJsonUrl =
    ('https://storage.cloud.google.com/chromeos-build-release-console/' +
     'all_devices.json');
const configUpdateTimeout = 3000;
const defaultConfig /** Config */ = {
  extractAfterUnlocked: false,
  lockAfterExtracted: false,
  hartURL: '',
  board: '',
};
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
 * @param {!Node} ele
 * @param {string} text
 * @param {string} href
 * @param {string} target
 */
const renderLink = (ele, text, href, target) => {
  const a = ele.appendChild(document.createElement('a'));
  a.href = href;
  a.innerText = text;
  a.target = target;
  a.style = 'display: block; margin: 5px; padding: 5px;';
};

/**
 * @param {!Node} ele
 * @param {string} id
 * @param {string} label
 * @param {Function=} onchange
 */
const renderInput = (ele, id, label, onchange = (() => {})) => {
  const div = ele.appendChild(document.createElement('div'));
  div.style = 'margin: 5px; padding: 5px;';
  const labelTag = div.appendChild(document.createElement('label'));
  labelTag.innerText = label + ': ';
  labelTag.htmlFor = id;
  const input = div.appendChild(document.createElement('input'));
  input.id = id;
  const state_key = 'input_' + id;
  input.type = 'text';
  input.value = state[state_key] || '';
  input.onchange = e => {
    state[state_key] = e.target.value;
    onchange();
  };
};

/**
 * @param {!Node} ele
 * @param {string} id
 * @param {string} label
 * @param {!Array<string>} keys
 * @param {!Array<string>} values
 * @param {Function=} onchange
 */
const renderSelect = (ele, id, label, keys, values, onchange = (() => {})) => {
  const div = ele.appendChild(document.createElement('div'));
  div.style = 'margin: 5px; padding: 5px;';
  const labelTag = div.appendChild(document.createElement('label'));
  labelTag.innerText = label + ': ';
  labelTag.htmlFor = id;
  const select = div.appendChild(document.createElement('select'));
  for (let i = 0; i < keys.length; i++) {
    const option = select.appendChild(document.createElement('option'));
    option.innerText = keys[i];
    option.value = values[i];
  }
  select.id = id;
  const state_key = 'input_' + id;
  select.value = state[state_key] || '';
  select.onchange = e => {
    state[state_key] = e.target.value;
    onchange();
  };
};

/**
 * @param {!Node} ele
 * @param {string} id
 * @param {string} label
 * @param {Function=} onchange
 */
const renderCheckBox = (ele, id, label, onchange = (() => {})) => {
  const div = ele.appendChild(document.createElement('div'));
  div.style = 'margin: 5px; padding: 5px;';
  const input = div.appendChild(document.createElement('input'));
  input.id = id;
  const labelTag = div.appendChild(document.createElement('label'));
  labelTag.innerText = label;
  labelTag.htmlFor = id;
  const state_key = 'input_' + id;
  input.type = 'checkbox';
  input.checked = state[state_key] || false;
  input.onchange = e => {
    state[state_key] = e.target.checked;
    onchange();
  };
};

/**
 * @param {boolean} isTriggeredByUser
 */
const handleScan = async (isTriggeredByUser) => {
  setStateAndRender({isLoading: true, message: 'Scanning...'});
  const scanData = /** @type{ScanData} */ (await fetchAPI('/scan'));
  if (!scanData) return;
  let message = undefined;
  if (scanData.isRestricted && !scanData.challenge) {
    message = 'Cannot generate rma challenge!!! Try again.';
  } else if (isTriggeredByUser && scanData.isRestricted) {
    // Open RSU page automatically if the scanning is triggered by user.
    window.open(`${challengeURL}?challenge=${scanData.challenge}`, 'challenge');
  }
  setStateAndRender({
    scanData,
    extractData: undefined,
    message,
    input_authcode: undefined,
  });
  if (state.input_config_extractAfterUnlocked && !state.scanData.isRestricted) {
    await handleExtract();
  }
};

/**
 * @param {!Node} ele
 */
const renderScan = (ele) => {
  renderText(ele, 'Scan the device', 'h4');
  renderButton(ele, 'Scan', () => {
    handleScan(true);
  });
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
 * handleUnlock
 */
const handleUnlock = async () => {
  setStateAndRender({isLoading: true, message: 'Unlocking...'});
  const authcode = state.input_authcode;
  const data = /** @type{ActionResult} */ (await fetchAPI(
      '/unlock', {cr50SerialName: state.scanData.cr50SerialName, authcode}));
  if (!data) return;
  if (data.success) {
    /* Re-scan the device */
    await handleScan(false);
  } else {
    setStateAndRender({message: 'Unlock failed.'});
  }
};

/**
 * @param {!Node} ele
 */
const renderUnlock = (ele) => {
  renderText(ele, 'Unlock the device', 'h4');
  renderLink(
      ele, 'Get RSU Authcode',
      `${challengeURL}?challenge=${state.scanData.challenge}`, 'challenge');
  renderInput(ele, 'authcode', 'Authcode');
  renderButton(ele, 'Unlock', handleUnlock);
};

/**
 * handleExtract
 */
const handleExtract = async () => {
  setStateAndRender({isLoading: true, message: 'Extracting...'});
  let board = state.input_config_board;
  if (!board) {
    board = state.scanData.referenceBoard;
  }
  if (state.supportedBoards.indexOf(board) == -1) {
    setStateAndRender(
        {message: `Board "${board}" is not supported by HWID Extractor.`});
    return;
  }
  const extractData = /** @type{ExtractData} */ (await fetchAPI(
      '/extract', {cr50SerialName: state.scanData.cr50SerialName, board}));
  if (!extractData) return;
  setStateAndRender({extractData});
  const {sn, hwid} = extractData;
  if (state.input_config_hartURL && sn && hwid) {
    window.open(state.input_config_hartURL + `?sn=${sn}&hwid=${hwid}`, 'hart');
  }
  if (state.input_config_lockAfterExtracted) {
    await handleLock();
  }
};

/**
 * @param {!Node} ele
 */
const renderExtract = (ele) => {
  renderText(ele, 'Extract HWID and Serial No.', 'h4');
  renderButton(ele, 'Extract', handleExtract);
  renderTable(ele, state.extractData);
};

/**
 * handleLock
 */
const handleLock = async () => {
  setStateAndRender({isLoading: true, message: 'Locking...'});
  const data = /** @type{ActionResult} */ (
      await fetchAPI('/lock', {cr50SerialName: state.scanData.cr50SerialName}));
  if (!data) return;
  if (data.success) {
    /* Re-scan the device */
    await handleScan(false);
  } else {
    setStateAndRender({message: 'Lock failed.'});
  }
};

/**
 * @param {!Node} ele
 */
const renderLock = (ele) => {
  renderText(ele, 'Lock the device', 'h4');
  renderButton(ele, 'Lock', handleLock);
};

/**
 * @param {string} action
 * @return {!Function}
 */
const handleTestlab = (action) => async () => {
  setStateAndRender({
    isLoading: true,
    message: `Testlab ${action}... (Keep tapping the power button.)`
  });
  const data = /** @type{ActionResult} */ (await fetchAPI(
      `/testlab-${action}`, {cr50SerialName: state.scanData.cr50SerialName}));
  if (!data) return;
  if (data.success) {
    /* Re-scan the device */
    await handleScan(false);
  } else {
    setStateAndRender({message: `Failed to ${action} testlab.`});
  }
};

/**
 * @param {!Node} ele
 * @param {string} action
 */
const renderTestlab = (ele, action) => {
  renderText(ele, `Testlab ${action}`, 'h4');
  renderText(
      ele,
      `To ${action} testlab, click the button bellow, and then keep tapping ` +
          'the power button until the process finished.',
      'p');
  renderButton(ele, `Testlab ${action}`, handleTestlab(action));
};

let configUpdateTimerId = 0;
/**
 * handleUpdateConfig
 *
 * If the config has been changed, it will be sent to the server. If the content
 * change again in `configUpdateTimeout`, the last update is canceled and a new
 * one is started.
 */
const handleUpdateConfig = async () => {
  const config = {};
  for (let key in defaultConfig) {
    config[key] = state[`input_config_${key}`];
  }
  clearTimeout(configUpdateTimerId);
  configUpdateTimerId = setTimeout(async () => {
    await fetchAPI('/update-config', config);
  }, configUpdateTimeout);
};

/**
 * @param {!Node} ele
 */
const renderUpdateConfig = (ele) => {
  renderText(ele, 'General', 'h4');
  renderCheckBox(
      ele, 'config_extractAfterUnlocked', 'Extract After Unlocked',
      handleUpdateConfig);
  renderCheckBox(
      ele, 'config_lockAfterExtracted', 'Lock After Extracted',
      handleUpdateConfig);
  const keys = ['Auto Detect'].concat(state.supportedBoards || []);
  const values = [''].concat(state.supportedBoards || []);
  renderSelect(
      ele, 'config_board', 'Board to be extracted', keys, values,
      handleUpdateConfig);
  renderText(ele, 'Warning: Choose wrong board may damage the hardware!', 'b');
  renderInput(ele, 'config_hartURL', 'Hart URL', handleUpdateConfig);
};

/**
 * @param {!EventTarget} event
 */
const handleUpdateRLZ = async (event) => {
  let allDevicesJSON = {};
  try {
    const files = event.target.files;
    if (files.length === 0) return;
    const file = files[0];
    const text = await file.text();
    allDevicesJSON = /** @type{Object} */ (JSON.parse(text));
  } catch (err) {
    console.error(err);
    setStateAndRender({message: `Failed to parse all_devices.json: ${err}`});
    return;
  }
  setStateAndRender({isLoading: true, message: 'Updating RLZ data...'});
  const data = /** @type{ActionResult} */ (
      await fetchAPI('/update-rlz', allDevicesJSON));
  if (!data) return;
  if (data.success) {
    setStateAndRender({message: 'RLZ mapping data update successfully.'});
  } else {
    setStateAndRender({message: 'Failed to update RLZ mapping data.'});
  }
};

/**
 * @param {!Node} ele
 */
const renderUpdateRLZ = (ele) => {
  renderText(ele, 'RLZ Mapping data', 'h4');
  renderText(
      ele,
      'Download "all_devices.json" and upload it to HWID Extractor to update ' +
          'the RLZ mapping data.',
      'p');
  renderLink(ele, 'all_devices.json', allDevicesJsonUrl, 'all_devices.json');
  const input = ele.appendChild(document.createElement('input'));
  input.type = 'file';
  input.style = 'margin: 5px; padding: 5px;';
  input.onchange = handleUpdateRLZ;
  input.disabled = state.isLoading;
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
  if (state.scanData) {
    if (state.scanData.isRestricted) {
      renderUnlock(ele);
    } else {
      renderExtract(ele);
      if (state.scanData.isTestlabEnabled) {
        renderTestlab(ele, 'disable');
      } else {
        renderLock(ele);
        renderTestlab(ele, 'enable');
      }
    }
  }
  renderText(ele, 'Configuration', 'h3');
  renderUpdateConfig(ele);
  renderUpdateRLZ(ele);
};

/**
 * GetConfig
 */
const GetConfigAndRender = async () => {
  const newState = {};
  const data = /** @type{SupportedBoardsData} */ (
      await fetchAPI('/get-supported-boards'));
  if (!data) return;
  newState.supportedBoards = data.supportedBoards;

  // Set ?v= to prevent browser cache.
  let resp = await fetch(`/config.json?v=${Math.random()}`);
  let config = defaultConfig;
  if (resp.ok) {
    config = /** @type{Config} */ (await resp.json());
  }
  for (let key in defaultConfig) {
    newState[`input_config_${key}`] = config[key];
  }

  setStateAndRender(newState);
};

/**
 * @param {!Event} event
 */
const handleMessage = async (event) => {
  console.log(event);
  if (event.origin !== challengeOrigin) return;
  setStateAndRender({input_authcode: event.data});
  await handleUnlock();
};

/**
 * Onload
 */
window.onload = async () => {
  window.addEventListener('message', handleMessage, false);
  await GetConfigAndRender();
};
