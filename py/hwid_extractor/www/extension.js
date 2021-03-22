// Copyright 2021 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const hwidExtractorOrigin = 'http://localhost:8000';

/**
 * callback for MutationObserver
 */
const callback = async () => {
  const jsAuthCodeDiv = document.getElementsByClassName('js-auth-code')[0];
  if (!jsAuthCodeDiv) return;
  const child = jsAuthCodeDiv.children[0];
  if (!child) return;
  const codeText = child.innerText;
  const label = 'Unlock Code: ';
  if (codeText.indexOf(label) != 0) return;
  const code = codeText.slice(label.length);

  window.opener.postMessage(code, hwidExtractorOrigin);
  window.close();
};

const observer = new MutationObserver(callback);

window.addEventListener('load', () => {
  if (!window.opener) return;
  const node = document.getElementById('content-area');
  observer.observe(node, {subtree: true, childList: true});
});
