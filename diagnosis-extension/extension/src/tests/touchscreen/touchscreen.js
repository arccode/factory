/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {TestCase} from '/src/tests/test_case.js';
import {LoggingUtils} from '/src/utils/logging_utils.js';
import {UiUtils} from '/src/utils/ui_utils.js';

export class TouchscreenTest extends TestCase {
  constructor() {
    super();
    this.html = '/src/tests/touchscreen/touchscreen.html';
    this.name = 'Touchscreen';
    this.row = 3;
    this.col = 7;
    this.previousTouchedIndex = -1;

    this.keyDown = this.keyDown.bind(this);
    this.handleTouchStart = this.handleTouchStart.bind(this);
    this.handleTouchMove = this.handleTouchMove.bind(this);
    this.handleTouchEnd = this.handleTouchEnd.bind(this);
  }

  async setUp() {
    await this.setHTML();
    this.initTouchEvent();
    this.setEndTestPromise();
  }

  async runTest() {
    this.setUpTestBoard();
    this.setUpUi();

    // The test requires human interaction, so we just wait for the test to end.
    const result = await this.waitEndTestResult();
    if (!result.success) {
      this.failTest(result.message);
    }
  }

  tearDown() {
    this.clearHTML();
    UiUtils.exitFullscreen();
  }

  setUpUi() {
    const testGrid = document.getElementById('block-test');
    testGrid.style.grid =
        `repeat(${this.row}, 1fr) / repeat(${this.col}, 1fr)`;

    // Remove the arrow class for the end block of spiral path.
    const endBlock = this.rowColToIndex(this.lastRow, this.lastCol);

    for (let i = 0; i < this.row * this.col; i++) {
      const div = document.createElement('div');
      div.id = `block-${i}`;
      div.classList.add('block');
      const inner_div = document.createElement('div');
      const [indexY, indexX] = this.indexToRowCol(i);
      if (i !== endBlock) inner_div.classList.add('arrow');
      inner_div.classList.add(this.grid[indexY][indexX].class);
      div.appendChild(inner_div);
      testGrid.appendChild(div);
    }
  }

  /** Start test by pressing SPACE. */
  keyDown(e) {
    if (!this.enteredTest && e.code === 'Space') {
      this.enteredTest = true;
      UiUtils.requestFullscreen();
      document.getElementById('block-test').hidden = false;
    } else if (this.enteredTest) {
      LoggingUtils.log('Test has started. Please slide the screen.');
    } else {
      this.endTest(false, 'Failed. Please press the correct key.');
    }
  }

  initTouchEvent() {
    // Set keyEvent for entering touchscreen test.
    document.addEventListener('keydown', this.keyDown);
    const element = document.getElementById('block-test');
    element.addEventListener('touchstart', this.handleTouchStart);
    element.addEventListener('touchmove', this.handleTouchMove);
    element.addEventListener('touchend', this.handleTouchEnd);
  }

  removeTouchEvent() {
    document.removeEventListener('keydown', this.keyDown);
    const element = document.getElementById('block-test');
    element.removeEventListener('touchstart', this.handleTouchStart);
    element.removeEventListener('touchmove', this.handleTouchMove);
    element.removeEventListener('touchend', this.handleTouchEnd);
  }

  /**
   * Create Touchscreen block tests.
   * Starts from upper-left corner, and goes in right-down-left-up
   * direction until the center of the screen.
   */
  setUpTestBoard() {
    let rowStart = 0;
    let columnStart = 0;
    let rowEnd = this.row - 1;
    let columnEnd = this.col - 1;
    let order = 0;
    this.grid = [];
    // Record the row and col index of the last block
    this.lastRow = 0;
    this.lastCol = 0;

    for (let i = 0; i < this.row; i++) {
      this.grid.push([]);
      for (let j = 0; j < this.col; j++) {
        this.grid[i].push({order: 0, class: ''});
      }
    }
    const assignGrid = (row, col, direction) => {
      this.grid[row][col].order = order++;
      this.grid[row][col].class = direction;
      [this.lastRow, this.lastCol] = [row, col];
    };
    // assign spiral index and arrow class for grid in spiral order.
    while (rowStart <= rowEnd && columnStart <= columnEnd) {
      for (let col = columnStart; col < columnEnd; col++) {
        assignGrid(rowStart, col, 'arrowRight');
      }
      for (let row = rowStart; row < rowEnd; row++) {
        assignGrid(row, columnEnd, 'arrowDown');
      }
      if (rowStart < rowEnd && columnStart < columnEnd) {
        for (let col = columnEnd; col > columnStart; col--) {
          assignGrid(rowEnd, col, 'arrowLeft');
        }
        for (let row = rowEnd; row > rowStart + 1; row--) {
          assignGrid(row, columnStart, 'arrowTop');
        }
        assignGrid(rowStart + 1, columnStart, 'arrowRight');
      }
      else if (columnStart == columnEnd && rowStart < rowEnd) {
        assignGrid(rowEnd, columnEnd, 'arrowDown');
      }
      else if (rowStart == rowEnd && columnStart < columnEnd) {
        assignGrid(rowEnd, columnEnd, 'arrowRight');
      }
      rowStart++;
      rowEnd--;
      columnStart++;
      columnEnd--;
    }
    this.grid[this.lastRow][this.lastCol].class = 'goal';
  }

  /** Get the index of a block from a given position. */
  getBlockIndex(screenX, screenY) {
    let col = Math.floor(screenX * this.col / window.innerWidth);
    let row = Math.floor(screenY * this.row / window.innerHeight);
    return [row, col];
  }

  /** Get row and column and return block number. */
  rowColToIndex(row, col) {
      return col + row * this.col;
  }

  /** Get block number and convert to row and column for the grid. */
  indexToRowCol(index){
      let col = Math.floor(index % this.col);
      let row = Math.floor(index / this.col);
      return [row, col];
  }

  /** Show if the block currently touching is on the right route. */
  touchBlock(row, col) {
    const id = this.rowColToIndex(row, col);
    const element = document.getElementById(`block-${id}`);
    let order = this.grid[row][col].order;
    if (!this.errorInTest &&
        this.previousTouchedIndex == order - 1 && element) {
      element.classList.add('succeed');
      this.previousTouchedIndex = order;
    } else {
      if (element) element.classList.add('failed');
      this.errorInTest = true;
    }
  }

  handleTouchStart(event) {
    this.errorInTest = false;
    if (this.enteredTest) {
      const screenX = event.changedTouches[0].screenX;  // col
      const screenY = event.changedTouches[0].screenY;  // row
      const [row, col] = this.getBlockIndex(screenX, screenY);
      this.touchBlock(row, col);
    } else {
      this.endTest(false, 'Failed. Please press space to start the test.');
    }
  }

  handleTouchMove(event) {
    const screenX = event.changedTouches[0].screenX;
    const screenY = event.changedTouches[0].screenY;
    const [row, col] = this.getBlockIndex(screenX, screenY);
    if (this.grid[row][col].order != this.previousTouchedIndex) {
      this.touchBlock(row, col);
    }
  }

  handleTouchEnd(event) {
    if (!this.errorInTest &&
      this.previousTouchedIndex === this.row * this.col - 1) {
      this.endTest(true);
    } else {
      this.endTest(false, 'Failed. Please try again.');
    }
  }

  endTest(success, message) {
    this.removeTouchEvent();
    this.previousTouchedIndex = -1;
    this.enteredTest = false;
    this.sendEndTestResult(success, message);
  }
}
