// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// TODO(pihsun): Make i18n.js an independent script that can be included on
// test page, so we don't need this script.
(() => {
  const style = document.createElement('style');
  style.innerHTML = `
    :host > span {
      display: none;
    }
  ` + cros.factory.i18n.locales.map((locale) => `
    :host-context(.goofy-locale-${locale}) > span.goofy-label-${locale} {
      display: inline;
    }
  `).join('');
  window.customElements.define('i18n-label', class extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({mode: 'open'});
      this.shadowRoot.appendChild(style.cloneNode(true));
    }
    connectedCallback() {
      const callback = () => {
        const text = this.innerHTML.trim();
        for (const dom of Array.from(
                 this.shadowRoot.querySelectorAll('span'))) {
          dom.remove();
        }
        this.shadowRoot.appendChild(cros.factory.i18n.i18nLabelNode(text));
      };

      const observer = new MutationObserver(callback);
      callback();
      observer.observe(this, {childList: true});
    }
  });
})();
