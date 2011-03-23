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

if [ "$#" != "2" ]; then
  echo "ERROR: Usage: $0 kernel_device main_firmware" 1>&2
  exit 1
fi

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
    echo "ERROR: Failed to $message" 1>&2
    echo "Command detail: $@" 1>&2
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
    gbb_utility -g --rootkey rootkey.vbpubk "$GBB"
  invoke "unpack rootkey" \
    vbutil_key --unpack rootkey.vbpubk

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
  return $RETURN
}

# verify_keys is run inside a sub-shell, so we need to check its return value
# instead of reading the global variable RETURN.
( cd "$TMPDIR"
  verify_keys "$KERN_DEV" "$FIRMWARE_IMAGE" ) || RETURN=1
/bin/rm -rf "$TMPDIR"
exit $RETURN

