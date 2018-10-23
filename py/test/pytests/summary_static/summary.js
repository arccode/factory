// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const _SCREENSAVER_ITERATION_MSECS = 50;
const _NUM_SCREENSAVER_MSG_STYLES = 3;


/**
 * API for summary test.
 */
window.SummaryTest = class {
  constructor(screensaverTimeout) {
    this._STATUS_LABELS = {
        PASSED: _('passed'),
        FAILED: _('failed'),
        ACTIVE: _('active'),
        UNTESTED: _('untested')};

    this._comps = this._bindUIComps([
        'prompt-message-container',
        'test-name',
        'test-status-label',
        'test-results-table',
        'screensaver-mask',
        'screensaver-msg'
    ]);

    this._screensaverTimeout = screensaverTimeout;
    this._isScreensaverStopped = null;
    this._resetScreensaverTime = null;

    if (this._screensaverTimeout !== null) {
      for (const eventType of ['CLICK', 'MOUSEMOVE', 'KEYDOWN']) {
        goog.events.listen(
            test.invocation.iframe.contentWindow.document.body,
            goog.events.EventType[eventType],
            this._resetOrStopScreensaver, false, this);
      }
      this._runScreensaverLoop();
    }
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

  async _runScreensaverLoop() {
    this._resetScreensaverTime = Date.now();
    this._isScreensaverStopped = true;

    while (true) {
      while (this._resetScreensaverTime !== null) {
        const duration = this._resetScreensaverTime + this._screensaverTimeout
                         - Date.now();
        this._resetScreensaverTime = null;
        await cros.factory.utils.delay(1000 * duration);
      }

      await this._startScreensaver();
      this._resetScreensaverTime = Date.now();
    }
  }

  async _startScreensaver() {
    const changeMaskColorRuntime = async () => {
      while (!this._isScreensaverStopped) {
        for (const [beg, end, offs] of [[0, 256, 1], [255, -1, -1]]) {
          for (let i = beg; i != end && !this._isScreensaverStopped;
               i += offs) {
            this._comps.screensaverMask.style['background-color'] =
                `rgb(${i}, ${i}, ${i})`;
            await cros.factory.utils.delay(_SCREENSAVER_ITERATION_MSECS);
          }
        }
      };
    };
    const moveMsgRuntime = async () => {
      let msgStyleIdx = 0;
      const createCoordRuntime = (posStyleName, posAttrName, sizeAttrName) => {
        const screenSize = this._comps.screensaverMask[sizeAttrName];
        const msgSize = this._comps.screensaverMsg[sizeAttrName];
        let delta = 2;
        return () => {
          const pos = this._comps.screensaverMsg[posAttrName];
          if (pos < 0 || screenSize < pos + msgSize) {
            delta *= -1;
            msgStyleIdx = (msgStyleIdx + 1) % _NUM_SCREENSAVER_MSG_STYLES;
            this._comps.screensaverMsg.className =
                `screensaver-msg-${msgStyleIdx}`;
          }
          this._comps.screensaverMsg.style[posStyleName] = `${pos + delta}px`;
        };
      };
      const xRuntime = createCoordRuntime('left', 'offsetLeft', 'offsetWidth');
      const yRuntime = createCoordRuntime('top', 'offsetTop', 'offsetHeight');

      this._comps.screensaverMsg.className = 'screensaver-msg-0';
      this._comps.screensaverMsg.style['left'] = 0;
      this._comps.screensaverMsg.style['top'] = 0;
      while (!this._isScreensaverStopped) {
        xRuntime();
        yRuntime();
        await cros.factory.utils.delay(_SCREENSAVER_ITERATION_MSECS);
      }
    };

    this._isScreensaverStopped = false;
    this._comps.screensaverMask.classList.remove('screensaver-disabled');
    this._comps.screensaverMask.classList.add('screensaver-enabled');
    window.test.setFullScreen(true);
    await Promise.all([changeMaskColorRuntime(), moveMsgRuntime()]);
  }

  _resetOrStopScreensaver(event) {
    if (this._isScreensaverStopped) {  // reset the screensaver timer
      this._resetScreensaverTime = Date.now();

    } else {  // stop the screensaver
      event.stopPropagation();
      this._isScreensaverStopped = true;
      this._comps.screensaverMask.classList.add('screensaver-disabled');
      this._comps.screensaverMask.classList.remove('screensaver-enabled');
      window.test.setFullScreen(false);
    }
  }
};
