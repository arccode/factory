// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for retrieve parameter test.
 */
window.RetrieveParameterTest = class {
  constructor() {
    this._comps = this._bindUIComps([
        'status',
        'downloaded-file',
        'error'
    ]);
  }

  displayError(message) {
    this._comps.error.innerText = message;
  }

  displayStatus(message) {
    this._comps.status.innerText = message;
  }

  displayAppendFiles(message) {
    const elem = document.createElement('span');
    elem.innerText = message;
    this._comps.downloadedFile.appendChild(elem);
  }

  _bindUIComps(elemIds) {
    const ret = {};
    for (const elemId of elemIds) {
      ret[goog.string.toCamelCase(elemId)] = document.getElementById(elemId);
      ret[goog.string.toCamelCase(elemId)].innerHTML = '';
    }
    return ret;
  }
};
