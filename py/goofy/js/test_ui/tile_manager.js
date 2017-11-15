// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.testUI.TileManager');

goog.require('cros.factory.i18n');
goog.require('cros.factory.testUI.Manager');
goog.require('goog.array');
goog.require('goog.asserts');
goog.require('goog.dom');

/**
 * UI that use tiled view to run multiple invocations.
 * @implements {cros.factory.testUI.Manager}
 */
cros.factory.testUI.TileManager = class {
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
     * Main container for test iframes.
     * @type {!Element}
     */
    this.mainContainer = goog.dom.createDom('div', 'goofy-tile-main-container');
    this.root.appendChild(this.mainContainer);

    /**
     * Map from test path to the block.
     * @type {!Object<string, !Element>}
     */
    this.pathBlockMap = Object.create(null);

    /**
     * The order of tests displayed.
     * @type {!Array<string>}
     */
    this.pathOrder = [];

    /**
     * Map from test path to whether the test is visible.
     * Would be updated in _redraw().
     * @type {!Object<string, boolean>}
     */
    this.pathVisibleMap = Object.create(null);

    /**
     * Number of rows in the layout.
     * @type {number}
     */
    this.rows = 1;

    /**
     * Number of columns in the layout.
     * @type {number}
     */
    this.columns = 1;
  }

  /**
   * Set additional options for the manager.
   * @param {!Object} options
   */
  setOptions(options) {
    const typedOptions =
        /** @type {{rows: ?number, columns: ?number}} */ (options);
    const {rows, columns} = typedOptions;
    this._setLayoutSize(rows || 2, columns || 2);
  }

  /**
   * Dispose the manager and remove all related UI.
   */
  dispose() {
    this.mainContainer.remove();
  }

  /**
   * Set the size of the layout.
   * @param {number} rows
   * @param {number} columns
   */
  _setLayoutSize(rows, columns) {
    this.rows = rows;
    this.columns = columns;
    this.mainContainer.style.grid =
        'repeat(' + this.rows + ', 1fr) / repeat(' + this.columns + ', 1fr)';
    this._redraw();
  }

  /**
   * Get the iframe from a test path.
   * @param {string} path
   * @return {!HTMLIFrameElement}
   */
  _getIframe(path) {
    return /** @type {!HTMLIFrameElement} */ (
        this.pathBlockMap[path].getElementsByTagName('iframe')[0]);
  }

  /**
   * Redraw the layout and set visibility properly according to this.pathOrder.
   */
  _redraw() {
    const totalSize = this.rows * this.columns;
    goog.array.forEach(this.pathOrder, (path, idx) => {
      const newVisibility = idx < totalSize;

      const block = this.pathBlockMap[path];
      const iframe = this._getIframe(path);
      block.classList.toggle('goofy-test-visible', newVisibility);
      iframe.classList.toggle('goofy-test-visible', newVisibility);
      block.style.order = idx;

      const oldVisibility = this.pathVisibleMap[path];
      if (oldVisibility != newVisibility) {
        this.callbacks.notifyTestVisible(path, newVisibility);
      }
      this.pathVisibleMap[path] = newVisibility;
    });
    if (this.pathOrder.length > 0) {
      this.callbacks.tryFocusIFrame(this._getIframe(this.pathOrder[0]));
    }
  }

  /**
   * Add a test iframe to the manager.
   * @param {string} path
   * @param {!cros.factory.i18n.TranslationDict} label
   * @param {!HTMLIFrameElement} iframe
   */
  addTestUI(path, label, iframe) {
    const block = goog.dom.createDom('div', 'goofy-tile-block');
    const title = goog.dom.createDom(
        'div', 'goofy-tile-title', cros.factory.i18n.i18nLabelNode(label));
    title.tabIndex = -1;
    block.appendChild(title);
    block.appendChild(iframe);

    this.mainContainer.appendChild(block);
    this.pathBlockMap[path] = block;
    this.pathVisibleMap[path] = false;
    this.pathOrder.push(path);

    title.addEventListener('focus', () => {
      setTimeout(() => {
        this.callbacks.tryFocusIFrame(iframe);
      }, 0);
    });
    iframe.contentWindow.addEventListener('focus', () => {
      title.classList.add('focused');
    });
    iframe.contentWindow.addEventListener('blur', () => {
      title.classList.remove('focused');
    });

    this._redraw();
  }

  /**
   * Remove a test iframe from the manager.
   * @param {string} path
   */
  removeTestUI(path) {
    this.mainContainer.removeChild(this.pathBlockMap[path]);
    delete this.pathBlockMap[path];
    delete this.pathVisibleMap[path];
    goog.array.remove(this.pathOrder, path);

    this.callbacks.notifyTestVisible(path, false);
    this._redraw();
  }

  /**
   * Show a test.
   * @param {string} path
   */
  showTest(path) {
    if (!(path in this.pathVisibleMap) || this.pathVisibleMap[path]) {
      return;
    }
    goog.array.moveItem(
        this.pathOrder, goog.array.indexOf(this.pathOrder, path), 0);
    this._redraw();
  }

  /**
   * Return whether a test is currently visible.
   * @param {string} path
   * @return {boolean}
   */
  isVisible(path) {
    return path in this.pathVisibleMap && this.pathVisibleMap[path];
  }
};
