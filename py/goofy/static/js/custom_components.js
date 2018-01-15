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
    :host-context(.goofy-locale-${locale}) > span.${locale} {
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
        const text = this.innerHTML.replace(/\s+/, ' ').trim();
        for (const dom of this.shadowRoot.querySelectorAll('span')) {
          dom.remove();
        }
        // We can't use cros.factory.i18n.i18nLabelNode here, since the
        // JavaScript i18n API doesn't allow HTML tags in i18n label, but we
        // allow HTML tags here.
        const translation = cros.factory.i18n.translation(text);
        for (const locale of cros.factory.i18n.locales) {
          const span = document.createElement('span');
          span.classList.add(locale);
          span.innerHTML = translation[locale];
          this.shadowRoot.appendChild(span);
        }
      };

      const observer = new MutationObserver(callback);
      callback();
      observer.observe(this, {childList: true});
    }
  });
})();
