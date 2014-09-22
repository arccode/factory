#!/bin/sh
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This file will be executed when user logins into VT2 or ssh.

is_highres() {
  local modes_file="/sys/class/graphics/fb0/modes"
  [ -s "${modes_file}" ] || return 2

  # Sample output: U:1366x768p-0
  local mode_line="$(head -n 1 "${modes_file}")"
  local dots="$(echo "${mode_line}" | sed 's/^U://; s/p-.*$//')"
  local dots_x="${dots%x*}"
  local dots_y="${dots#*x}"

  # Try to get physical size by xrandr (via EDID).
  local display="$(XAUTHORITY=/home/chronos/.Xauthority \
                   xrandr -d :0 2>/dev/null |
                   grep " connected " | head -n 1)"
  # Sample output: eDP connected 2560x1700+0+0 (normal left inverted right x
  # axis y axis) 272mm x 181mm
  local points="$(echo "${display}" | sed 's/.*connected //; s/+.*$//')"
  local lengths="$(echo "${display}" |
                   sed 's/.* \([0-9]*\)mm x \([0-9]*\)mm/\1 \2/')"
  # DPI is calculated by dots / length. However, the data (points) from xrandr
  # may be altered by Chrome, so we have to use points only if dots (from fb0)
  # are not available.
  [ -n "${dots_x}" ] || dots_x="${points%x*}"
  [ -n "${dots_y}" ] || dots_y="${points#*x}"
  local length_x="${lengths% *}"
  local length_y="${lengths#* }"

  if [ -n "${length_x}" -a -n "${length_y}" ]; then
    # 1 mm = 1/25.4 inch.
    local dpi_x=$((dots_x * 254 / (length_x * 10) ))
    local dpi_y=$((dots_y * 254 / (length_y * 10) ))

    # Assume 150dpi needs large fonts.
    [ "${dpi_x}" -ge 150 -a "${dpi_y}" -gt 150 ]
  else
    # No physical length information.
    # Assume 1600x1200 already needs large fonts.
    [ "${dots_x}" -ge 1600 -a "${dots_y}" -ge 1200 ]
  fi
}

set_vt_fonts() {
  if is_highres; then
    (cd /usr/local/share/consolefonts; setfont sun12x22)
  fi
}

main() {
  # Factory always needs cursor.
  setterm -cursor on

  # On high-DPI systems, we need large console fonts.
  set_vt_fonts || true

  # Put '/usr/local/factory/bin' at the head of PATH so that we can run factory
  # binaries easily.
  export PATH="/usr/local/factory/bin:${PATH}"
}

main "$@"
