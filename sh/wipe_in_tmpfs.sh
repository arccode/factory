#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script performs the following tasks to start a wiping process under
# factory test image without reboot to release image:
# - Stop all running upstart jobs.
# - Invoke chromeos_shutdown to umount stateful partition.
# - chroot to the wiping tmpfs.

# ======================================================================
# Constants

NEWROOT="/tmp/wipe_tmpfs"

STATE_PATH="/mnt/stateful_partition"
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

# Move the following mount points to tmpfs by mount --rbind
REBIND_MOUNT_POINTS="/dev /proc /sys /run"

SERVICES_NEEDS_RUNNING="
  boot-services
  console-tty2
  dbus
  factory-wipe
  shill
  openssh-server"

CREATE_TMPFS="${SCRIPT_DIR}/create_wiping_tmpfs.sh"
DISPLAY_MESSAGE="${SCRIPT_DIR}/display_wipe_message.sh"

WIPE_INIT_UNDER_NEWROOT="${SCRIPT_DIR#${NEWROOT}}/wipe_init.sh"

WIPE_ARGS_FILE="/tmp/factory_wipe_args"

LOG_FILE="/tmp/wipe_in_tmpfs.log"

# Mount points that need chromeos_shutdown to umount.
CHROMEOS_SHUTDOWN_UNMOUNT_POINTS="
  /usr/local
  /home
  /mnt/stateful_partition"

# ======================================================================
# Set up logging

stop_and_save_logging() {
  # Stop appending to the log and preserve it.
  exec >/dev/null 2>&1

  # If stateful partition is already unmounted, mount it before save log
  # to stateful partition.
  if ! mount | awk '{print $3}' | grep -q "^${STATE_PATH}$"; then
    mount -t ext4 "${STATE_DEV}" "${STATE_PATH}"
  fi
  mv -f "${LOG_FILE}" "${STATE_PATH}"/unencrypted/"$(basename "${LOG_FILE}")"
  sync; sleep 3
}

die() {
  echo "ERROR: $*"
  stop_and_save_logging

  "${DISPLAY_MESSAGE}" wipe_failed

  exit 1
}

# Dumps each command to "${LOG_FILE}" and exits when error.
set -xe
exec >"${LOG_FILE}" 2>&1

# This script never exits under normal conditions. Traps all unexpected errors.
trap die EXIT

# ======================================================================
# Global variables

FACTORY_ROOT_DEV=$(rootdev -s)
ROOT_DISK=$(rootdev -d -s)
STATE_DEV="${FACTORY_ROOT_DEV%[0-9]*}1"

WIPE_ARGS="factory"
CUTOFF_ARGS=""
SHOPFLOOR_URL=""

# ======================================================================
# Helper functions

find_wipe_args() {
  grep "^$1" "${WIPE_ARGS_FILE}" | cut -d '=' -f 2 - || true
}

parse_wipe_args() {
  local fast_wipe=""

  if [ -f "${WIPE_ARGS_FILE}" ]; then
    fast_wipe="$(find_wipe_args FAST_WIPE)"
    [ "${fast_wipe}" = "true" ] && WIPE_ARGS="${WIPE_ARGS} fast"
    CUTOFF_ARGS="$(find_wipe_args CUTOFF_ARGS)"
    SHOPFLOOR_URL="$(find_wipe_args SHOPFLOOR_URL)"
  fi
}


stop_running_upstart_jobs() {
  # Try a three times to stop running services because some service will
  # respawn one time after being stopped, ex: shill_respawn. Two times
  # should enough to stop shill then shill_respawn, adding one more try
  # for safety.
  local i=0 service=""
  for i in $(seq 3); do
    for service in $(initctl list | awk '/start\/running/ {print $1}'); do
      # Stop all running services except ${SERVICES_NEEDS_RUNNING}
      if ! echo "${SERVICES_NEEDS_RUNNING}" |
          egrep -q "(^| )${service}(\$| )"; then
        stop "${service}" || true
      fi
    done
  done
}

# Unmounts all mount points on stateful partition.
unmount_mount_points_on_stateful() {
  # Gets all mount points from $(mount) first, then unmount all.
  local mount_point=""
  for mount_point in $(mount "${STATE_PATH}" 2>&1 |
      grep 'mounted on' | awk '{print $6}' | tac); do
    if ! echo "${CHROMEOS_SHUTDOWN_UNMOUNT_POINTS}" |
        egrep -q "(^| )${mount_point}(\$| )"; then
      local unmounted=false
      for i in $(seq 3); do
        if umount "${mount_point}"; then
          unmounted=true
          break
        fi
        sleep .1
      done
      if ! ${unmounted}; then
        die "Unable to unmount ${mount_point}."
      fi
    fi
  done
}

# Unmount stateful partition.
unmount_stateful() {
  unmount_mount_points_on_stateful

  # Try a few times to unmount the stateful partition because sometimes
  # '/home/chronos' will be re-created again after being unmounted.
  # Umount it again can fix the problem.
  local i=0
  for i in $(seq 5); do
    if mount | awk '{print $3}' | grep -q "^${STATE_PATH}$"; then
      # Invoke chromeos_shutdown to unmount path in
      # CHROMEOS_SHUDOWN_UNMOUNT_POINTS. chromeos_shutdown is the script called
      # in restart.conf that performs all "on shutdown" tasks like
      # cleaning up mounted partitions, and can be invoked here without
      # really putting system into shutdown state.
      chromeos_shutdown
      sleep .1
    else
      break
    fi
  done

  # Make sure all mounting points related to stateful partition are
  # successfully unmounted.
  if mount | egrep -q "(${STATE_DEV}|encstateful)"; then
    die "Unable to unmount stateful parition. Aborting."
  fi
}

# Bind mount important mount points into tmpfs.
rebind_mount_point() {
  local mount_point=""
  for mount_point in ${REBIND_MOUNT_POINTS}; do
    local dst_dir="${NEWROOT}${mount_point}"
    if [ ! -d "${dst_dir}" ]; then
      mkdir -p "${dst_dir}"
    fi
    mount --rbind "${mount_point}" "${dst_dir}"
  done
  # Copy the mtab so mount command still can work after chroot.
  # mkfs.ext4 ${STATE_DEV} also need this, otherwise, machine will
  # be in self-repair mode after reboot.
  cp -fd "/etc/mtab" "${NEWROOT}/etc/mtab"
}

# chroot to the tmpfs and invoke factory wiping.
chroot_tmpfs_to_wipe() {
  # We use pivot_root here to chroot into the tmpfs
  local oldroot=""
  oldroot=$(mktemp -d --tmpdir="${NEWROOT}")
  cd "${NEWROOT}"
  pivot_root . "$(basename "${oldroot}")"
  exec chroot . "${WIPE_INIT_UNDER_NEWROOT}" "${FACTORY_ROOT_DEV}" \
    "${ROOT_DISK}" "${WIPE_ARGS}" "${CUTOFF_ARGS}" "${SHOPFLOOR_URL}"
}

# In wiping tmp filesystem, modprobe fails to load modules when new USB
# ethernet dongle connected. Load all drivers for USB ethernet dongle here so
# we can recognize and reconnect to ethernet in wiping tmp filesystem.
load_usbnet_module() {
  local module_path=""
  for module_path in /lib/modules/$(uname -r)/kernel/drivers/net/usb/*.ko; do
    modprobe "$(basename ${module_path} .ko)"
  done
}

# ======================================================================
# Main function

main() {
  if ! echo "${SCRIPT_DIR}" | grep -q "^${NEWROOT}" ; then
    # Create a new tmp filesystem and exec the script under it.
    "${CREATE_TMPFS}" "${NEWROOT}"
    exec "${NEWROOT}/${SCRIPT_DIR}/wipe_in_tmpfs.sh"
  fi

  parse_wipe_args
  load_usbnet_module
  stop_running_upstart_jobs
  unmount_stateful
  rebind_mount_point
  chroot_tmpfs_to_wipe
}

main "$@"
