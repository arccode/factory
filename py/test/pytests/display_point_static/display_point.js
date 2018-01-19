// Copyright 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * Gets an random percent position from 0% to 99%.
 * @return {string}
 */
const getRandomPosition = () => `${Math.floor(Math.random() * 100)}%`;

/**
 * API for display_point test.
 */
window.DisplayPointTest = class {
  /*
   * @param {Array<number>} arrayNumberPoint
   * @param {number} pointSize
   */
  constructor(arrayNumberPoint, pointSize) {
    this.pointSize = pointSize;
    this.displayDiv = document.getElementById('fullscreen');
  }

  /**
   * Setups point in the subtest.
   * @param {number} numberPoint number of points
   * @param {string} backgroundColor background color of the screen
   * @param {string} pointColor color of the points
   */
  setupPoints(numberPoint, backgroundColor, pointColor) {
    this.displayDiv.innerHTML = '';
    cros.factory.utils.removeClassesWithPrefix(this.displayDiv, 'bg-');
    this.displayDiv.classList.add(`bg-${backgroundColor}`);

    for (let p = 0; p < numberPoint; ++p) {
      const div = document.createElement('div');
      div.classList.add('point', `bg-${pointColor}`);
      div.style.top = getRandomPosition();
      div.style.left = getRandomPosition();
      div.style.width = `${this.pointSize}px`;
      div.style.height = `${this.pointSize}px`;
      this.displayDiv.appendChild(div);
    }
  }

  /**
   * Switches the fullscreen display on. Sets displayDiv
   * visibility to visible and enlarges the test iframe to fullscreen.
   */
  switchDisplayOn() {
    this.displayDiv.classList.remove('hidden');
    window.test.setFullScreen(true);
  }

  /**
   * Switches the fullscreen display off. Sets displayDiv
   * visibility to hidden and restores the test iframe to normal.
   */
  switchDisplayOff() {
    this.displayDiv.classList.add('hidden');
    window.test.setFullScreen(false);
  }
};
