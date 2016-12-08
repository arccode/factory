// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.


/**
 * API for display_point test.
 * @constructor
 * @param {string} container
 * @param {Array.<number>} arrayNumberPoint
 * @param {number} pointSize
 */
var DisplayPointTest = function(container, arrayNumberPoint, pointSize) {
  this.container = container;
  this.arrayNumberPoint = arrayNumberPoint;
  this.pointSize = pointSize;
  this.display = false;
  this.fullScreenElement = null;
  this.focusItem = 0;
  this.enInstruct = 'Press Space to display;<br>' +
      'After checking, Enter number of points to pass.';
  this.zhInstruct = '按空格键显示;<br>' +
      '检查后按下正确的点数按键通过。';
  this.itemNumber = 2;
  this.backgroundStyleList = [
    'display-point-background-white',
    'display-point-background-black'];
  this.pointStyleList = [
    'display-point-black',
    'display-point-white'];
  this.checked = false;
};

/**
 * Initializes display point test ui.
 * There is a caption for instructions.
 * There is an input box below the caption.
 */
DisplayPointTest.prototype.init = function() {
  var caption = document.createElement('div');
  caption.className = 'display-point-caption';
  appendSpanEnZh(caption, this.enInstruct, this.zhInstruct);
  $(this.container).appendChild(caption);
};

/**
 * Initializes fullscreen elements.
 */
DisplayPointTest.prototype.initFullScreenElement = function() {
  this.fullScreenElement = document.createElement('div');
  this.fullScreenElement.className = 'display-full-screen-hide';
  $(this.container).appendChild(this.fullScreenElement);
};

/**
 * Initializes display div in fullscreen element.
 */
DisplayPointTest.prototype.initDisplayDiv = function() {
  this.displayDiv = document.createElement('div');
  this.fullScreenElement.appendChild(this.displayDiv);
};

/**
 * Setups display div element and draws the points.
 * Optionally shows the fullscreen display.
 * @param {boolean} display
 */
DisplayPointTest.prototype.drawDisplayPoint = function(display) {
  this.setupDisplayDiv();
  this.setupPoint();
  if (display) {
    this.switchDisplayOn();
  }
};

/**
 * Setups display div element. Cleans up its content, sets the style, and set
 * click handler.
 */
DisplayPointTest.prototype.setupDisplayDiv = function() {
  //cleans up display div
  this.displayDiv.innerHTML = '';
  this.displayDiv.className = this.backgroundStyleList[this.focusItem];
  this.displayDiv.addEventListener('click', function(event) {
    this.switchDisplayOff();
  }.bind(this));
};

/**
 * Gets an random integral position from 0 to 99.
 * @return {number}
 */
DisplayPointTest.prototype.getRandomPosition = function() {
  return Math.floor(Math.random() * 100);
};

/**
 * Setups point in the subtest.
 */
DisplayPointTest.prototype.setupPoint = function() {
  var numberPoint = this.arrayNumberPoint[this.focusItem];
  for (var p = 0; p < numberPoint; ++p) {
    var div = document.createElement('div');
    div.className = this.pointStyleList[this.focusItem];
    div.style.position = 'absolute';
    div.style.top = this.getRandomPosition() + '%';
    div.style.left = this.getRandomPosition() + '%';
    div.style.width = this.pointSize + 'px';
    div.style.height = this.pointSize + 'px';
    this.displayDiv.appendChild(div);
  }
};

/**
 * Judges the subtest. If the subtest passes, prepares the next subtest or
 * passes the test if there is no more subtest.
 * Fails the test if the subtest fails.
 * @param {number} number
 */
DisplayPointTest.prototype.judgePoint = function(number) {
  if (this.checked) {
    if (number == this.arrayNumberPoint[this.focusItem]) {
      this.focusItem = this.focusItem + 1;
      if (this.focusItem < this.itemNumber) {
        this.drawDisplayPoint(true);
        // We always show next subtest, so we dont need to reset this.checked.
      } else {
        window.test.pass();
      }
    } else {
      window.displayPointTest.failTest(number);
    }
  }
};

/**
 * Toggles the fullscreen display visibility.
 */
DisplayPointTest.prototype.switchDisplayOnOff = function() {
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
DisplayPointTest.prototype.switchDisplayOn = function() {
  this.display = true;
  this.checked = true;
  this.fullScreenElement.className = 'display-full-screen-show';
  window.test.setFullScreen(true);
};

/**
 * Switches the fullscreen display off. Sets fullScreenElement
 * visibility to hidden and restores the test iframe to normal.
 */
DisplayPointTest.prototype.switchDisplayOff = function() {
  this.display = false;
  this.fullScreenElement.className = 'display-full-screen-hide';
  window.test.setFullScreen(false);
};

/**
 * Fails the test and logs the failed items.
 * @param {number} number
 */
DisplayPointTest.prototype.failTest = function(number) {
  var failMsg = 'DisplayPoint test failed at item ' + this.focusItem;
  failMsg += ' Correct number: ' + this.arrayNumberPoint[this.focusItem];
  failMsg += ' Input number: ' + number;
  window.test.fail(failMsg);
};

/**
 * Creates a display point test and runs it.
 * @param {string} container
 * @param {Array.<number>} arrayNumberPoint
 * @param {number} pointSize
 */
function setupDisplayPointTest(container, arrayNumberPoint, pointSize) {
  window.displayPointTest = new DisplayPointTest(container, arrayNumberPoint,
                                                 pointSize);
  window.displayPointTest.init();
  window.displayPointTest.initFullScreenElement();
  window.displayPointTest.initDisplayDiv();
  window.displayPointTest.drawDisplayPoint(false);
}

/**
 * Judges the subtest answer.
 * @param {number} number
 */
function judgeSubTest(number) {
  window.displayPointTest.judgePoint(number);
}

/**
 * Switches the fullscreen display.
 */
function switchDisplayOnOff() {
  window.displayPointTest.switchDisplayOnOff();
}

/**
 * Fails the test.
 */
function failTest() {
  window.displayPointTest.failTest('None');
}

/**
 * Appends en span and zh span to the input element.
 * @param {Element} div the element we to which we want to append spans.
 * @param {string} en the English text to append.
 * @param {string} zh the Simplified-Chinese text to append.
 */
function appendSpanEnZh(div, en, zh) {
  var en_span = document.createElement('span');
  var zh_span = document.createElement('span');
  en_span.className = 'goofy-label-en';
  en_span.innerHTML = en;
  zh_span.className = 'goofy-label-zh';
  zh_span.innerHTML = zh;
  div.appendChild(en_span);
  div.appendChild(zh_span);
}
