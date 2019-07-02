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
}
