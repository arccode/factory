// Copyright 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

window.KeyboardTest = class {
  /**
   * @param {string} layout
   * @param {!Object} bindings
   */
  constructor(layout, bindings, numpad_keys) {
    const keyContainer = document.getElementById('keyboard-keys');
    for (const keycode of Object.keys(bindings)) {
      for (const [left, top, width, height] of bindings[keycode]) {
        const div = document.createElement('div');
        div.dataset.keycode = keycode;
        div.style.left = left;
        div.style.top = top;
        div.style.width = width;
        div.style.height = height;
        div.classList.add('main-keyboard-key');
        div.classList.add('keyboard-test-key');
        keyContainer.appendChild(div);
      }
    }

    const imageContainer = document.getElementById('keyboard-test-image');
    const img = new Image();
    img.id = 'layout-image';
    img.src = `${layout}.png`;

    img.onload = () => {
      const xOffset = (imageContainer.clientWidth - img.width) / 2;
      keyContainer.style.left = xOffset;
    };
    imageContainer.appendChild(img);

    const numpadContainer = document.getElementById('numpad')
    if (numpad_keys) {
      numpadContainer.style.display = 'grid'
      for (const keycode of numpad_keys) {
        const div = document.createElement('div');
        div.classList.add('numpad-key');
        div.classList.add('keyboard-test-key');
        div.dataset.keycode = keycode;
        numpadContainer.appendChild(div);
      }
    }

    // The numpad keys are appended at run time, so the width/height of
    // keyboardContainer is not updated. Thus we cannot directly use
    // fitToStateContainer here.
    const keyboardContainer = document.getElementById('keyboard');
    const {width: stateWidth, height: stateHeight} =
        window.template.getStateSize();
    const elementWidth = keyboardContainer.scrollWidth +
        numpadContainer.scrollWidth;
    const elementHeight = Math.max(
        keyboardContainer.scrollHeight, numpadContainer.scrollHeight);
    const minRatio =
        Math.min(1, stateWidth / elementWidth, stateHeight / elementHeight);
    keyboardContainer.style.transform = `scale(${minRatio})`;

    window.addEventListener('resize', () => {
      this.fitToStateContainer(keyboardContainer);
    })
  }

  /**
   * Add transform: scale(xxx) to element so it's inside state container.
   * @param {!Element} element
   */
  fitToStateContainer(element) {
    const {width: stateWidth, height: stateHeight} =
        window.template.getStateSize();
    const elementWidth = element.scrollWidth;
    const elementHeight = element.scrollHeight;
    const minRatio =
        Math.min(1, stateWidth / elementWidth, stateHeight / elementHeight);
    element.style.transform = `scale(${minRatio})`;
  }

  /**
   * Mark the keycode state on test UI.
   * @param {number} keycode
   * @param {string} state
   * @param {number} numLeft
   */
  markKeyState(keycode, state, numLeft) {
    const content = numLeft === 0 ? '' : numLeft.toString();
    for (const div of document.querySelectorAll(
             `.keyboard-test-key[data-keycode="${keycode}"]`)) {
      cros.factory.utils.removeClassesWithPrefix(div, 'state-');
      div.classList.add(`state-${state}`);
      div.innerText = content;
    }
  }
};
