// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.testUI.TabManager');

goog.require('cros.factory.i18n');
goog.require('cros.factory.testUI.Manager');
goog.require('goog.asserts');
goog.require('goog.dom');
goog.require('goog.ui.Tab');
goog.require('goog.ui.TabBar');

/**
 * UI that use tab to run multiple invocations.
 * @implements {cros.factory.testUI.Manager}
 */
cros.factory.testUI.TabManager = class {
  /**
   * @param {!Element} root
   * @param {!cros.factory.testUI.CallBacks} callbacks
   */
  constructor(root, callbacks) {
    /**
     * The root element of the UI.
     * @type {!Element}
     */
    this.root = root;

    /**
     * The callbacks that can be used to notify Goofy about test state change.
     * @type {!cros.factory.testUI.CallBacks}
     */
    this.callbacks = callbacks;

    /**
     * Tab bar object.
     * @type {!goog.ui.TabBar}
     */
    this.tabBar = new goog.ui.TabBar();
    this.tabBar.render(this.root);

    /**
     * Main container for test iframes.
     * @type {!Element}
     */
    this.mainContainer = goog.dom.createDom('div', 'goofy-tab-main-container');
    this.root.appendChild(this.mainContainer);

    /**
     * The path of selected test.
     * @type {?string}
     */
    this.selectedPath = null;

    /**
     * Map from test path to iframe.
     * @type {!Object<string, !HTMLIFrameElement>}
     */
    this.pathIFrameMap = Object.create(null);

    /**
     * Map from test path to tab.
     * @type {!Object<string, !goog.ui.Tab>}
     */
    this.pathTabMap = Object.create(null);

    goog.events.listen(this.tabBar, goog.ui.Component.EventType.SELECT, () => {
      const selectedTab = this.tabBar.getSelectedTab();
      const testPath =
          goog.object.findKey(this.pathTabMap, (t) => t === selectedTab);
      goog.asserts.assert(testPath, 'Got select event with non-exist tab!');
      if (this.selectedPath) {
        this._setTestVisible(this.selectedPath, false);
      }
      this.selectedPath = testPath;
      this._setTestVisible(this.selectedPath, true);
    });
  }

  /**
   * Set additional options for the manager.
   * The tab manager have no additional options.
   * @param {!Object} options
   */
  setOptions(options) {}

  /**
   * Dispose the manager and remove all related UI.
   */
  dispose() {
    this.tabBar.dispose();
    this.mainContainer.remove();
  }

  /**
   * Add a test iframe to the manager.
   * @param {string} path
   * @param {!cros.factory.i18n.TranslationDict} label
   * @param {!HTMLIFrameElement} iframe
   */
  addTestUI(path, label, iframe) {
    this.mainContainer.appendChild(iframe);

    const tab = new goog.ui.Tab(cros.factory.i18n.i18nLabelNode(label));
    this.tabBar.addChild(tab, true);

    this.pathTabMap[path] = tab;
    this.pathIFrameMap[path] = iframe;

    if (this.tabBar.getChildCount() === 1) {
      tab.setSelected(true);
    }
  }

  /**
   * Remove a test iframe from the manager.
   * @param {string} path
   */
  removeTestUI(path) {
    this.tabBar.removeChild(this.pathTabMap[path], true);
    delete this.pathTabMap[path];

    this.mainContainer.removeChild(this.pathIFrameMap[path]);
    delete this.pathIFrameMap[path];

    if (path === this.selectedPath) {
      this.selectedPath = null;
    }
    this.callbacks.notifyTestVisible(path, false);
  }

  /**
   * @param {string} path
   * @param {boolean} visible
   * @private
   */
  _setTestVisible(path, visible) {
    const iframe = this.pathIFrameMap[path];
    if (iframe) {
      iframe.classList.toggle('goofy-test-visible', visible);
      if (visible) {
        this.callbacks.tryFocusIFrame(iframe);
      }
    }
    this.callbacks.notifyTestVisible(path, visible);
  }

  /**
   * Show a test.
   * @param {string} path
   */
  showTest(path) {
    if (path in this.pathTabMap) {
      this.pathTabMap[path].setSelected(true);
    }
  }

  /**
   * Return whether a test is currently visible.
   * @param {string} path
   * @return {boolean}
   */
  isVisible(path) {
    return path === this.selectedPath;
  }
};
