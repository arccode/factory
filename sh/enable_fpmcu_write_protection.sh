#!/usr/bin/env bash
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


set -x
set -e

readonly _BOARD="$(cros_config /fingerprint board)"

# TODO(b/149590275): Update once they match
if [[ "${_BOARD}" == "bloonchipper" ]]; then
  readonly _FLASHPROTECT_HW_AND_SW_WRITE_PROTECT_ENABLED_BEFORE_REBOOT='^Flash protect flags: 0x0000000b wp_gpio_asserted ro_at_boot ro_now$'
  readonly _FLASHPROTECT_HW_AND_SW_WRITE_PROTECT_ENABLED='^Flash protect flags: 0x0000040f wp_gpio_asserted ro_at_boot ro_now rollback_now all_now$'
elif [[ "${_BOARD}" == "dartmonkey" ]]; then
  readonly _FLASHPROTECT_HW_AND_SW_WRITE_PROTECT_ENABLED_BEFORE_REBOOT='^Flash protect flags: 0x00000009 wp_gpio_asserted ro_at_boot$'
  readonly _FLASHPROTECT_HW_AND_SW_WRITE_PROTECT_ENABLED='^Flash protect flags:\s*0x0000000b wp_gpio_asserted ro_at_boot ro_now$'
else
  echo "Unrecognized FPMCU board: ${_BOARD}"
  exit 1
fi

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
      "${_FLASHPROTECT_HW_AND_SW_WRITE_PROTECT_ENABLED_BEFORE_REBOOT}"
  fpcmd reboot_ec || true
  sleep 2

  # Make sure the flag is correct.
  fpcmd flashprotect | check_pattern  \
      "${_FLASHPROTECT_HW_AND_SW_WRITE_PROTECT_ENABLED}"

  # Make sure the RW image is active.
  fpcmd version | check_pattern '^Firmware copy:\s*RW$'

  # Verify that the system is locked.
  rm -rf /tmp/fp.raw || true
  rm -rf /tmp/error_msg.txt || true
  ! fpcmd fpframe raw >/tmp/fp.raw 2>/tmp/error_msg.txt
  cat /tmp/error_msg.txt | check_pattern 'ACCESS_DENIED'
}


main "${@}"
