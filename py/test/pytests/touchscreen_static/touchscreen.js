// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const MOVE_TOLERANCE = 20;
const INDICATOR_LENGTH = 4;

/**
 * API for touchscreen test.
 */
window.TouchscreenTest = class {
  /*
   * @param {number} numColumns Number of columns.
   * @param {number} numRows Number of rows.
   * @param {number} maxRetries Number of retries.
   * @param {number} demoIntervalMsecs Interval (ms) to show drawing pattern.
   *     Non-positive value means no demo.
   * @param {boolean} e2eMode Perform end-to-end test or not (for touchscreen).
   * @param {boolean} spiralMode Blocks must be drawn in spiral order or not.
   */
  constructor(
      numColumns, numRows, maxRetries, demoIntervalMsecs, e2eMode, spiralMode) {
    this.numColumns = numColumns;
    this.numRows = numRows;
    this.numBlocks = this.numRows * this.numColumns;
    this.maxRetries = maxRetries;
    this.e2eMode = e2eMode;
    this.spiralMode = spiralMode;

    this.expectSequence = [];
    this.tries = 0;
    this.tryFailed = false;

    this.previousBlockIndex = -1;
    this.testedBlockCount = 0;

    this.demoIntervalMsecs = demoIntervalMsecs;

    this.previousX = 0;
    this.previousY = 0;

    this.setupUI();

    if (this.spiralMode) {
      this.expectSequence = this.generateTouchSequence();
      if (this.demoIntervalMsecs > 0) {
        this.showDemoIndicator();
      }
    }
  }

  /**
   * Initializes fullscreen div elements and sets fullscreen mode.
   *
   * The touch table contains numRows by numColumns divs.
   */
  setupUI() {
    if (this.e2eMode) {
      const fullScreenElement = document.getElementById('fullscreen');
      const handler = (handlerName) => (event) => {
        event.preventDefault();
        const touchEvent = event.changedTouches[0];
        this[handlerName](touchEvent.screenX, touchEvent.screenY);
      };
      fullScreenElement.addEventListener(
          'touchstart', handler('touchStartHandler'));
      fullScreenElement.addEventListener(
          'touchmove', handler('touchMoveHandler'));
      fullScreenElement.addEventListener(
          'touchend', handler('touchEndHandler'));
    }

    const testGrid = document.getElementById('test-grid');
    testGrid.style.grid =
        `repeat(${this.numRows}, 1fr) / repeat(${this.numColumns}, 1fr)`;

    for (let i = 0; i < this.numBlocks; i++) {
      const div = document.createElement('div');
      div.id = `block-${i}`;
      testGrid.appendChild(div);
    }

    this.restartTest();
    window.test.setFullScreen(true);
  }

  /**
   * Creates a touchscreen block test sequence.
   *
   * It starts from upper-left corner, draws the outer blocks in right, down,
   * left, up directions; then draws inner blocks till the center block is
   * reached.
   *
   * @return {Array<{blockIndex: number, directionX: number,
   *                 directionY: number}>}
   *     Array of touchscreen block test sequence.
   */
  generateTouchSequence() {
    const steps = [[1, 0], [0, 1], [-1, 0], [0, -1]];
    const points = [];
    const walked = new Set();
    const canWalk = (col, row) =>
        (col >= 0 && col < this.numColumns && row >= 0 && row < this.numRows &&
         !walked.has(this.colRowToIndex(col, row)));

    let col = 0, row = 0, direction = 0;
    for (let i = 0; i < this.numBlocks; i++) {
      points.push([col, row]);
      walked.add(this.colRowToIndex(col, row));
      for (const newDirection of [direction, (direction + 1) % 4]) {
        const [dCol, dRow] = steps[newDirection];
        if (canWalk(col + dCol, row + dRow)) {
          col += dCol;
          row += dRow;
          direction = newDirection;
          break;
        }
      }
    }

    const result = points.map(([col, row]) => ({
                                blockIndex: this.colRowToIndex(col, row),
                                directionX: 0,
                                directionY: 0
                              }));

    for (let i = 1; i < this.numBlocks; i++) {
      const [col0, row0] = points[i - 1];
      const [col1, row1] = points[i];
      if (col0 !== col1) {
        result[i - 1].directionX = result[i].directionX = col1 - col0;
      }
      if (row0 !== row1) {
        result[i - 1].directionY = result[i].directionY = row1 - row0;
      }
    }

    return result;
  }

  /**
   * Converts (col, row) block coordinates to block index.
   *
   * @param {number} col column index of block.
   * @param {number} row row index of block.
   * @return {number} block index
   */
  colRowToIndex(col, row) {
    return col + row * this.numColumns;
  }

  /**
   * Gets block index of the touch event.
   *
   * @param {number} screenX x-coordinate on screen.
   * @param {number} screenY y-coordinate on screen.
   * @return {number} Block ID.
   */
  getBlockIndex(screenX, screenY) {
    const col = Math.floor(screenX / screen.width * this.numColumns);
    const row = Math.floor(screenY / screen.height * this.numRows);
    return this.colRowToIndex(col, row);
  }

  /**
   * Update previous x, y coordinates.
   *
   * @param {number} screenX x-coordinate on screen.
   * @param {number} screenY y-coordinate on screen.
   */
  updatePreviousXY(screenX, screenY) {
    this.previousX = screenX;
    this.previousY = screenY;
  }

  /**
   * Checks if the moving direction conforms to expectSequence.
   *
   * On conducting the God's touch test in OQC, circles are supposed to show up
   * exactly under the touching finger. If this is not the case, the touchscreen
   * is considered bad. It is desirable to catch the mis-location problem too in
   * this test. Such a bad panel may be caught in this test when a finger moves
   * in some direction, its reported coordinates jump in the other directions
   * when the finger moves to near around the problematic spot of the touchscreen.
   *
   * If directionX == 1, the finger is supposed to move to the right.
   * If directionX == -1, the finger is supposed to move to the left.
   * If directionX == 0, the finger is supposed to move in a vertical direction.
   * The rules apply to directionY in a similar way.
   * MOVE_TOLERANCE is used to allow a little deviation.
   *
   * @param {number} screenX x-coordinate on screen.
   * @param {number} screenY y-coordinate on screen.
   * @return {boolean} false if the moving direction is not correct.
   */
  checkDirection(currentBlockIndex, screenX, screenY) {
    if (this.testedBlockCount === this.numBlocks) {
      return true;
    }
    const expectSequenceIndex = this.expectSequence.findIndex(
        (ele) => ele.blockIndex === currentBlockIndex);
    const diffX = screenX - this.previousX;
    const diffY = screenY - this.previousY;
    let checkX = false;
    let checkY = false;
    switch (this.expectSequence[expectSequenceIndex].directionX) {
      case 1:
        checkX = diffX > -MOVE_TOLERANCE;
        break;
      case 0:
        checkX = Math.abs(diffX) < MOVE_TOLERANCE;
        break;
      case -1:
        checkX = diffX < MOVE_TOLERANCE;
        break;
    }
    switch (this.expectSequence[expectSequenceIndex].directionY) {
      case 1:
        checkY = diffY > -MOVE_TOLERANCE;
        break;
      case 0:
        checkY = Math.abs(diffY) < MOVE_TOLERANCE;
        break;
      case -1:
        checkY = diffY < MOVE_TOLERANCE;
        break;
    }
    return checkX && checkY;
  }

  /**
   * Fails this try and if #retries is reached, fail the test.
   *
   * @param {cros.factory.i18n.TranslationDict} message The failed message.
   * @param {number} failedBlock The block index which the failure occurs.
   */
  failThisTry(message, failedBlock) {
    this.prompt(message);
    this.setBlockState(failedBlock, 'failed');
    // Prevent marking multiple failure for a try.
    if (!this.tryFailed) {
      this.tryFailed = true;
      this.tries++;
      if (this.tries > this.maxRetries) {
        this.failTest();
      }
    }
  }

  /**
   * Handles touchstart event.
   *
   * It checks if the touch starts from block (0, 0).
   * If not, prompt operator to do so.
   *
   * @param {number} screenX x-coordinate on screen.
   * @param {number} screenY y-coordinate on screen.
   */
  touchStartHandler(screenX, screenY) {
    const touchBlockIndex = this.getBlockIndex(screenX, screenY);
    this.updatePreviousXY(screenX, screenY);

    if (this.spiralMode &&
        touchBlockIndex !== this.expectSequence[0].blockIndex) {
      this.failThisTry(
          _('Please start drawing from upper-left corner.'), touchBlockIndex);
      this.previousBlockIndex = touchBlockIndex;
      return;
    }

    // Reset blocks for previous failure.
    if (this.tryFailed) {
      this.restartTest();
    }
  }

  /**
   * Handles touchmove event.
   *
   * It'll check if the current block is the expected one.
   * If not, it'll prompt operator to restart from upper-left block.
   *
   * @param {number} screenX x-coordinate on screen.
   * @param {number} screenY y-coordinate on screen.
   */
  touchMoveHandler(screenX, screenY) {
    const touchBlockIndex = this.getBlockIndex(screenX, screenY);

    if (touchBlockIndex !== this.previousBlockIndex) {
      if (this.tryFailed) {
        // Failed case. Either out-of-sequence touch or early finger leaving.
        // Show stronger prompt for drawing multiple unexpected blocks.
        this.failThisTry(
            _('Please leave your finger and restart from upper-left block.'),
            touchBlockIndex);
      } else if (this.spiralMode) {
        if (touchBlockIndex ===
            this.expectSequence[this.testedBlockCount].blockIndex) {
          this.markBlockTested(touchBlockIndex);
        } else {
          this.failThisTry(
              _('Fails to draw blocks in sequence. Please try again.'),
              touchBlockIndex);
        }
      } else {
        this.markBlockTested(touchBlockIndex);
      }
      this.previousBlockIndex = touchBlockIndex;
    }

    if (!this.tryFailed && this.spiralMode &&
        !this.checkDirection(touchBlockIndex, screenX, screenY)) {
      // Failed case. Ask the tester to verify with God's touch test.
      this.failThisTry(
          _('Test failed! ' +
            'Please test this panel carefully with Gods Touch test.'),
          touchBlockIndex);
    }
    this.updatePreviousXY(screenX, screenY);
  }

  /**
   * Handles touchend event.
   *
   * @param {number} screenX x-coordinate on screen.
   * @param {number} screenY y-coordinate on screen.
   */
  touchEndHandler(screenX, screenY) {
    if (this.spiralMode) {
      const touchBlockIndex = this.getBlockIndex(screenX, screenY);

      if (!this.tryFailed) {
        this.failThisTry(
            _('Finger leaving too early. Please try again.'), touchBlockIndex);
      }
    }
  }

  /**
   * Restarts the test.
   *
   * Resets test properties to default and blocks to untested.
   */
  restartTest() {
    this.prompt(
        this.spiralMode ?
            _('Draw blocks from upper-left corner in sequence; Esc to fail.') :
            _('Draw blocks in any order; Esc to fail.'));
    for (let i = 0; i < this.numBlocks; i++) {
      this.setBlockState(i, 'untested');
    }
    this.previousBlockIndex = -1;
    this.testedBlockCount = 0;
    this.tryFailed = false;
  }

  /**
   * Shows a hungry snake animation to guide operator to draw test pattern on
   * the touchscreen.
   *
   * It starts at the expected blocks (index 0). It changes the target block's
   * CSS to demo-0 (head indicator). Then the indicator block moves forward to
   * next expected block after demoIntervalMsecs. As indicator moving forward,
   * it had a tail with lighter color. And the block just behind the tail will
   * be reset to untested CSS.
   */
  async showDemoIndicator() {
    for (let head = 0; head < this.numBlocks + INDICATOR_LENGTH; head++) {
      for (let i = 0; i < this.numBlocks; i++) {
        cros.factory.utils.removeClassesWithPrefix(
            this.getBlockDiv(i), 'demo-');
      }
      for (let indicatorSegment = 0; indicatorSegment < INDICATOR_LENGTH;
           indicatorSegment++) {
        const index = head - indicatorSegment;
        if (index < this.testedBlockCount || index >= this.numBlocks) {
          continue;
        }
        this.getBlockDiv(this.expectSequence[index].blockIndex)
            .classList.add(`demo-${indicatorSegment}`);
      }
      await cros.factory.utils.delay(this.demoIntervalMsecs);
    }
  }

  /**
   * Gets a block div from block index.
   *
   * @param {number} blockIndex
   * @return {?Element}
   */
  getBlockDiv(blockIndex) {
    return document.getElementById(`block-${blockIndex}`);
  }

  /**
   * Sets a block's test state.
   *
   * @param {number} blockIndex
   * @param {boolean} state The state of the block.
   */
  setBlockState(blockIndex, state) {
    const div = this.getBlockDiv(blockIndex);
    cros.factory.utils.removeClassesWithPrefix(div, 'state-');
    div.classList.add(`state-${state}`);
  }

  /**
   * Mark a untested block as tested. Also check if the test is completed.
   *
   * @param {number} blockIndex
   */
  markBlockTested(blockIndex) {
    if (!this.isBlockTested(blockIndex)) {
      this.setBlockState(blockIndex, 'tested');
      this.testedBlockCount++;
      this.checkTestComplete();
    }
  }

  /**
   * Gets whether a block is tested.
   *
   * @param {number} blockIndex
   */
  isBlockTested(blockIndex) {
    return this.getBlockDiv(blockIndex).classList.contains('state-tested');
  }

  /**
   * Checks if test is completed.
   * */
  checkTestComplete() {
    if (this.testedBlockCount === this.numBlocks) {
      window.test.pass();
    }
  }

  /**
   * Fails the test and prints out all the failed items.
   */
  failTest() {
    const getElementIds = (cls) =>
        Array.from(document.getElementsByClassName(cls)).map((ele) => ele.id);

    const untestedBlocks = getElementIds('state-untested');
    const failedBlocks = getElementIds('state-failed');

    let failMessage = 'Touchscreen test failed.';
    if (failedBlocks.length) {
      failMessage += `  Failed blocks: ${failedBlocks.join()}`;
    }
    if (untestedBlocks.length) {
      failMessage += `  Untested blocks: ${untestedBlocks.join()}`;
    }
    window.test.fail(failMessage);
  }

  /**
   * Sets prompt message.
   *
   * @param {cros.factory.i18n.TranslationDict} msg A message object
   *     containing i18n messages.
   */
  prompt(msg) {
    goog.dom.safe.setInnerHtml(
        document.getElementById('prompt'), cros.factory.i18n.i18nLabel(msg));
  }

  /**
   * Handle goofy touch event.
   * @param {string} handlerName The type of handler to trigger.
   * @param {number} normalizedX Normalized x coordinate in [0, 1].
   * @param {number} normalizedY Normalized y coordinate in [0, 1].
   */
  goofyTouchListener(handlerName, normalizedX, normalizedY) {
    const screenX = screen.width * normalizedX;
    const screenY = screen.height * normalizedY;
    this[handlerName](screenX, screenY);
  }
};
