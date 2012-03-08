#!/bin/sh
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Common library for Google Factory Tools shell scripts.

# ======================================================================
# global variables

# cgpt related configuration
CGPT_DEVICE=""
CGPT_CONFIG=""

# ======================================================================
# message and error handling

# usage: alert messages...
alert() {
  echo "$*" 1>&2
}

# usage: die messages...
die() {
  alert "ERROR: $*"
  exit 1
}

# ======================================================================
# cgpt utilities (works with CGPT_DEVICE by default)

# usage: cgpt_backup_status
cgpt_backup_status() {
  local partno
  local info
  local device="$CGPT_DEVICE"
  [ -e "$device" ] || die "Invalid device for cgpt: $device"
  info="$(cgpt show "$device" -q | awk '{print $3}')" ||
    die "Failed to show cgpt info for $device"
  for partno in $info; do
    echo "${partno}=$(cgpt show "$device" -i "$partno" -A)"
  done
}

# usage: cgpt_restore_status
cgpt_restore_status() {
  local info
  local partno
  local attr
  local device="$CGPT_DEVICE"
  local backup_config="$CGPT_CONFIG"
  local failure=0
  for info in $backup_config; do
    partno="$(echo $info | cut -d'=' -f1)"
    attr="$(echo $info | cut -d'=' -f2)"
    [ -n "$partno" -a -n "$attr" ] || failure=1
    cgpt add "$device" -i "$partno" -A "$attr" || failure=1
  done
  return $failure
}

# usage: cgpt_init cgpt_device
cgpt_init() {
  CGPT_DEVICE="$1"
  [ -n "$CGPT_DEVICE" -a -e "$CGPT_DEVICE" ] ||
    die "Invalid device: $CGPT_DEVICE"
  CGPT_CONFIG="$(cgpt_backup_status "$CGPT_DEVICE")" ||
    die "Failed to retrieve cgpt data."
  [ -n "$CGPT_CONFIG" ] || die "Invalid cgpt data on $CGPT_DEVICE."
}

# ======================================================================
# device name processing

# usage: device_add_partno full_device partition_no
device_add_partno() {
  local device="$1"
  local partno="$2"
  local slice=""

  case "$device" in
    /dev/sd[a-z] )
      echo "${device}${partno}"
      ;;
    /dev/mmcblk[0-9] )
      echo "${device}p${partno}"
      ;;
    * )
      for slice in "" "p" "s" ; do
        if [ -e "${device}${slice}${partno}" ]; then
          echo "${device}${slice}${partno}"
          return
        fi
      done
      die "Unknown device type: $device"
      ;;
  esac
}

# usage: device_remove_partno device_with_partition
device_remove_partno() {
  local device="$1"
  echo "$device" | sed -rn 's/p?[0-9]+$//p'
}

# ======================================================================
# chromeos specific utilities

chromeos_is_legacy_firmware() {
  [ "$(crossystem mainfw_type || echo "nonchrome")" = "nonchrome" ]
}

# usage: chromeos_invoke_postinst rootfs_dev
chromeos_invoke_postinst() {
  local rootdev="$1"
  local mount_point="$(mktemp -d)"
  local failure=0

  # Some compatible and experimental fs (e.g., ext4) may be buggy and still try
  # to write the file system even if we mount it with "ro" (ex, when seeing
  # journaling error in ext3, or s_kbytes_written in ext4). It is safer to
  # always mount the partition with legacy ext2. (ref: chrome-os-partner:3940)
  mount -t ext2 -o ro "$rootdev" "$mount_point" || {
    alert "Failed to mount partition $rootdev."
    rmdir "$mount_point" || true
    return 1
  }
  alert "Running postinst for $rootdev..."
  # TODO(hungte) We need to find a way to tell postinst there's no need to
  # update firmware. That options was "--noupdate_firmware" but removed after
  # postinst is replaced by cros_installer.
  IS_INSTALL=1 "$mount_point"/postinst "$rootdev" ||
    failure="$?"
  umount -f "$mount_point" ||
    alert "WARNING: Failed to unmount partition $rootdev"
  rmdir "$mount_point" || true
  if [ "$failure" != "0" ]; then
    alert "chromeos-postinst on $rootdev failed with error code $failure."
    return "$failure"
  fi
  return 0
}
