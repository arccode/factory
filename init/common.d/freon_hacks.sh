#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

is_freon() {
  # Currently 'frecon' is only available on boards with Freon enabled.
  if [ -x "/sbin/frecon" ]; then
    return 0
  else
    return 1
  fi
}

main() {
  if ! is_freon; then
    return 0
  fi

  # For freon boards: We disable powerd in factory test mode, but the screen
  # backlight is turned on by powerd. Manually set the brightness level to
  # 50% of max brightness.
  backlight_tool --set_brightness_percent=50.0
}

main "$@"
