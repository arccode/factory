// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for summary test.
 */
window.SummaryTest = class {
  constructor() {
    this._STATUS_LABELS = {
        PASSED: _('passed'),
        FAILED: _('failed'),
        ACTIVE: _('active'),
        UNTESTED: _('untested')};

    this._comps = this._bindUIComps([
        'prompt-message-container',
        'test-name',
        'test-status-label',
        'test-results-table'
    ]);
  }

  setPromptMessage(i18nMessage, isPass) {
    const createElementForPass = () => {
      const elem = document.createElement('a');
      elem.setAttribute('href', '#');
      elem.addEventListener('click', () => window.test.pass());
      return elem;
    };
    const createElementForNotPass = () => document.createElement('div');

    const elem = isPass ? createElementForPass() : createElementForNotPass();

    goog.dom.safe.setInnerHtml(elem, cros.factory.i18n.i18nLabel(i18nMessage));

    this._comps.promptMessageContainer.innerHTML = '';
    this._comps.promptMessageContainer.appendChild(elem);
  }

  setTestName(testName) {
    const i18nDict = window._('Test Status for {testName}:',
                              {testName: testName});
    goog.dom.safe.setInnerHtml(
        this._comps.testName, window.cros.factory.i18n.i18nLabel(i18nDict));
  }

  setOverallTestStatus(overallStatus) {
    goog.dom.safe.setInnerHtml(
        this._comps.testStatusLabel,
        cros.factory.i18n.i18nLabel(this._STATUS_LABELS[overallStatus]));
    this._comps.testStatusLabel.setAttribute(
        'class', this._getTestStatusClass(overallStatus));
  }

  setDetailTestResults(detailResults) {
    const appendTestResult = (label, status) => {
      const tr = document.createElement('tr');
      tr.classList.add(this._getTestStatusClass(status));

      const th = document.createElement('th');
      goog.dom.safe.setInnerHtml(th, cros.factory.i18n.i18nLabel(label));

      const td = document.createElement('td');
      goog.dom.safe.setInnerHtml(
          td, cros.factory.i18n.i18nLabel(this._STATUS_LABELS[status]));

      tr.appendChild(th);
      tr.appendChild(td);
      this._comps.testResultsTable.appendChild(tr);
    };

    for (const detailResult of detailResults) {
      appendTestResult(detailResult.label, detailResult.status);
    }
  }

  enableAccessibility() {
    window.template.classList.add('test-accessibility');
  }

  _bindUIComps(elemIds) {
    const ret = {};
    for (const elemId of elemIds) {
      ret[goog.string.toCamelCase(elemId)] = document.getElementById(elemId);
    }
    return ret;
  }

  _getTestStatusClass(status) {
    return 'test-status-' + status.replace(/_/g, '-');
  }
};
