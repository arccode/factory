/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
export class UiUtils {
  /** Removes all classes from DOM element with given prefix. */
  static removeClassesWithPrefix(element, prefix) {
    element.classList.remove(
      ...Array.from(element.classList).filter((cls) => cls.startsWith(prefix)));
  }
  /** Put into fullscreen mode if applicable. */
  static requestFullscreen() {
    const element = document.documentElement;
    if (element.requestFullscreen) {
      element.requestFullscreen();
    } else if (element.webkitRequestFullscreen) {
      element.webkitRequestFullscreen();
    }
  }
  /** Exit fullscreen mode if currently being presented in fullscreen.  */
  static exitFullscreen() {
    const isInFullscreen = document.fullscreenElement ||
      document.webkitFullscreenElement;
    if (isInFullscreen) {
      if (document.exitFullscreen) {
          document.exitFullscreen();
      } else if (document.webkitExitFullscreen){
          document.webkitExitFullscreen();
      }
    }
  }
}
