// Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for touchscreen test.
 * @constructor
 * @param {string} container
 * @param {number} xSegments
 * @param {number} ySegments
 */
var TouchscreenTest = function(container, xSegments, ySegments) {
  this.container = container;
  this.xSegments = xSegments;
  this.ySegments = ySegments;
  this.display = false;
  this.enInstruct = 'Press Space to display and use one finger to ' +
      'touch each sector; Esc to fail.';
  this.zhInstruct = '按空白键显示并用一个手指触摸每区; 按Esc键失败。';
};

/**
 * Creates a touchscreen test and runs it.
 * @param {string} container
 * @param {number} xSegments
 * @param {number} ySegments
 */
function setupTouchscreenTest(container, xSegments, ySegments) {
  window.touchscreenTest = new TouchscreenTest(container, xSegments, ySegments);
  window.touchscreenTest.init();
  window.touchscreenTest.setupFullScreenElement();
}

/**
 * Initializes touchscreen caption div elements.
 */
TouchscreenTest.prototype.init = function() {
  var caption = document.createElement('div');
  caption.className = 'touchscreen-caption';
  appendSpanEnZh(caption, this.enInstruct, this.zhInstruct);
  $(this.container).appendChild(caption);
};

/**
 * Initializes fullscreen div elements.
 * The touch table contains xSegment by ySegment divs
 */
TouchscreenTest.prototype.setupFullScreenElement = function() {
  this.fullScreenElement = document.createElement('div');
  this.fullScreenElement.className = 'touchscreen-full-screen-hide';
  var touchscreenTable = createTable(this.ySegments, this.xSegments, 'touch',
      'touchscreen-test-sector-untested');
  this.fullScreenElement.appendChild(touchscreenTable);
  $(this.container).appendChild(this.fullScreenElement);
};

/**
 * Toggles the fullscreen display visibility.
 */
TouchscreenTest.prototype.switchDisplayOnOff = function() {
  this.display = !this.display;
  if (this.display) {
    this.switchDisplayOn();
  } else {
    this.switchDisplayOff();
  }
};

/**
 * Switches the fullscreen display on. Sets fullScreenElement
 * visibility to visible and enlarges the test iframe to fullscreen.
 */
TouchscreenTest.prototype.switchDisplayOn = function() {
  this.display = true;
  this.fullScreenElement.className = 'touchscreen-full-screen-show';
  window.test.setFullScreen(true);
};

/**
 * Switches the fullscreen display off. Sets fullScreenElement
 * visibility to hidden and restores the test iframe to normal.
 */
TouchscreenTest.prototype.switchDisplayOff = function() {
  this.display = false;
  this.fullScreenElement.className = 'touchscreen-full-screen-hide';
  window.test.setFullScreen(false);
};

/**
 * Marks the given (x,y) sector as "tested" on the test ui.
 * @param {number} x
 * @param {number} y
 */
TouchscreenTest.prototype.markSectorTested = function(x, y) {
  var id = 'touch-x-' + x + '-y-' + y;
  var element = document.getElementById(id);
  if (element) {
    element.className = 'touchscreen-test-sector-tested';
  }
  this.checkTestComplete();
};

/**
 * Checks if test is completed by checking the number of sectors that
 * haven't passed the test.
 * */
TouchscreenTest.prototype.checkTestComplete = function() {
  if (this.getClassArray('touchscreen-test-sector-untested').length == 0) {
    window.test.pass();
  }
};

/**
 * Fails the test and prints out all the failed items.
 */
TouchscreenTest.prototype.failTest = function() {
  var failedSectors = new Array();

  this.getClassArray('touchscreen-test-sector-untested').forEach(
    function(element) {
      failedSectors.push((element.id));
    }
  );

  this.failMsg = 'Touchscreen test failed. Malfunction sectors:';
  failedSectors.forEach(function(element, index, array) {
    this.failMsg += ' ' + element;
    if (index != array.length - 1) {
      this.failMsg += ',';
    }
  }, this);
  window.test.fail(this.failMsg);
};

/**
 * Returns an Array converted from the NodeList of the given class.
 * @param {string} className
 * @return {Array}
 */
TouchscreenTest.prototype.getClassArray = function(className) {
  return Array.prototype.slice.call(document.getElementsByClassName(className));
};

/**
 * Appends en span and zh span to the input element.
 * @param {Element} div the element to which we want to append spans.
 * @param {string} en the English text to be appended.
 * @param {string} zh the Simplified-Chinese text to be appended.
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

/**
 * Creates a table element with specified row number and column number.
 * Each td in the table contains one div with id prefix-x-x_number-y-y_number
 * and the specified CSS class.
 * @param {number} rowNumber
 * @param {number} colNumber
 * @param {string} prefix
 * @param {string} className
 * @return {Element}
 */
function createTable(rowNumber, colNumber, prefix, className) {
  var table = document.createElement('table');
  table.style.width = '100%';
  table.style.height = '100%';
  var tableBody = document.createElement('tbody');
  for (var y = 0; y < rowNumber; ++y) {
    var row = document.createElement('tr');
    for (var x = 0; x < colNumber; ++x) {
      var cell = document.createElement('td');
      var div = document.createElement('div');
      div.id = prefix + '-x-' + x + '-' + 'y-' + y;
      div.innerHTML = div.id;
      div.className = className;
      cell.appendChild(div);
      row.appendChild(cell);
    }
    tableBody.appendChild(row);
  }
  table.appendChild(tableBody);
  return table;
}

/**
 * Switches the display.
 */
function switchDisplayOnOff() {
  window.touchscreenTest.switchDisplayOnOff();
}

/**
 * Marks a sector as tested.
 * @param {number} x
 * @param {number} y
 */
function markSectorTested(x, y) {
  window.touchscreenTest.markSectorTested(x, y);
}

/**
 * Fails the test.
 */
function failTest() {
  window.touchscreenTest.failTest();
}

/**
 * Shows message of two fingers and fail the test.
 */
function twoFingersException() {
  alert('Use only one finger!' + ' 请用一个手指');
  window.touchscreenTest.failTest();
}
