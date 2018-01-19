// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for display test.
 */
window.DisplayTest = class {
  constructor() {
    this.fullscreen = false;
    this.fullscreenElement = document.getElementById('display-full-screen');
  }

  /**
   * Toggles the fullscreen display visibility.
   */
  toggleFullscreen() {
    this.fullscreen = !this.fullscreen;
    this.fullscreenElement.classList.toggle('hidden', !this.fullscreen);
    window.test.setFullScreen(this.fullscreen);
  }
};
