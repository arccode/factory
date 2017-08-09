// Copyright 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for backlight test.
 * @constructor
 * @param {string} container
 */
var BacklightTest = function(container) {
  this.container = container;
  var _ = cros.factory.i18n.translation;
  this.instruct =
      _('Press Space to change backlight brightness;\n' +
        'Press Esc to reset backlight brightness to original;\n' +
        'After checking, Enter H if pressing Space changes the ' +
        'backlight to be brighter;\n' +
        'Enter L if pressing Space changes the backlight to be ' +
        'dimmer.\n' +
        'This test will be executed twice.');
};


/**
 * Initializes backlight test ui.
 * There is a caption for instructions.
 */
BacklightTest.prototype.init = function() {
  $(this.container).appendChild(cros.factory.i18n.i18nLabelNode(this.instruct));
  $(this.container).className = 'backlight-caption';
};


/**
 * Creates a backlight test and runs it.
 * @param {string} container
 */
function setupBacklightTest(container) {
  window.backlightTest = new BacklightTest(container);
  window.backlightTest.init();
}
