// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for touchscreen test.
 * @constructor
 * @param {string} container
 * @param {number} numColumns Number of columns.
 * @param {number} numRows Number of rows.
 * @param {number} maxRetries Number of retries.
 */
TouchscreenTest = function(container, numColumns, numRows,
                           maxRetries) {
  this.container = container;
  this.numColumns = numColumns;
  this.numRows = numRows;
  this.maxRetries = maxRetries;

  this.expectSequence = [];
  this.tries = 0;

  this.previousBlockIndex = -1;
  this.expectBlockIndex = 0;
  this.tryFailed = false;

  this.MSG_INSTRUCTION = {
    en: 'Draw blocks from upper-left corner in sequence; Esc to fail.',
    zh: '从左上角开始依序画格子; 按 Esc 键标记失败'};
  this.MSG_START_UPPER_LEFT = {
    en: 'Please start drawing from upper-left corner.',
    zh: '请从左上角开始画格子'};
  this.MSG_OUT_OF_SEQUENCE = {
    en: 'Fails to draw blocks in sequence. Please try again.',
    zh: '没依照顺序画格子！请重来'};
  this.MSG_OUT_OF_SEQUENCE_MULTIPLE = {
    en: 'Please leave your finger and restart from upper-left block.',
    zh: '请移开手指并从左上角开始重画'};
  this.MSG_LEAVE_EARLY = {
    en: 'Finger leaving too early. Please try again.',
    zh: '手指太早离开！请重来'};
};

/**
 * Creates a touchscreen test and runs it.
 * @param {string} container
 * @param {number} numColumns Number of columns.
 * @param {number} numRows Number of rows.
 * @param {number} maxRetries Number of retries.
 */
function setupTouchscreenTest(container, numColumns, numRows,
                              maxRetries) {
  window.touchscreenTest = new TouchscreenTest(container, numColumns,
                                               numRows, maxRetries);
  window.touchscreenTest.init();
}

/**
 * Initializes Touchscreen UI and touch sequence.
 */
TouchscreenTest.prototype.init = function() {
  this.setupFullScreenElement();
  this.expectSequence = this.generateTouchSequence();

  // Sanity check
  if (this.expectSequence.length != this.numColumns * this.numRows) {
    alert('generateTouchSequence() is buggy. The number of sequences ' +
          'is not equal to the number of blocks.');
    this.failTest();
  }
};

/**
 * Initializes fullscreen div elements and sets fullscreen mode.
 *
 * The touch table contains xSegment by ySegment divs
 */
TouchscreenTest.prototype.setupFullScreenElement = function() {
  this.fullScreenElement = document.createElement('div');
  var fullScreen = this.fullScreenElement;
  fullScreen.className = 'touchscreen-full-screen';
  fullScreen.addEventListener('touchstart',
                              this.touchStartHandler.bind(this), false);
  fullScreen.addEventListener('touchmove',
                              this.touchMoveHandler.bind(this), false);
  fullScreen.addEventListener('touchend',
                              this.touchEndHandler.bind(this), false);

  fullScreen.appendChild(createPrompt(this.MSG_INSTRUCTION));

  var touchscreenTable = createTable(this.numRows, this.numColumns, 'touch',
                                     'touchscreen-test-block-untested');
  fullScreen.appendChild(touchscreenTable);
  $(this.container).appendChild(fullScreen);

  window.test.setFullScreen(true);
};

/**
 * Creates a touchscreen block test sequence.
 *
 * It starts from upper-left corner, draws the outer blocks in right, down,
 * left, up directions; then draws inner blocks till the center block is
 * reached.
 *
 * @returns {Array<number>} Array of touchscreen block test sequence.
 */
TouchscreenTest.prototype.generateTouchSequence = function() {
  var xyToIndex = this.xyToIndex.bind(this);
  function impl(startX, startY, sizeX, sizeY) {
    var result = [];
    if (sizeX <= 0 || sizeY <= 0) {
      return result;
    }
    var x = startX;
    var y = startY;

    // Go right.
    for (; x < startX + sizeX; x++) {
      result.push(xyToIndex(x, y));
    }

    if (sizeY == 1) {
      return result;
    }

    // Go down. Skips the duplicate first point (same below).
    for (x--, y++; y < startY + sizeY; y++) {
      result.push(xyToIndex(x, y));
    }

    if (sizeX == 1) {
      return result;
    }

    // Go left.
    for (y--, x--; x >= startX; x--) {
      result.push(xyToIndex(x, y));
    }

    // Go up.
    for (x++, y--; y > startY; y--) {
      result.push(xyToIndex(x, y));
    }

    return result.concat(impl(startX + 1, startY + 1, sizeX - 2, sizeY - 2));
  }
  return impl(0, 0, this.numColumns, this.numRows);
};

/**
 * Converts (x, y) block coordinates to block index.
 * @param {number} x x-coordinate
 * @param {number} y y-coordinate
 * @return {number} block index
 */
TouchscreenTest.prototype.xyToIndex = function(x, y) {
  return x + y * this.numColumns;
};

/**
 * Gets block index of the touch event.
 * @param {touch event} touch Touch event.
 * @returns {number} Block ID.
 */
TouchscreenTest.prototype.getBlockIndex = function(touch) {
  var col = Math.floor(touch.screenX / screen.width * this.numColumns);
  var row = Math.floor(touch.screenY / screen.height * this.numRows);
  return this.xyToIndex(col, row);
};

/**
 * Fails this try and if #retries is reached, fail the test.
 */
TouchscreenTest.prototype.failThisTry = function() {
  // Prevent marking multiple failure for a try.
  if (!this.tryFailed) {
    this.tryFailed = true;
    this.tries++;
    if (this.tries > this.maxRetries) {
      this.failTest();
    }
  }
};

/**
 * Handles touchstart event.
 *
 * It checks if the touch starts from block (0, 0).
 * If not, prompt operator to do so.
 *
 * @param {event} event.
 */
TouchscreenTest.prototype.touchStartHandler = function(event) {
  var touch = event.changedTouches[0];
  var touchBlockIndex = this.getBlockIndex(touch);
  event.preventDefault();

  if (touchBlockIndex != 0) {
    this.prompt(this.MSG_START_UPPER_LEFT);
    this.markBlock(touchBlockIndex, false);
    this.startTouch = false;
    this.failThisTry();
    return;
  }

  // Reset blocks for previous failure.
  if (this.tryFailed) {
    this.restartTest();
  }
  this.startTouch = true;
};

/**
 * Handles touchmove event.
 *
 * It'll check if the current block is the expected one.
 * If not, it'll prompt operator to restart from upper-left block.
 *
 * @param {event} event.
 */
TouchscreenTest.prototype.touchMoveHandler = function(event) {
  var touch = event.changedTouches[0];
  var touchBlockIndex = this.getBlockIndex(touch);
  event.preventDefault();

  // Filter out move event of the same block.
  if (this.previousBlockIndex == touchBlockIndex) {
    return;
  }

  // No need to check block sequence if last one is out-of-sequence.
  if (!this.tryFailed &&
      this.expectSequence[this.expectBlockIndex] == touchBlockIndex) {
    // Successful touched a expected block. Expecting next one.
    this.markBlock(touchBlockIndex, true);
    this.expectBlockIndex++;
    this.previousBlockIndex = touchBlockIndex;
    this.checkTestComplete();
  } else {
    // Failed case. Either out-of-sequence touch or early finger leaving.
    // Show stronger prompt for drawing multiple unexpected blocks.
    this.prompt(this.tryFailed ? this.MSG_OUT_OF_SEQUENCE_MULTIPLE :
                this.MSG_OUT_OF_SEQUENCE);
    this.markBlock(touchBlockIndex, false);
    this.failThisTry();
    this.previousBlockIndex = touchBlockIndex;
  }
};

/**
 * Handles touchend event.
 * @param {event} event.
 */
TouchscreenTest.prototype.touchEndHandler = function(event) {
  var touch = event.changedTouches[0];
  var touchBlockIndex = this.getBlockIndex(touch);
  event.preventDefault();

  if (!this.tryFailed) {
    this.prompt(this.MSG_LEAVE_EARLY);
    this.failThisTry();
  }
  this.markBlock(touchBlockIndex, false);
};

/**
 * Restarts the test.
 *
 * Resets test properties to default and blocks to untested.
 */
TouchscreenTest.prototype.restartTest = function() {
  this.prompt(this.MSG_INSTRUCTION);
  for (var i = 0; i < this.expectSequence.length; i++) {
    $('touch-' + i).className = 'touchscreen-test-block-untested';
  }
  this.previousBlockIndex = -1;
  this.expectBlockIndex = 0;
  this.tryFailed = false;
};

/**
 * Sets a block's test state
 * @param {number} blockIndex
 * @param {bool} passed false if the block is touched unexpectedly or the
 *     finger left too early.
 */
TouchscreenTest.prototype.markBlock = function(blockIndex, passed) {
  $('touch-' + blockIndex).className =
      'touchscreen-test-block-' + (passed ? 'tested': 'failed');
};

/**
 * Checks if test is completed.
 * */
TouchscreenTest.prototype.checkTestComplete = function() {
  if (this.expectBlockIndex == this.expectSequence.length) {
    window.test.pass();
  }
};

/**
 * Fails the test and prints out all the failed items.
 */
TouchscreenTest.prototype.failTest = function() {
  // Returns an Array converted from the NodeList of the given class.
  function elements(className) {
    return Array.prototype.slice.call(
        document.getElementsByClassName(className));
  }

  var untestedBlocks = [];
  elements('touchscreen-test-block-untested').forEach(
    function(element) {
      untestedBlocks.push(element.id);
    }
  );
  var failedBlocks = [];
  elements('touchscreen-test-block-failed').forEach(
    function(element) {
      failedBlocks.push(element.id);
    }
  );

  this.failMessage = 'Touchscreen test failed.';
  if (failedBlocks.length) {
    this.failMessage +=  '  Failed blocks: ' + failedBlocks.join();
  }
  if (untestedBlocks.length) {
    this.failMessage +=  '  Untested blocks: ' + untestedBlocks.join();
  }
  window.test.fail(this.failMessage);
};

/**
 * Sets prompt message
 * @param {object} message A message object containing en and zh messages.
 */
TouchscreenTest.prototype.prompt = function(message) {
  $('prompt_en').innerHTML = message.en;
  $('prompt_zh').innerHTML = message.zh;
};

/**
 * Creates an prompt element.
 *
 * It contains prompt_en and prompt_zh divs, with class goofy-label-en and
 * goofy-label-zh, respectively so that Goofy can switch the language of
 * prompt.
 *
 * @param {object} message A message object containing en and zh messages.
 * @return {object} prompt div.
 */
function createPrompt(message) {
  var prompt = document.createElement('div');
  prompt.className = 'touchscreen-prompt';

  var en_span = document.createElement('span');
  en_span.className = 'goofy-label-en';
  en_span.id = 'prompt_en';
  en_span.innerHTML = message.en;
  prompt.appendChild(en_span);

  var zh_span = document.createElement('span');
  zh_span.className = 'goofy-label-zh';
  zh_span.id = 'prompt_zh';
  zh_span.innerHTML = message.zh;
  prompt.appendChild(zh_span);

  return prompt;
}

/**
 * Creates a table element with specified row number and column number.
 * Each td in the table contains one div with id prefix-block_index
 * and the specified CSS class.
 * @param {number} rowNumber
 * @param {number} colNumber
 * @param {String} prefix
 * @param {String} className
 * @return {table}
 */
function createTable(rowNumber, colNumber, prefix, className) {
  var table = document.createElement('table');
  table.className = 'touchscreen-test-table';
  var tableBody = document.createElement('tbody');
  var blockIndex = 0;
  for (var y = 0; y < rowNumber; ++y) {
    var row = document.createElement('tr');
    for (var x = 0; x < colNumber; ++x) {
      var cell = document.createElement('td');
      cell.id = prefix + '-' + blockIndex++;
      cell.className = className;
      cell.innerHTML = '&nbsp';
      row.appendChild(cell);
    }
    tableBody.appendChild(row);
  }
  table.appendChild(tableBody);
  return table;
}

/**
 * Fails the test.
 */
function failTest() {
  window.touchscreenTest.failTest();
}
