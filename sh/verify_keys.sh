#!/bin/sh
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Derived from dev_debug_vboot.
#
# This script checks if system firmware and SSD images are ready for verified
# booting.
#

. "$(dirname "$0")/common.sh" || exit 1

if [ "$#" != "2" ]; then
  alert "ERROR: Usage: $0 kernel_device main_firmware"
  exit 1
fi

DEVKEYS="/usr/share/vboot/devkeys"
TMPDIR="$(mktemp -d)"
KERN_DEV="$(readlink -f "$1")"
FIRMWARE_IMAGE="$(readlink -f "$2")"
RETURN=0

invoke() {
  # Usage: invoke "message" "shell-command"
  result=0
  message="$1"
  shift
  eval "$@" >_stdout 2>_stderr || result=$?
  if [ "$result" != 0 ]; then
    alert "ERROR: Failed to $message"
    alert "Command detail: $@"
    cat _stdout _stderr 1>&2
    RETURN=1
  fi
}

detect_section_name() {
  # Usage: detect_section_name official_name alias_name
  if [ -f "$2" ]; then
    echo "$2"
  else
    echo "$1"
  fi
}

verify_keys() {
  # Usage: verify_keys kernel_device main_firmware

  # Define section names
  GBB="$(detect_section_name GBB GBB_Area)"
  FW_MAIN_A="$(detect_section_name FW_MAIN_A Firmware_A_Data)"
  FW_MAIN_B="$(detect_section_name FW_MAIN_B Firmware_B_Data)"
  VBLOCK_A="$(detect_section_name VBLOCK_A Firmware_A_Key)"
  VBLOCK_B="$(detect_section_name VBLOCK_B Firmware_B_Key)"

  invoke "dump kernel" dd if="$1" bs=1M count=64 of=hd_kern.blob
  invoke "extract firmware" dump_fmap -x "$2"
  invoke "get keys from firmware" \
    gbb_utility -g --rootkey rootkey.vbpubk \
                   --recoverykey recoverykey.vbpubk "$GBB"
  invoke "unpack rootkey" \
    vbutil_key --unpack rootkey.vbpubk
  invoke "unpack recovery key" \
    vbutil_key --unpack recoverykey.vbpubk

  # check if rootkey is developer key. 130 is the magic number for DEV key
  local key
  local rootkey_hash="$(od "rootkey.vbpubk" |
                        head -130 |
                        md5sum |
                        sed 's/ .*$//' 2>/dev/null || true)"
  if [ "$rootkey_hash" = "a13642246ef93daaf75bd791446fec9b" ]; then
    alert "ERROR: YOU ARE TRYING TO FINALIZE WITH DEV ROOTKEY."
  fi

  # Verify firmware A/B with root key
  invoke "verify VBLOCK_A with FW_MAIN_A" \
    vbutil_firmware --verify "$VBLOCK_A" --signpubkey rootkey.vbpubk \
    --fv "$FW_MAIN_A" --kernelkey kernel_subkey_a.vbpubk
  invoke "verify VBLOCK_B with FW_MAIN_B" \
    vbutil_firmware --verify "$VBLOCK_B" --signpubkey rootkey.vbpubk \
    --fv "$FW_MAIN_B" --kernelkey kernel_subkey_b.vbpubk

  # Unpack keys and keyblocks
  for key in kernel_subkey_a.vbpubk kernel_subkey_b.vbpubk; do
    invoke "unpack $key" vbutil_key --unpack $key
  done
  for keyblock in *kern*.blob; do
    invoke "unpack $keyblock" vbutil_keyblock --unpack $keyblock
  done

  # Test each kernel by each key
  for key in kernel_subkey_a.vbpubk kernel_subkey_b.vbpubk
  do
    for kern in *kern*.blob; do
      invoke "verify $kern by $key" \
        vbutil_kernel --verify $kern --signpubkey $key
    done
  done

  if [ "$RETURN" != "0" ]; then
    # Error encountered. Let's try if we can provide more information.
    key="recoverykey.vbpubk"
    vbutil_kernel --verify "$kern" --signpubkey "$key" >/dev/null 2>&1 &&
      alert "ERROR: YOU ARE USING A RECOVERY KEY SIGNED IMAGE." ||
      true
    for key in recovery_key.vbpubk kernel_subkey.vbpubk; do
      if [ -f "$DEVKEYS/$key" ]; then
        vbutil_kernel --verify "$kern" \
                      --signpubkey "$DEVKEYS/$key" >/dev/null 2>&1 &&
          alert "ERROR: YOU ARE FINALIZING WITH DEV-SIGNED IMAGE ($key)." ||
          true
      fi
    done
    alert "ERROR: Verification failed."
  else
    alert "SUCCESS: Verification complete."
  fi

  return $RETURN
}

# verify_keys is run inside a sub-shell, so we need to check its return value
# instead of reading the global variable RETURN.
( cd "$TMPDIR"
  alert "Checking firmware and kernel partition keys for $KERN_DEV..."
  verify_keys "$KERN_DEV" "$FIRMWARE_IMAGE" ) || RETURN=1
/bin/rm -rf "$TMPDIR"
exit $RETURN

