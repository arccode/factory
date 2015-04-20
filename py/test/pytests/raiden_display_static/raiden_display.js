// Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for display test.
 * @constructor
 * @param {string} container
 * @param {Array.<string>} colors
 */
DisplayTest = function(container) {
  this.container = container;
  this.display = false;
  this.styleDiv = null;
  this.fullScreenElement = null;
};

/**
 * Creates a display test and runs it.
 * @param {string} container
 * @param {Array.<string>} colors
 */
function setupDisplayTest(container) {
  window.displayTest = new DisplayTest(container);
  window.displayTest.setupFullScreenElement();
  window.displayTest.setupDisplayDiv();
  window.displayTest.setDisplayDivClass();
}

/**
 * Initializes fullscreen elements.
 */
DisplayTest.prototype.setupFullScreenElement = function() {
  this.fullScreenElement = document.createElement("div");
  this.fullScreenElement.className = "display-full-screen-hide";
  $(this.container).appendChild(this.fullScreenElement);
};

/**
 * Initializes display div in fullscreen element.
 */
DisplayTest.prototype.setupDisplayDiv = function() {
  this.displayDiv = document.createElement("div");
  this.displayDiv.id = "display-div";
  this.fullScreenElement.appendChild(this.displayDiv);
};

/**
 * Setups display div style. Grids need to be taking care of separately.
 */
DisplayTest.prototype.setDisplayDivClass = function() {
  var displayBeforeSetting = this.display;
  //cleans up display div
  this.displayDiv.innerHTML = "";
  this.displayDiv.className = "display-subtest-image";
};

/**
 * Toggles the fullscreen display visibility.
 */
DisplayTest.prototype.switchDisplayOnOff = function() {
  //If current display is on, turns it off
  if (this.display) {
    this.switchDisplayOff();
  } else {
    this.switchDisplayOn();
  }

};

/**
 * Switches the fullscreen display on. Sets fullScreenElement
 * visibility to visible and enlarges the test iframe to fullscreen.
 */
DisplayTest.prototype.switchDisplayOn = function() {
  this.display = true;
  this.fullScreenElement.className = "display-full-screen-show";
  window.test.setFullScreen(true);
};

/**
 * Switches the fullscreen display off. Sets fullScreenElement
 * visibility to hidden and restores the test iframe to normal.
 */
DisplayTest.prototype.switchDisplayOff = function() {
  this.display = false;
  this.fullScreenElement.className = "display-full-screen-hide";
  window.test.setFullScreen(false);
};

/**
 * Switches the display.
 */
function switchDisplayOnOff() {
  window.displayTest.switchDisplayOnOff();
}
