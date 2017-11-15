// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.testUI.Manager');

goog.require('cros.factory.i18n');

/**
 * @typedef {{
 *   notifyTestVisible: function(string, boolean),
 *   tryFocusIFrame: function(!HTMLIFrameElement)
 * }}
 */
cros.factory.testUI.CallBacks;

/**
 * The interface that UI manager should implements.
 * @interface
 */
cros.factory.testUI.Manager = class {
  /**
   * @param {!Element} root
   * @param {!cros.factory.testUI.CallBacks} callbacks
   */
  constructor(root, callbacks) {}

  /**
   * Set additional options for the manager.
   * @param {!Object} options
   */
  setOptions(options) {}

  /**
   * Dispose the manager and remove all related UI.
   */
  dispose() {}

  /**
   * Add a test iframe to the manager.
   * @param {string} path
   * @param {!cros.factory.i18n.TranslationDict} label
   * @param {!HTMLIFrameElement} iframe
   */
  addTestUI(path, label, iframe) {}

  /**
   * Remove a test iframe from the manager.
   * @param {string} path
   */
  removeTestUI(path) {}

  /**
   * Show a test.
   * @param {string} path
   */
  showTest(path) {}

  /**
   * Return whether a test is currently visible.
   * @param {string} path
   * @return {boolean}
   */
  isVisible(path) {}
};
