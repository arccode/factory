// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

(() => {
  /**
   * The document (templates.html) that contains the <template>.
   * This need to be get in the first pass when the script is run, and not in
   * the class methods.
   * @type {!Document}
   */
  const templateDoc = document.currentScript.ownerDocument;

  class TestView extends HTMLElement {
    constructor() {
      super();

      this.attachShadow({mode: 'open'});
      const template = templateDoc.getElementById('test-view');
      this.shadowRoot.appendChild(template.content.cloneNode(true));
      // Prevent slotchange events under test-view to propogate to container,
      // to stop extra style refresh call on container.
      this.addEventListener('slotchange', (e) => {
        e.stopPropagation();
      });
    }
  }
  window.customElements.define('test-view', TestView);

  class TestViewsContainer extends HTMLElement {
    constructor() {
      super();

      this.attachShadow({mode: 'open'});
      const template = templateDoc.getElementById('test-views-container');
      this.shadowRoot.appendChild(template.content.cloneNode(true));
      const slot = this.shadowRoot.querySelector('slot');
      slot.addEventListener('slotchange', (e) => {
        const nodes = e.currentTarget.assignedNodes({flatten: true});
        const testViewIds = [];
        for (const node of nodes) {
          if (node instanceof TestView) {
            if (!node.id) {
              throw 'Each test-view should have an id!';
            }
            testViewIds.push(node.id);
          }
        }
        const css = testViewIds.map((id) => `
          :host(:not([view="${id}"])) ::slotted(test-view#${id}) {
            display: none;
          }
        `).join('');
        this.shadowRoot.querySelector('#extra-style').innerHTML = css;
      });
    }
  }
  window.customElements.define('test-views-container', TestViewsContainer);
})();
