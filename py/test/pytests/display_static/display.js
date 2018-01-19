// Copyright 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for display test.
 */
window.DisplayTest = class {
  /**
   * @param {!Array<string>} items
   */
  constructor(items) {
    this.focusItem = 0;
    this.itemList = items;
    this.itemStatusList = [];

    const table = document.getElementById('display-table');
    for (const item of this.itemList) {
      const itemName = document.createElement('div');
      itemName.classList.add('center');
      itemName.appendChild(cros.factory.i18n.i18nLabelNode(_(item)));
      table.appendChild(itemName);

      const itemStatus = document.createElement('div');
      itemStatus.dataset.name = item;
      itemStatus.classList.add('center');
      itemStatus.classList.add('subtest-status-untested');
      itemStatus.appendChild(cros.factory.i18n.i18nLabelNode('Untested'));
      this.itemStatusList.push(itemStatus);

      table.appendChild(itemStatus);
    }

    this.fullscreenElement = document.getElementById('display-full-screen');

    this.displayDiv = document.getElementById('display-div');
    this._setDisplayDivClass();

    this.fullscreen = false;
  }

  /**
   * Setups display div style.
   * @private
   */
  _setDisplayDivClass() {
    cros.factory.utils.removeClassesWithPrefix(this.displayDiv, 'subtest-');
    this.displayDiv.classList.add(`subtest-${this.itemList[this.focusItem]}`);
  }

  /**
   * Toggles the fullscreen display visibility.
   */
  toggleFullscreen() {
    this.fullscreen = !this.fullscreen;
    this.fullscreenElement.classList.toggle('hidden', !this.fullscreen);
    window.test.setFullScreen(this.fullscreen);
  }

  /**
   * Changes the status in test table based success or not.
   * Setups the display style for the next subtest.
   * Judges the whole test if there is no more subtests.
   * @param {boolean} success
   */
  judgeSubTest(success) {
    const element = this.itemStatusList[this.focusItem];
    element.innerHTML = '';
    cros.factory.utils.removeClassesWithPrefix(element, 'subtest-status-');
    if (success) {
      element.classList.add('subtest-status-passed');
      element.appendChild(cros.factory.i18n.i18nLabelNode('Passed'));
    } else {
      element.classList.add('subtest-status-failed');
      element.appendChild(cros.factory.i18n.i18nLabelNode('Failed'));
    }
    this.focusItem++;
    if (this.focusItem < this.itemList.length) {
      this._setDisplayDivClass();
    } else {
      this.judgeTest();
    }
  }

  /**
   * Checks if test is passed by checking the number of items that have passed.
   */
  judgeTest() {
    if (document.getElementsByClassName('subtest-status-passed').length ===
        this.itemList.length) {
      window.test.pass();
    } else {
      const failedItems =
          Array.from(document.getElementsByClassName('subtest-status-failed'))
              .map((e) => e.dataset.name);
      window.test.fail(
          `Display test failed. Malfunction items: ${failedItems.join(', ')}`);
    }
  }
};
