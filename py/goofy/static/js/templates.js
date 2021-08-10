// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

(() => {
  /**
   * Remove all children of root in the specified slot.
   * @param {!Element} root
   * @param {?string} slotName the specified slot name, if null, would remove
   *     all children without a slot.
   */
  const clearSlotContent = (root, slotName) => {
    const elements = Array.from(root.querySelectorAll(
        slotName ? `:scope > [slot="${slotName}"]` : ':scope > :not([slot])'));
    if (!slotName) {
      // All direct child text nodes should be removed too.
      elements.push(...Array.from(root.childNodes)
                        .filter((node) => node.nodeType === Node.TEXT_NODE));
    }
    for (const element of elements) {
      element.remove();
    }
  };

  /**
   * Set the content of specified slot.
   * @param {!Element} root
   * @param {?string} slotName
   * @param {string} html
   * @param {boolean=} append
   */
  const setSlotContent = (root, slotName, html, append = false) => {
    if (!append) {
      clearSlotContent(root, slotName);
    }
    for (const element of Array.from(
             cros.factory.utils.createFragmentFromHTML(html, document)
                 .childNodes)) {
      let newElement = null;
      if (element instanceof Text) {
        if (slotName) {
          // For a top-level text node, we need a span wrapper to set the
          // "slot" attribute on it. This is not exactly equivalent to original
          // text node, since some formatting might change, but it should be
          // fine most of the time.
          // TODO(pihsun): We can fix this when display: contents is available.
          newElement = document.createElement('span');
          newElement.classList.add('inline');
          newElement.appendChild(element);
        } else {
          newElement = element;
        }
      } else if (element instanceof Element) {
        newElement = element;
      } else {
        continue;
      }
      if (slotName) {
        newElement.slot = slotName;
      }
      root.appendChild(newElement);
    }
  };

  /**
   * The document (templates.html) that contains the <template>.
   * This need to be get in the first pass when the script is run, and not in
   * the class methods.
   * @type {!Document}
   */
  const templateDoc = document.currentScript.ownerDocument;

  /**
   * A custom HTML element <test-template>.
   * The template has four sections: title, instruction (optional), state and
   * buttons.
   *
   * The instruction section also contains a progress bar, which is initially
   * hidden and can be shown with template.drawProgressBar().
   */
  class TestTemplate extends HTMLElement {
    constructor() {
      super();

      this.attachShadow({mode: 'open'});
      const template = templateDoc.getElementById('test-template');
      this.shadowRoot.appendChild(template.content.cloneNode(true));

      const markFailButton =
          this.shadowRoot.querySelector('#button-mark-failed');
      markFailButton.addEventListener('click', () => {
        window.test.userAbort();
      });
      if (window.test.invocation.getTestListEntry().disable_abort) {
        markFailButton.classList.add('disable-abort');
      }

      const screenshotButton =
          this.shadowRoot.querySelector('#button-screenshot');
      screenshotButton.addEventListener('click', () => {
        window.test.screenshot();
      });

      this.progressBar = null;
      this.progressTotal = 0;
      this.progressNow = 0;
      this.startTime = Date.now();
      this.startElapsedTimer();
    }

    /**
     * Set the title section in the template.
     * @param {string} html
     */
    setTitle(html) {
      setSlotContent(this, 'title', html);
    }

    /**
     * Set the state section in the template. If append is true, would append
     * to the state section.
     * @param {string} html
     * @param {boolean=} append
     */
    setState(html, append = false) {
      setSlotContent(this, null, html, append);
    }

    /**
     * Get the size for the state section.
     * @return {!DOMRect}
     */
    getStateSize() {
      return this.shadowRoot.querySelector('#state-container')
          .getBoundingClientRect();
    }

    /**
     * Add a button to the button section with given label.
     * @param {!cros.factory.i18n.TranslationDict} label
     * @return {!HTMLButtonElement}
     */
    addButton(label) {
      const button = document.createElement('button');
      button.slot = 'extra-button';
      button.appendChild(cros.factory.i18n.i18nLabelNode(label));
      this.appendChild(button);
      return button;
    }

    /**
     * Set the instruction section in the template.
     * @param {string} html
     */
    setInstruction(html) {
      setSlotContent(this, 'instruction', html);
    }

    /**
     * Show the progress bar and set up the progress bar object.
     * @param {number} numItems number of items
     */
    drawProgressBar(numItems) {
      if (!this.progressBar) {
        const container =
          this.shadowRoot.querySelector('#progress-bar-container');
        container.classList.add('show');

        const element = this.shadowRoot.querySelector('#progress-bar');
        const progressBar = new goog.ui.ProgressBar();
        progressBar.decorate(element);
        this.progressBar = progressBar;
      }

      this.progressTotal = numItems;
      this.progressNow = 0;
      this._updateProgressBarValue();
    }

    /**
     * Advance the progress bar.
     */
    advanceProgress() {
      this.setProgress(this.progressNow + 1);
    }

    /**
     * Set the progress to value.
     * @param {number} value number of completed items, can be floating point.
     */
    setProgress(value) {
      if (!this.progressBar) {
        throw Error(
            'Need to call drawProgressBar() before setProgress()!');
      }
      if (value > this.progressTotal) {
        value = this.progressTotal;
      }
      this.progressNow = value;
      this._updateProgressBarValue();
    }

    /**
     * Update the value of progress bar according to progressNow and
     * progressTotal.
     */
    _updateProgressBarValue() {
      const percent = this.progressNow * 100 / this.progressTotal;
      this.progressBar.setValue(percent);

      const indicator =
        this.shadowRoot.querySelector('#progress-bar-indicator');
      const roundToTwoDecimal = (x) => parseFloat(x.toFixed(2));

      indicator.innerText =
          `${percent.toFixed(1)}% (${roundToTwoDecimal(this.progressNow)}/${
              roundToTwoDecimal(this.progressTotal)})`;
    }

    /**
     * Set the value of timer.
     * Show the timer if forceShow is set.
     * Also set values of all elements with class `${name}-div`.
     * @param {number} value the remaining time.
     * @param {string=} name the name of the timer.
     * @param {boolean=} forceShow
     */
    setTimerValue(value, name = 'timer', forceShow = true) {
      if (forceShow) {
        this.showTimer(name);
      }
      this.shadowRoot.querySelector(`#${name}`).innerText = value.toFixed(0);
      for (const element of this.querySelectorAll(`.${name}-div`)) {
        element.innerText = value.toFixed(0);
      }
    }

    /**
     * Show the timer.
     * @param {string=} name the name of the timer.
     */
    showTimer(name = 'timer') {
      this.shadowRoot.querySelector(`#${name}-container`)
          .classList.add('show');
    }

    /**
     * Hide the timer.
     * @param {string=} name the name of the timer.
     */
    hideTimer(name = 'timer') {
      this.shadowRoot.querySelector(`#${name}-container`)
          .classList.remove('show');
    }

    /**
     * Set the view of the template.
     * @param {string} view the id of the view to set.
     */
    setView(view) {
      this.shadowRoot.querySelector('#state-container')
          .setAttribute('view', view);
    }

    async startElapsedTimer() {
      this.showTimer('elapsed-timer');
      while (true) {
        this.setTimerValue(((Date.now() - this.startTime) / 1000),
                           'elapsed-timer', false);
        await cros.factory.utils.delay(500);
      }
    }
  }
  window.customElements.define('test-template', TestTemplate);
  Object.defineProperty(window, 'template', {
    get: () => document.querySelector('test-template')
  });
})();
