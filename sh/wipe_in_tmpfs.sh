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
# Set up logging

LOG_FILE="/tmp/wipe_in_tmpfs.log"

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

# Appends messages with newline.
split_messages() {
  local message=""
  for message in "$@"; do
    printf "${message}\n"
  done
}

display_message() {
  local text_file="$(mktemp)"
  split_messages "$@" >"${text_file}"

  # TODO(shunshingou): display_boot_message usually fails in this situation,
  # we need other method to show error message.
  display_boot_message show_file "${text_file}"
}

die() {
  echo "ERROR: $*"
  stop_and_save_logging

  display_message "Factory wipe failed in wipe_in_tmpfs." \
                  "Please contact engineer for help."

  exit 1
}

# Dumps each command to "${LOG_FILE}" and exits when error.
set -xe
exec >"${LOG_FILE}" 2>&1

# This script never exits under normal conditions. Traps all unexpected errors.
trap die EXIT

# ======================================================================
# Constants

NEWROOT="/tmp/wipe_tmpfs"

SERVICES_NEEDS_RUNNING="boot-services console-tty2 dbus factory-wipe"

CREATE_TMPFS_SCRIPT="/usr/local/factory/sh/create_wiping_tmpfs.sh"

FAST_WIPE_FILE="/tmp/factory_fast_wipe"
WIPE_ARGS="factory"
[ -f "${FAST_WIPE_FILE}" ] && WIPE_ARGS="${WIPE_ARGS} fast"

FACTORY_ROOT_DEV=$(rootdev -s)
ROOT_DISK=$(rootdev -d -s)
STATE_DEV="${FACTORY_ROOT_DEV%[0-9]*}1"
STATE_PATH="/mnt/stateful_partition"

# Move the following mount points to tmpfs by mount --rbind
REBIND_MOUNT_POINTS="/dev /proc /sys"

# ======================================================================
# Helper functions

invoke_self_under_tmp() {
  local target_script="/tmp/wipe_in_tmpfs.sh"

  if [ "$0" != "${target_script}" ]; then
    cp "$0" "${target_script}"
    exec "${target_script}"
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
      if ! echo "${SERVICES_NEEDS_RUNNING}" \
          | egrep -q "(^| )${service}($| )"; then
        stop "${service}" || true
      fi
    done
  done
}

# Unmounts all mount points under the filesystem.
unmount_mount_points_under_filesystem() {
  # Gets all mount points from $(mount) first, then unmount all of them.
  # For example, gets /etc/profile.d/cursor.sh and /etc/chrome_dev.conf for
  # /dev/sda1 if $(mount) output is as below:
  #   - /dev/sda1 on /etc/profile.d/cursor.sh type ext4 ...
  #   - /dev/sda1 on /etc/chrome_dev.conf type ext4 ...
  local fs_name="$1" mount_point=""
  for mount_point in $(mount | awk '$1 == fs {print $3}' fs="$fs_name"); do
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
  done
}

# Unmount stateful partition.
unmount_stateful() {
  # Try a few times to unmount the stateful partition because sometimes
  # '/home/chronos' will be re-created again after being unmounted.
  # Umount it again can fix the problem.
  local i=0
  for i in $(seq 5); do
    if mount | awk '{print $3}' | grep -q "^${STATE_PATH}$"; then
      # Invoke chromeos_shutdown to unmount /home, /usr/local and
      # /mnt/stateful_partition. chromeos_shutdown is the script called
      # in restart.conf that performs all "on shutdown" tasks like
      # cleaning up mounted partitions, and can be invoked here without
      # really putting system into shutdown state.
      chromeos_shutdown
      sleep .1
    else
      break
    fi
  done

  # Unmount other special mount points under stateful partition
  # that chromeos_shutdown won't unmount.
  # For exmaple, /etc/chrome_dev.conf and /etc/profile.d/cursor.sh
  # that only required by factory toolkit.
  unmount_mount_points_under_filesystem "${STATE_DEV}"

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
  exec chroot . wipe_init "${FACTORY_ROOT_DEV}" "${ROOT_DISK}" "${WIPE_ARGS}"
}

# ======================================================================
# Main function

main() {
  # Create the wiping tmpfs and it will copy some files from rootfs to tmpfs.
  # Therefore, we need to do this before unmount stateful partition.
  "${CREATE_TMPFS_SCRIPT}" "${NEWROOT}"

  invoke_self_under_tmp
  stop_running_upstart_jobs
  unmount_stateful
  rebind_mount_point
  chroot_tmpfs_to_wipe
}

main "$@"
