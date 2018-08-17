/* Copyright 2018 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {Component, OnInit} from '@angular/core';
import {TestCase} from '../../interfaces/test-case';
import {TestRunService} from '../../test-run-service';

const successColor = '#99ff99';
const errorColor = '#ff8888';

/** Touchscreen Test */
@Component({
  selector: 'app-touchscreen',
  templateUrl: './touchscreen.component.html',
  styleUrls: ['./touchscreen.component.css']
})
export class TouchscreenComponent extends TestCase implements OnInit {
  constructor(private readonly testRunService: TestRunService) {
    super();
    this.handleTouchStart = this.handleTouchStart.bind(this);
    this.handleTouchMove = this.handleTouchMove.bind(this);
    this.handleTouchEnd = this.handleTouchEnd.bind(this);
  }

  args: {[key: string]: string} = {};
  inTesting: boolean = false;
  grid: {index: number, class: string}[][] = [];
  previousTouchIndex: number = -1;
  errorCount: number = 0;
  isErrorInCurrentTest: boolean = false;
  remainingTime: number = 0;

  setUp(args: {[key: string]: string}): void {
    this.args = args;
    this.init();
  }

  ngOnInit(): void {}

  runTest(): void {
    console.log(`${this.getTestName()}.runTest is called`);
  }

  getTestName(): string {
    return 'Touchscreen';
  }

  /** Init Test UI */
  initTestBoard() {
    let rowStart = 0;
    let rowEnd = parseInt(this.args.ySegments) - 1;
    let columnStart = 0;
    let columnEnd = parseInt(this.args.xSegments) - 1;
    let index = 0;

    let lastPosition: [number, number] = [0, 0];
    this.grid = [];
    for (let i = 0; i < parseInt(this.args.ySegments); i++) {
      this.grid[i] = [];
      for (let j = 0; j < parseInt(this.args.xSegments); j++) {
        this.grid[i][j] = {index: 0, class: ''};
      }
    }
    /** assign index and arrow class for grid in spiral order */
    while (rowStart <= rowEnd && columnStart <= columnEnd) {
      for (let col = columnStart; col <= columnEnd; col++) {
        this.grid[rowStart][col].index = index++;
        this.grid[rowStart][col].class = 'arrow arrowRight';
        lastPosition = [rowStart, col];
      }
      for (let row = rowStart + 1; row <= rowEnd; row++) {
        this.grid[row][columnEnd].index = index++;
        this.grid[row][columnEnd].class = 'arrow arrowDown';
        lastPosition = [row, columnEnd];
      }
      if (rowStart < rowEnd && columnStart < columnEnd) {
        for (let col = columnEnd - 1; col > columnStart; col--) {
          this.grid[rowEnd][col].index = index++;
          this.grid[rowEnd][col].class = 'arrow arrowLeft';
          lastPosition = [rowEnd, col];
        }
        for (let row = rowEnd; row > rowStart; row--) {
          this.grid[row][columnStart].index = index++;
          this.grid[row][columnStart].class = 'arrow arrowTop';
          lastPosition = [row, columnStart];
        }
      }
      rowStart++;
      rowEnd--;
      columnStart++;
      columnEnd--;
    }
    this.grid[lastPosition[0]][lastPosition[1]].class = 'remainingTime';
  }

  /** Touch Event */
  initTouchEvent() {
    let element = document.getElementsByTagName('table')[0];
    element.addEventListener('touchstart', this.handleTouchStart, false);
    element.addEventListener('touchmove', this.handleTouchMove, false);
    element.addEventListener('touchend', this.handleTouchEnd, false);
  };

  removeTouchEvent() {
    let element = document.getElementsByTagName('table')[0];
    element.removeEventListener('touchstart', this.handleTouchStart, false);
    element.removeEventListener('touchmove', this.handleTouchMove, false);
    element.removeEventListener('touchend', this.handleTouchEnd, false);
  };

  touchBlock(id: string) {
    const element = document.getElementById(id);
    if (!this.isErrorInCurrentTest &&
        this.previousTouchIndex == parseInt(id) - 1 && element) {
      element.style.backgroundColor = successColor;
    } else {
      if (element) element.style.backgroundColor = errorColor;
      this.isErrorInCurrentTest = true;
    }
    this.previousTouchIndex = parseInt(id);
  };

  handleTouchStart(e: TouchEvent) {
    document.getElementsByTagName('h1')[0].style.display = 'none';

    this.isErrorInCurrentTest = false;
    for (let i = 0; i < parseInt(this.args.ySegments); i++) {
      for (let j = 0; j < parseInt(this.args.xSegments); j++) {
        const element = document.getElementById(
            (i * parseInt(this.args.xSegments) + j).toString());
        if (element) element.style.backgroundColor = 'transparent';
      }
    }

    this.touchBlock((e.target as HTMLTextAreaElement).id);
  }

  handleTouchMove(e: TouchEvent) {
    let screenX = e.changedTouches[0].screenX;
    let screenY = e.changedTouches[0].screenY;
    let posX = 0;
    let posY = 0;
    posX = Math.floor(screen.width / (parseInt(this.args.xSegments) * screenX));
    posY =
        Math.floor(screen.height / (parseInt(this.args.ySegments) * screenY));
    if (this.grid[posY][posX].index != this.previousTouchIndex) {
      this.touchBlock(this.grid[posY][posX].index.toString());
    }
  }

  handleTouchEnd() {
    if (!this.isErrorInCurrentTest &&
        this.previousTouchIndex ==
            parseInt(this.args.xSegments) * parseInt(this.args.ySegments) - 1) {
      this.removeTouchEvent();
      this.endTest(
          true,
          `Use ${
              parseFloat(this.args.timeout) -
              this.remainingTime} second to finish test.`);
    }
    this.previousTouchIndex = -1;
    this.isErrorInCurrentTest = false;
    this.errorCount++;
    if (this.errorCount > 3) {
      this.endTest(false, `Faild over 3 times`);
    }
  }

  setTestTimeout() {
    setTimeout(() => {
      this.remainingTime -= 0.1;
      let remainingTimeDom =
          document.getElementsByClassName('remainingTime')[0];
      if (remainingTimeDom) {
        remainingTimeDom.innerHTML = this.remainingTime.toFixed(1);
      }
      if (this.remainingTime >= 0 && this.inTesting) {
        this.setTestTimeout();
      } else if (this.inTesting) {
        this.endTest(false, `Timed out.`);
      }
    }, 100);
  }

  /** init test */
  init() {
    this.remainingTime = parseFloat(this.args.timeout);
    this.inTesting = true;
    this.errorCount = 0;
    this.initTestBoard();
    this.initTouchEvent();
    this.setTestTimeout();
  }

  /** end test */
  endTest(success: boolean, message: string) {
    this.inTesting = false;
    this.testRunService.endTest(success, message);
  }
}

export const TOUCHSCREEN_ARGS_SPEC = [
  {
    name: 'xSegments',
    help: 'Number of segments in x-axis.',
    default: 5,
    type: 'number'
  },
  {
    name: 'ySegments',
    help: 'Number of segments in y-axis.',
    default: 5,
    type: 'number'
  },
  {name: 'timeout', help: 'Timeout', default: 30, type: 'number'}
];
