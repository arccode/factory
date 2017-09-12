// Copyright 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for touchpad test.
 * @constructor
 * @param {number} xSegments
 * @param {number} ySegments
 * @param {number} countTarget
 * @param {number} quadCountTarget
 */
var TouchpadTest = function(
    xSegments, ySegments, countTarget, quadCountTarget) {
  this.xSegments = xSegments;
  this.ySegments = ySegments;
  this.leftCount = 0;
  this.rightCount = 0;
  this.countTarget = countTarget;
  this.quadCountTarget = quadCountTarget;
  this.quadrantCount = Array(4).fill(0);
};

/**
 * Creates a touchpad test and runs it.
 * @param {number} xSegments
 * @param {number} ySegments
 * @param {number} countTarget
 * @param {number} quadCountTarget
 */
function setupTouchpadTest(xSegments, ySegments, countTarget, quadCountTarget) {
  window.touchpadTest =
      new TouchpadTest(xSegments, ySegments, countTarget, quadCountTarget);
  window.touchpadTest.init();
}

/**
 * Initialize the touchpad UI.
 */
TouchpadTest.prototype.init = function() {
  const container = document.getElementById('state');

  const secondContainer =
      goog.dom.createDom('div', {'id': 'touchpad-test-second-container'});
  container.prepend(secondContainer);
  this.initQuadrantClickTable(secondContainer);

  const firstContainer =
      goog.dom.createDom('div', {'id': 'touchpad-test-first-container'});
  container.prepend(firstContainer);
  this.initTouchScrollTables(firstContainer);
};

/**
 * Initialize the touch and scroll tables.
 * @param {!Element} container The parent element.
 */
TouchpadTest.prototype.initTouchScrollTables = function(container) {
  const touchTable = createTable(
      this.ySegments, this.xSegments, 'touch', 'touchpad-test-sector');
  touchTable.style.flex = this.xSegments;
  container.appendChild(touchTable);

  const scrollTable =
      createTable(this.ySegments, 1, 'scroll', 'touchpad-test-sector');
  scrollTable.style.flex = 1;
  container.appendChild(scrollTable);
};

/**
 * Initialize the quadrant click table.
 * @param {!Element} container The parent element.
 */
TouchpadTest.prototype.initQuadrantClickTable = function(container) {
  // This is for SMT test, operator cannot click for each quadrant
  if (this.quadCountTarget) {
    const quadrantTable = goog.dom.createDom('div', {'id': 'quadrant-table'});
    container.appendChild(quadrantTable);

    const quadrants = [
      [2, 'Left-Top'], [1, 'Right-Top'], [3, 'Left-Bottom'],
      [4, 'Right-Bottom']
    ];
    for (const [quad, text] of quadrants) {
      const div = goog.dom.createDom(
          'div', {'id': 'quadrant' + quad, 'class': 'touchpad-test-sector'},
          'Click ' + text + ' Corner',
          goog.dom.createDom('div', {'id': 'quadrant' + quad + '-count'}));
      quadrantTable.appendChild(div);
    }
    for (let i = 1; i <= 4; i++) {
      this.updateQuadrantCountText(i);
    }
  }

  for (const button of ['left', 'right']) {
    const div = goog.dom.createDom(
        'div', 'touchpad-test-click', goog.dom.createDom('div', {
          'id': button + '-circle',
          'class': 'touchpad-test-circle'
        }),
        goog.dom.createDom('span', {'id': button + '-text-cell'}));
    container.appendChild(div);
  }

  this.updateCircleCountText();
};

/**
 * Marks the given (x,y) sector as "tested" on the test ui.
 * @param {number} x
 * @param {number} y
 */
TouchpadTest.prototype.markSectorTested = function(x, y) {
  var id = 'touch-x-' + x + '-y-' + y;
  var element = document.getElementById(id);
  if (element) {
    element.classList.add('tested');
  }
  this.checkTestComplete();
};

/**
 * Marks the given y scroll sector as "tested" on the test ui.
 * @param {number} y
 */
TouchpadTest.prototype.markScrollSectorTested = function(y) {
  var id = 'scroll-x-0-y-' + y;
  var element = document.getElementById(id);
  if (element) {
    element.classList.add('tested');
  }
  this.checkTestComplete();
};

/**
 * Marks the given quadrant sector as "tested" on the test ui.
 * @param {number} quadrant
 */
TouchpadTest.prototype.markQuadrantSectorTested = function(quadrant) {
  var id = 'quadrant' + quadrant;
  var element = document.getElementById(id);
  if (element) {
    element.classList.add('tested');
  }
  this.checkTestComplete();
};

/**
 * Marks the given circle as "down" on the test ui.
 * @param {string} id
 */
TouchpadTest.prototype.markCircleDown = function(id) {
  var element = document.getElementById(id);
  if (element) {
    element.classList.remove('tested');
    element.classList.add('down');
  }
};

/**
 * Marks the given circle as "tested" on the test ui.
 * @param {string} id
 */
TouchpadTest.prototype.markCircleTested = function(id) {
  var element = document.getElementById(id);
  if (element) {
    element.classList.remove('down');
    element.classList.add('tested');
  }
  this.checkTestComplete();
};

/**
 * Updates the text of the circle cells on the test ui.
 */
TouchpadTest.prototype.updateCircleCountText = function() {
  document.getElementById('left-text-cell').innerText =
      this.leftCount + ' / ' + this.countTarget;
  document.getElementById('right-text-cell').innerText =
      this.rightCount + ' / ' + this.countTarget;
};

/**
 * Adds one count to the left circle count.
 */
TouchpadTest.prototype.updateLeftCount = function() {
  if (this.leftCount < this.countTarget) {
    this.leftCount++;
    this.updateCircleCountText();
  }
  this.markCircleTested('left-circle');
};

/**
 * Adds one count to the right circle count.
 */
TouchpadTest.prototype.updateRightCount = function() {
  if (this.rightCount < this.countTarget) {
    this.rightCount++;
    this.updateCircleCountText();
  }
  this.markCircleTested('right-circle');
};

/**
 * Adds a mark to quadrant.
 * @param {number} quad
 */
TouchpadTest.prototype.updateQuadrant = function(quad) {
  if (this.quadrantCount[quad - 1] < this.quadCountTarget) {
    this.quadrantCount[quad - 1]++;
    this.updateQuadrantCountText(quad);
    if (this.quadrantCount[quad - 1] == this.quadCountTarget) {
      this.markQuadrantSectorTested(quad);
    }
  }
};

/**
 * Update the number of click for each quadrant
 * @param {number} quad
 */
TouchpadTest.prototype.updateQuadrantCountText = function(quad) {
  var id = 'quadrant' + quad + '-count';
  var element = document.getElementById(id);

  if (element) {
    element.innerText =
        this.quadrantCount[quad - 1] + ' / ' + this.quadCountTarget;
  }
};

/**
 * Get list of all untested sectors.
 * @return {!NodeList}
 */
TouchpadTest.prototype.getUntestedSectors = function() {
  return document.querySelectorAll('.touchpad-test-sector:not(.tested)');
};

/**
 * Checks if test is completed by checking the number of sectors that
 * haven't passed the test. Also check that click counts reach target or not.
 */
TouchpadTest.prototype.checkTestComplete = function() {
  if (!this.getUntestedSectors().length && this.leftCount == this.countTarget &&
      this.rightCount == this.countTarget) {
    window.test.pass();
  }
};

/**
 * Fails the test and prints out all the failed items.
 */
TouchpadTest.prototype.failTest = function() {
  var failedSectors = [];

  this.getUntestedSectors().forEach(function(element) {
    failedSectors.push(element.id);
  });

  var failMsg = 'Touchpad test failed. Malfunction sectors: ';
  failMsg += failedSectors.join(', ');

  if (this.leftCount < this.countTarget) {
    failMsg += ' left click count: ' +
        document.getElementById('left-text-cell').innerText;
  }
  if (this.rightCount < this.countTarget) {
    failMsg += ' right click count: ' +
        document.getElementById('right-text-cell').innerText;
  }

  window.test.fail(failMsg);
};

/**
 * Creates a table element with specified row number and column number.
 * Each td in the table contains one div with id prefix-x-x_number-y-y_number
 * and the specified CSS class.
 * @param {number} rowNumber
 * @param {number} colNumber
 * @param {string} prefix
 * @param {string} className
 * @return {!Element}
 */
function createTable(rowNumber, colNumber, prefix, className) {
  var table = goog.dom.createDom('div', {
    'class': 'touchpad-test-table',
    'style':
        'grid: repeat(' + rowNumber + ', 1fr) / repeat(' + colNumber + ', 1fr)'
  });
  for (var y = 0; y < rowNumber; ++y) {
    for (var x = 0; x < colNumber; ++x) {
      var id = prefix + '-x-' + x + '-y-' + y;
      var div = goog.dom.createDom('div', {'class': className, 'id': id}, id);
      table.appendChild(div);
    }
  }
  return table;
}

/**
 * Marks a sector as tested.
 * @param {number} x
 * @param {number} y
 */
function markSectorTested(x, y) {
  window.touchpadTest.markSectorTested(x, y);
}

/**
 * Marks a scroll secotr as tested.
 * @param {number} y
 */
function markScrollSectorTested(y) {
  window.touchpadTest.markScrollSectorTested(y);
}

/**
 * Marks single click as down.
 * @param {number} quadrant
 */
function markSingleClickDown(quadrant) {
  window.touchpadTest.markCircleDown('left-circle');
}

/**
 * Marks single click as tested.
 * @param {number} quadrant
 */
function markSingleClickUp(quadrant) {
  window.touchpadTest.updateLeftCount();
  window.touchpadTest.updateQuadrant(quadrant);
}

/**
 * Marks double click as down.
 */
function markDoubleClickDown() {
  window.touchpadTest.markCircleDown('right-circle');
}

/**
 * Marks double click as tested.
 */
function markDoubleClickUp() {
  window.touchpadTest.updateRightCount();
}

/**
 * Fails the test.
 */
function failTest() {
  if (!window.touchpadTest) {
    window.test.fail('Timeout while waiting for SPACE');
  } else {
    window.touchpadTest.failTest();
  }
}
