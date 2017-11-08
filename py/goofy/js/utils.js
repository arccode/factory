// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.utils');

/**
 * Returns a promise that resolves after a period of time.
 * @param {number} ms the millisecond of the delay.
 * @return {Promise}
 */
cros.factory.utils.delay = (ms) => new Promise((resolve) => {
  setTimeout(resolve, ms);
});

/**
 * Removes all classes from DOM element with given prefix.
 * @param {!Element} element
 * @param {string} prefix
 */
cros.factory.utils.removeClassesWithPrefix = (element, prefix) => {
  element.classList.remove(
      ...Array.from(element.classList).filter((cls) => cls.startsWith(prefix)));
};

/**
 * Create a DocumentFragment from an HTML.
 * @param {string} html
 * @param {!Document} doc
 * @return {!DocumentFragment}
 */
cros.factory.utils.createFragmentFromHTML = (html, doc) => {
  // TODO(pihsun): Passing doc in is a temporary hack to make this work as
  // expected in child iframe. Should be solved after utils.js is turned into a
  // real ES6 module.
  const template = doc.createElement('template');
  template.innerHTML = html;
  return template.content;
};

