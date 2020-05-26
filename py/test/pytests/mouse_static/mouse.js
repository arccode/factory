// Copyright 2020 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for mouse test.
 */
window.MouseTest = class {
  constructor() {
    this.initMoveTable(document.getElementById('first-container'));
    this.initClickTable(document.getElementById('second-container'));
  }

  /**
   * Initialize the mouse move table.
   * @param {!Element} container The parent element.
   */
  initMoveTable(container) {
    const moveTable = createTable(['up', 'down', 'left', 'right'], 'move');
    moveTable.style.flex = 1;
    container.appendChild(moveTable);
  }

  /**
   * Initialize the button click table.
   * @param {!Element} container The parent element.
   */
  initClickTable(container) {
    const clickTable = createTable(['left', 'middle', 'right'], 'click');
    clickTable.style.flex = 1;
    container.appendChild(clickTable);
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
   * Marks the given move direction as "tested" on the test ui.
   * @param {string} direction
   */
  markMoveDirectionTested(direction) {
    this.markElementState(`move-${direction}`, 'tested');
  }

  /**
   * Marks the given click button as "tested" on the test ui.
   * @param {string} button
   */
  markClickButtonTested(button) {
    this.markElementState(`click-${button}`, 'tested');
  }

  /**
   * Marks the given click button as "down" on the test ui.
   * @param {string} button
   */
  markClickButtonDown(button) {
    this.markElementState(`click-${button}`, 'down');
  }
};

/**
 * Creates a 1-D table element with specified names.
 * Each td in the table contains one div with id prefix-name and the specified
 * CSS class.
 * @param {string[]} names
 * @param {string} prefix
 * @return {!Element}
 */
function createTable(names, prefix) {
  const n = names.length;
  const table = goog.dom.createDom('div', {
    'class': 'table-div',
    'style':
        `grid: repeat(1, 1fr) / repeat(${n}, 1fr)`
  });
  for (let i = 0; i < n; ++i) {
    const id = `${prefix}-${names[i]}`;
    const div = goog.dom.createDom('div', {'id': id}, id);
    table.appendChild(div);
  }
  return table;
}
