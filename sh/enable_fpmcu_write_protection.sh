#!/usr/bin/env bash
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


set -x
set -e


check_pattern() {
  local pattern="${1}"
  local tmpfname="$(mktemp)"
  tee "${tmpfname}"
  grep -q -e "${pattern}" "${tmpfname}"
}


fpcmd() {
  ectool --name=cros_fp "${@}"
}


main() {
  # Reset the FPMCU state.
  fpcmd reboot_ec || true
  sleep 2

  # Check if SWWP is diabled but HWWP is enabled.
  fpcmd flashprotect | check_pattern \
      '^Flash protect flags:\s*0x00000008 wp_gpio_asserted$'
  rm -rf /tmp/fp.raw || true
  fpcmd fpframe raw >/tmp/fp.raw

  # Enable SWWP.
  fpcmd flashprotect enable || true
  sleep 2
  fpcmd flashprotect | check_pattern \
      '^Flash protect flags: 0x00000009 wp_gpio_asserted ro_at_boot$'
  fpcmd reboot_ec || true
  sleep 2

  # Make sure the flag is correct.
  fpcmd flashprotect | check_pattern  \
      '^Flash protect flags:\s*0x0000000b wp_gpio_asserted ro_at_boot ro_now$'

  # Make sure the RW image is active.
  fpcmd version | check_pattern '^Firmware copy:\s*RW$'

  # Verify that the system is locked.
  rm -rf /tmp/fp.raw || true
  rm -rf /tmp/error_msg.txt || true
  ! fpcmd fpframe raw >/tmp/fp.raw 2>/tmp/error_msg.txt
  cat /tmp/error_msg.txt | check_pattern 'ACCESS_DENIED'
}


main "${@}"
