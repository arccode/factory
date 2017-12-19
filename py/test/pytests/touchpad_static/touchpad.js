// Copyright 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for touchpad test.
 */
window.TouchpadTest = class {
  /*
   * @param {number} xSegments
   * @param {number} ySegments
   * @param {number} countTarget
   * @param {number} quadCountTarget
   */
  constructor(xSegments, ySegments, countTarget, quadCountTarget) {
    this.xSegments = xSegments;
    this.ySegments = ySegments;
    this.countTarget = countTarget;
    this.quadCountTarget = quadCountTarget;

    this.initTouchScrollTables(document.getElementById('first-container'));
    this.initQuadrantClickTable(document.getElementById('second-container'));
  }

  /**
   * Initialize the touch and scroll tables.
   * @param {!Element} container The parent element.
   */
  initTouchScrollTables(container) {
    const touchTable =
        createTable(this.ySegments, this.xSegments, 'touch');
    touchTable.style.flex = this.xSegments;
    container.appendChild(touchTable);

    const scrollTable = createTable(this.ySegments, 1, 'scroll');
    scrollTable.style.flex = 1;
    container.appendChild(scrollTable);
  }

  /**
   * Initialize the quadrant click table.
   * @param {!Element} container The parent element.
   */
  initQuadrantClickTable(container) {
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
            'div', {'id': `quadrant-${quad}`}, `Click ${text} Corner`,
            goog.dom.createDom('div', {'id': `quadrant-${quad}-count`}));
        quadrantTable.appendChild(div);
      }
      for (let i = 1; i <= 4; i++) {
        this.updateQuadrantCountText(i, 0);
      }
    }

    for (const button of ['left', 'right']) {
      const div = goog.dom.createDom(
          'div', 'click', goog.dom.createDom('div', {
            'id': `${button}-circle`,
            'class': 'circle'
          }),
          goog.dom.createDom('span', {'id': `${button}-text-cell`}));
      container.appendChild(div);
    }

    this.updateCircleCountText(0, 0);
  }

  /**
   * Marks element with given id as tested on the test ui.
   * @param {string} id
   * @param {string} state
   */
  markElementState(id, state) {
    const element = document.getElementById(id);
    if (element) {
      cros.factory.utils.removeClassesWithPrefix(element, 'state-');
      element.classList.add(`state-${state}`);
    }
  }

  /**
   * Marks the given (x,y) sector as "tested" on the test ui.
   * @param {number} x
   * @param {number} y
   */
  markSectorTested(x, y) {
    this.markElementState(`touch-x-${x}-y-${y}`, 'tested');
  }

  /**
   * Marks the given y scroll sector as "tested" on the test ui.
   * @param {number} y
   */
  markScrollSectorTested(y) {
    this.markElementState(`scroll-x-0-y-${y}`, 'tested');
  }

  /**
   * Marks the given quadrant sector as "tested" on the test ui.
   * @param {number} quadrant
   */
  markQuadrantSectorTested(quadrant) {
    this.markElementState(`quadrant-${quadrant}`, 'tested');
  }

  /**
   * Marks the given circle as "down" on the test ui.
   * @param {string} id
   */
  markCircleDown(id) {
    this.markElementState(`${id}-circle`, 'down');
  }

  /**
   * Marks the given circle as "tested" on the test ui.
   * @param {string} id
   */
  markCircleTested(id) {
    this.markElementState(`${id}-circle`, 'tested');
  }

  /**
   * Updates the text of the circle cells on the test ui.
   */
  updateCircleCountText(leftCount, rightCount) {
    document.getElementById('left-text-cell').innerText =
        `${leftCount} / ${this.countTarget}`;
    document.getElementById('right-text-cell').innerText =
        `${rightCount} / ${this.countTarget}`;
  }

  /**
   * Update the number of click for each quadrant
   * @param {number} quad
   * @param {number} count
   */
  updateQuadrantCountText(quad, count) {
    document.getElementById(`quadrant-${quad}-count`).innerText =
        `${count} / ${this.quadCountTarget}`;
  }
};

/**
 * Creates a table element with specified row number and column number.
 * Each td in the table contains one div with id prefix-x-x_number-y-y_number
 * and the specified CSS class.
 * @param {number} rowNumber
 * @param {number} colNumber
 * @param {string} prefix
 * @return {!Element}
 */
function createTable(rowNumber, colNumber, prefix) {
  const table = goog.dom.createDom('div', {
    'class': 'table-div',
    'style':
        `grid: repeat(${rowNumber}, 1fr) / repeat(${colNumber}, 1fr)`
  });
  for (let y = 0; y < rowNumber; ++y) {
    for (let x = 0; x < colNumber; ++x) {
      const id = `${prefix}-x-${x}-y-${y}`;
      const div = goog.dom.createDom('div', {'id': id}, id);
      table.appendChild(div);
    }
  }
  return table;
}
