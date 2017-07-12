#!/bin/bash

# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Script to generate a factory install partition set and miniomaha.conf
# file from a release image and a factory image. This creates a server
# configuration that can be installed using a factory install shim.
#
# miniomaha lives in "." and miniomaha partition sets live in "./static".
#
# All internal environment variables used by this script are prefixed with
# "MFP_".  Please avoid using them for other purposes.
#
# *** IMPORTANT:
# ***
# *** This script is somewhat fragile, so if you make changes, please use
# *** py/tools/test_make_factory_package.py as a regression test.

. "$(dirname "$(readlink -f "$0")")/factory_common.sh" || exit 1
: ${CROS_PAYLOAD:="${SCRIPT_DIR}/cros_payload"}

# Detects environment in in cros source tree, chroot, or extracted bundle.
setup_cros_sdk_environment() {
  local crosutils_path="$SCRIPT_DIR/../../../scripts"
  if [ -f "$crosutils_path/.default_board" ]; then
    DEFAULT_BOARD="$(cat "$crosutils_path/.default_board")"
  fi

  # Detect whether we're inside a chroot or not
  INSIDE_CHROOT=0
  [ -e /etc/debian_chroot ] && INSIDE_CHROOT=1
}

setup_cros_sdk_environment
FLAGS_NONE='none'
# Flags
DEFINE_string board "${DEFAULT_BOARD}" "Board for which the image was built"

# Flags for key input components
DEFINE_string release_image "" \
  "Path to a ChromiumOS release (or recovery) image."
DEFINE_string test_image "" \
  "Path to a ChromiumOS test image (build_image test) chromiumos_test_image.bin"
DEFINE_string toolkit "" \
  "Path to a factory toolkit to use (install_factory_toolkit.run)."
DEFINE_string factory_shim "" \
"Path to a factory shim (build_image factory_install) factory_install_shim.bin"

# Flags for optional input components
DEFINE_string firmware "" \
  "Path to a firmware updater (shellball) chromeos-firmwareupdate,"\
" or leave empty (default) for the updater in release image (--release_image),"\
" or '$FLAGS_NONE' to prevent running firmware updater."
DEFINE_string hwid "" \
  "Path to a HWID bundle updating the HWID database config files,"\
" or '$FLAGS_NONE' to prevent updating the HWID config file."
DEFINE_string complete_script "" \
  "If set, include the script for the last-step execution of factory install"

DEFINE_string toolkit_arguments "" \
  "If set, additional arguments will be passed to factory toolkit installer. "

# Flags for output modes.
DEFINE_string usbimg "" \
  "If set, the name of the USB installation disk image file to output."
DEFINE_string diskimg "" \
  "If set, the name of the diskimage file to output."
DEFINE_boolean preserve "${FLAGS_FALSE}" \
  "If set, reuse the diskimage file, if available"
DEFINE_integer sectors 31277232  "Size of image in sectors."
DEFINE_string omaha_data_dir "" \
  "Directory to place all generated data in Omaha mode."

DEFINE_boolean run_omaha "${FLAGS_FALSE}" \
  "Run mini-omaha server after factory package setup completed."

# Deprecated flags
DEFINE_string factory_toolkit "" \
  "Deprecated by --toolkit. "
DEFINE_string factory "" \
  "Deprecated by --test_image and --toolkit."
DEFINE_string install_shim "" \
  "Deprecated by --factory_shim. "
# Usage Help
# shellcheck disable=SC2034
FLAGS_HELP="Prepares factory resources (mini-omaha server, RMA/usb/disk images)

USAGE: $0 [flags] args
Note environment variables with prefix MFP_ are for reserved for internal use.
"

# Internal variables
ENABLE_FIRMWARE_UPDATER=$FLAGS_TRUE

# Parse command line
FLAGS "$@" || exit 1
# shellcheck disable=SC2124
ORIGINAL_PARAMS="$@"
eval set -- "${FLAGS_ARGV}"

# Convert legacy options
if [ -n "${FLAGS_factory_toolkit}" ]; then
  FLAGS_toolkit="${FLAGS_factory_toolkit}"
  warn "--factory_toolkit is deprecated by --toolkit."
fi
if [ -n "${FLAGS_install_shim}" ]; then
  FLAGS_factory_shim="${FLAGS_install_shim}"
  warn "--install_shim is deprecated by --factory_shim."
fi
if [ -n "${FLAGS_factory}" ]; then
  die "--factory is deprecated by --test_image TEST_IMAGE --toolkit TOOLKIT."
fi

LOOP_DEVICE=""

# This does not work inside subshell.
set_loop_device() {
  if [ -n "${LOOP_DEVICE}" ]; then
    die "Sorry, you have to invoke free_loop_device before setting another."
  fi
  LOOP_DEVICE="$1"
}

free_loop_device() {
  if [ -n "${LOOP_DEVICE}" ]; then
    sudo umount "${LOOP_DEVICE}" 2>/dev/null || true
    sudo losetup -d "${LOOP_DEVICE}" || true
    LOOP_DEVICE=""
  fi
}

on_exit() {
  free_loop_device
  image_clean_temp
}

on_error() {
  trap - EXIT
  error "Failed to complete $0."
  on_exit
}

# Param checking and validation
check_file_param() {
  local param="$1"
  local msg="$2"
  local param_name="${param#FLAGS_}"
  local param_value="$(eval echo \$"$1")"

  [ -n "$param_value" ] ||
    die "You must assign a file for --$param_name $msg"
  [ -f "$param_value" ] ||
    die "Cannot find file: $param_value"
}

check_file_param_or_none() {
  local param="$1"
  local msg="$2"
  local param_name="${param#FLAGS_}"
  local param_value="$(eval echo \$"$1")"

  if [ "$param_value" = "$FLAGS_NONE" ]; then
    eval "$param=''"
    return
  fi
  [ -n "$param_value" ] ||
    die "You must assign either a file or 'none' for --$param_name $msg"
  [ -f "$param_value" ] ||
    die "Cannot find file: $param_value"
}

check_optional_file_param() {
  local param="$1"
  local msg="$2"
  local param_name="${param#FLAGS_}"
  local param_value="$(eval echo \$"$1")"

  if [ -n "$param_value" ] && [ ! -f "$param_value" ]; then
    die "Cannot find file: $param_value"
  fi
}

check_empty_param() {
  local param="$1"
  local msg="$2"
  local param_name="${param#FLAGS_}"
  local param_value="$(eval echo \$"$1")"

  [ -z "$param_value" ] || die "Parameter --$param_name is not supported $msg"
}

check_false_param() {
  local param="$1"
  local msg="$2"
  local param_name="${param#FLAGS_}"
  local param_value="$(eval echo \$"$1")"

  [ "$param_value" = "$FLAGS_FALSE" ] ||
    die "Parameter --$param_name is not supported $msg"
}

check_parameters() {
  # TODO(hungte) Auto-collect files from sub-folders in bundle.
  check_file_param FLAGS_release_image ""
  check_file_param FLAGS_test_image ""
  check_file_param FLAGS_toolkit ""
  check_file_param_or_none FLAGS_hwid ""

  # --diskimg need complete_script to be empty, but that is fine for
  # check_optional_file_param.
  check_optional_file_param FLAGS_complete_script ""

  # Pre-parse parameter default values
  case "${FLAGS_firmware}" in
    $FLAGS_NONE )
      ENABLE_FIRMWARE_UPDATER="$FLAGS_FALSE"
      ;;
    "" )
      # Empty value means "enable updater from rootfs" for all modes except
      # --diskimg mode.
      if [ -n "${FLAGS_diskimg}" ]; then
        ENABLE_FIRMWARE_UPDATER="$FLAGS_FALSE"
      else
        FLAGS_firmware="$FLAGS_NONE"
      fi
      ;;
  esac

  # All remaining parameters must be checked:
  # factory_shim, firmware, complete_script.
  if [ -n "${FLAGS_usbimg}" ]; then
    [ -z "${FLAGS_diskimg}" ] ||
      die "--usbimg and --diskimg cannot be used at the same time."
    check_file_param FLAGS_factory_shim "in --usbimg mode"
    check_file_param_or_none FLAGS_firmware "in --usbimg mode"
    check_false_param FLAGS_run_omaha "in --usbimg mode"
  elif [ -n "${FLAGS_diskimg}" ]; then
    check_empty_param FLAGS_factory_shim "in --diskimg mode"
    check_empty_param FLAGS_firmware "in --diskimg mode"
    check_empty_param FLAGS_complete_script "in --diskimg mode"
    check_false_param FLAGS_run_omaha "in --diskimg mode"
    if [ -b "${FLAGS_diskimg}" ] && [ ! -w "${FLAGS_diskimg}" ] &&
       [ -z "$MFP_SUDO" ] && [ "$(id -u)" != "0" ]; then
      # Restart the command with original parameters with sudo for writing to
      # block device that needs root permission.
      # MFP_SUDO is a internal flag to prevent unexpected recursion.
      # shellcheck disable=SC2086
      MFP_SUDO=TRUE exec sudo "$0" ${ORIGINAL_PARAMS}
    fi
  else
    check_empty_param FLAGS_factory_shim "in mini-omaha mode"
    check_file_param_or_none FLAGS_firmware "in mini-omaha mode"
  fi
}

find_omaha() {
  OMAHA_PROGRAM="${SCRIPT_DIR}/miniomaha.py"

  if [ -n "${FLAGS_omaha_data_dir}" ]; then
    OMAHA_DATA_DIR="$(readlink -f "${FLAGS_omaha_data_dir}")/"
  else
    OMAHA_DATA_DIR="${SCRIPT_DIR}/static/"
  fi

  OMAHA_CONF="${OMAHA_DATA_DIR}/miniomaha.conf"
  [ -f "${OMAHA_PROGRAM}" ] ||
    die "Cannot find mini-omaha server program: $OMAHA_PROGRAM"
}

setup_environment() {
  # Convert args to paths.  Need eval to un-quote the string so that shell
  # chars like ~ are processed; just doing FOO=`readlink -f ${FOO}` won't work.

  find_omaha

  # When "sudo -v" is executed inside chroot, it prompts for password; however
  # the user account inside chroot may be using a different password (ex,
  # "chronos") from the same account outside chroot.  The /etc/sudoers file
  # inside chroot has explicitly specified "userid ALL=NOPASSWD: ALL" for the
  # account, so we should do nothing inside chroot.
  if [ ${INSIDE_CHROOT} -eq 0 ]; then
    echo "Caching sudo authentication"
    sudo -v
    echo "Done"
  fi

  image_check_part_tools
}

# Builds cros_payloads into a folder.
build_payloads() {
  local dest="$1"

  [ -n "$FLAGS_board" ] || die "Need --board parameter for payloads."
  [ -n "$FLAGS_test_image" ] || die "Need --test_image parameter for payloads."
  [ -n "$FLAGS_release_image" ] || die "Need --release_image for payloads."
  [ -n "$FLAGS_toolkit" ] || die "Need --toolkit for payloads."

  local json_path="${dest}/${FLAGS_board}.json"
  echo "{}" >"${json_path}"
  local empty_file="$(mktemp)"
  image_add_temp "${empty_file}"

  if [ "${ENABLE_FIRMWARE_UPDATER}" = "${FLAGS_TRUE}" ] &&
     [ -z "${FLAGS_firmware}" ]; then
    info "Preparing firmware updater from release image..."
    local fwupdater_tmp_dir="$(mktemp -d --tmpdir)"
    image_add_temp "${fwupdater_tmp_dir}"
    "${SCRIPT_DIR}/extract_firmware_updater.sh" -i "${FLAGS_release_image}" \
      -o "${fwupdater_tmp_dir}"
    FLAGS_firmware="${fwupdater_tmp_dir}/chromeos-firmwareupdate"
  fi

  local i component resource
  local components=(test_image release_image toolkit firmware hwid complete)
  local resources=("${FLAGS_test_image}" "${FLAGS_release_image}" \
                   "${FLAGS_toolkit}" "${FLAGS_firmware}" "${FLAGS_hwid}" \
                   "${FLAGS_complete_script}")
  for i in "${!components[@]}"; do
    component="${components[$i]}"
    resource="${resources[$i]}"
    if [ -n "${resource}" ]; then
      echo "Generating ${component} payloads from ${resource}..."
      "${CROS_PAYLOAD}" add "${json_path}" "${component}" "${resource}"
    else
      echo "Adding empty ${component} payload..."
      "${CROS_PAYLOAD}" add "${json_path}" "${component}" "${empty_file}"
    fi
  done
}

generate_omaha() {
  mkdir -p "${OMAHA_DATA_DIR}"
  build_payloads "${OMAHA_DATA_DIR}"
  echo 'config = [ {} ]' >"${OMAHA_CONF}"

  local data_dir_param=""
  if [ -n "${FLAGS_omaha_data_dir}" ]; then
      data_dir_param="--data_dir ${OMAHA_DATA_DIR}"
  fi
  info "The miniomaha/cros_payload server lives in: ${OMAHA_DATA_DIR}
  To run the server:
    python ${OMAHA_PROGRAM} ${data_dir_param}"
}

generate_usbimg() {
  # TODO(hungte) Read board from release image if needed.
  [ -n "$FLAGS_board" ] || die "Need --board parameter."

  # It is possible to enlarge the disk by calculating sizes of all input files,
  # create cros_payloads folder in the disk image file, to minimize execution
  # time. However, that implies we have to shrink disk image later (due to gz),
  # and run build_payloads using root, which are not easy. As a result, here we
  # want to create payloads in temporary folder then copy into disk image.

  info "Generating cros_payloads.."
  local payloads_dir="$(mktemp -d --tmpdir)"
  image_add_temp "${payloads_dir}"
  build_payloads "${payloads_dir}"

  local payloads_size="$(du -sk "${payloads_dir}" | cut -f 1)"
  info "cros_payloads size: $((payloads_size / 1024))M."

  info "Preparing new USB image from ${FLAGS_factory_shim}..."
  cp -f "${FLAGS_factory_shim}" "${FLAGS_usbimg}"
  local old_size="$(stat --printf="%s" "${FLAGS_usbimg}")"
  local new_size="$((payloads_size * 1024 + old_size))"

  info "Size changed: $((new_size / 1048576))M => $((old_size / 1048576))M."
  truncate -s "${new_size}" "${FLAGS_usbimg}"
  "${SCRIPT_DIR}/pygpt" repair --expand "${FLAGS_usbimg}"

  local state_dev="$(image_map_partition "${FLAGS_usbimg}" 1)"
  set_loop_device "${state_dev}"
  sudo e2fsck -f "${state_dev}"
  sudo resize2fs "${state_dev}"
  free_loop_device

  local stateful_dir="$(mktemp -d --tmpdir)"
  image_add_temp "${stateful_dir}"
  image_mount_partition "${FLAGS_usbimg}" 1 "${stateful_dir}" "rw"

  local stateful_payloads="${stateful_dir}/cros_payloads"
  sudo mkdir -m 0755 -p "${stateful_payloads}"
  info "Moving payload files to disk image..."
  sudo mv -f "${payloads_dir}"/* "${stateful_payloads}"

  local lsb_path="/dev_image/etc/lsb-factory"
  echo "FACTORY_INSTALL_FROM_USB=1" | sudo tee -a "${stateful_dir}${lsb_path}"
  echo "USE_CROS_PAYLOAD=1" | sudo tee -a "${stateful_dir}${lsb_path}"
  sudo df -h "${stateful_dir}"
  image_umount_partition "${stateful_dir}"

  info "Generated USB image at ${FLAGS_usbimg}."
  info "Done"
}

generate_diskimg() {
  prepare_diskimg

  local build_tmp="$(mktemp -d --tmpdir)"
  image_add_temp "${build_tmp}"
  build_payloads "${build_tmp}"

  local json_path="${build_tmp}/${FLAGS_board}.json"
  # TODO(hungte) "losetup -P" needs Ubuntu 15 and we need an alternative for 14.
  local outdev="$(sudo losetup --find --show -P "${FLAGS_diskimg}")"

  if [ ! -b "${outdev}" ]; then
    die "Fail to create loop devices. Try to run inside chroot."
  fi
  set_loop_device "${outdev}"
  sudo "${CROS_PAYLOAD}" install "${json_path}" "${outdev}" \
    test_image release_image
  # Increase stateful partition with 1G free space if possible.
  sudo ${SCRIPT_DIR}/resize_image_fs.sh -i "${outdev}" --append -s 1024 || true
  sudo "${CROS_PAYLOAD}" install "${json_path}" "${outdev}" \
    toolkit hwid release_image.crx_cache

  echo "Updating files in stateful partition"
  # Add /etc/lsb-factory into diskimg if not exists.
  image_mount_partition "${outdev}" 1 "${build_tmp}" "rw"
  sudo touch "${build_tmp}"/dev_image/etc/lsb-factory || true
  image_umount_partition "${build_tmp}"
  free_loop_device

  echo "Generated Image at ${FLAGS_diskimg}."
  echo "Done"
}

prepare_diskimg() {
  local outdev="$(readlink -f "$FLAGS_diskimg")"
  local sectors="$FLAGS_sectors"

  # We'll need some code to put in the PMBR, for booting on legacy BIOS.
  echo "Fetch PMBR"
  local pmbrcode="$(mktemp --tmpdir)"
  image_add_temp "$pmbrcode"
  sudo dd bs=512 count=1 status=noxfer \
    if="${FLAGS_release_image}" of="${pmbrcode}"

  echo "Prepare base disk image"
  # Create an output file if requested, or if none exists.
  if [ -b "${outdev}" ] ; then
    echo "Using block device ${outdev}"
  elif [ ! -e "${outdev}" ] || \
       [ "$(stat -c %s "${outdev}")" != "$(( sectors * 512 ))" ] || \
       [ "$FLAGS_preserve" = "$FLAGS_FALSE" ]; then
    echo "Generating empty image file"
    truncate -s "0" "$outdev"
    truncate -s "$((sectors * 512))" "$outdev"
  else
    echo "Reusing $outdev"
  fi

  local root_fs_dir="$(mktemp -d --tmpdir)"
  local write_gpt_path="${root_fs_dir}/usr/sbin/write_gpt.sh"
  local chromeos_common_path="${root_fs_dir}/usr/share/misc/chromeos-common.sh"

  image_add_temp "${root_fs_dir}"
  image_mount_partition "${FLAGS_release_image}" "3" "${root_fs_dir}" "ro" "-t ext2"

  if [ ! -f "${write_gpt_path}" ]; then
    die "This script no longer works on legacy images without write_gpt.sh"
  fi
  if [ ! -f "${chromeos_common_path}" ]; then
    die "Legacy images without ${chromeos_common_path} is not supported."
  fi

  # We need to patch up write_gpt.sh a bit to cope with the fact we're
  # running in a non-chroot/device env and that we're not running as root
  local partition_script="$(mktemp --tmpdir)"
  image_add_temp "${partition_script}"

  # write_gpt_path may be only readable by user 1001 (chronos).
  # shellcheck disable=SC2024
  sudo cat "${chromeos_common_path}" "${write_gpt_path}" >"${partition_script}"
  echo "write_base_table \$1 ${pmbrcode}" >> "${partition_script}"
  # Activate partition 2
  echo "\${GPT} add -i 2 -S 1 -P 1 \$1" >> "${partition_script}"

  # Add local bin to PATH before running locate_gpt
  sed -i 's,locate_gpt,PATH="'"$PATH"'";locate_gpt,g' "${partition_script}"

  # Prepare block device and invoke script. Note: cd is required for the
  # rebasing of lib/chromeos-common.
  local ret=$FLAGS_TRUE
  local outdev_block="$(sudo losetup -f --show "${outdev}")"
  (cd "$SCRIPT_DIR"; sudo bash "${partition_script}" "${outdev_block}") ||
    ret=$?
  sudo losetup -d "${outdev_block}"
  image_umount_partition "${root_fs_dir}"
  [ "$ret" = "$FLAGS_TRUE" ] || die "Failed to setup partition (write_gpt.sh)."
}

check_cherrypy3() {
  local version="$("$1" -c 'import cherrypy as c;print c.__version__' || true)"
  local version_major="${version%%.*}"

  if [ -n "$version_major" ] && [ "$version_major" -ge 3 ]; then
    return "$FLAGS_TRUE"
  fi
  # Check how to install cherrypy3
  local install_command=""
  if image_has_command apt-get; then
    install_command="by 'sudo apt-get install python-cherrypy3'"
  elif image_has_command emerge; then
    install_command="by 'sudo emerge dev-python/cherrypy'"
  fi
  die "Please install cherrypy 3.0 or later $install_command"
}

run_omaha() {
  local python="python2"
  image_has_command "$python" || python="python"
  image_has_command "$python" || die "Please install Python in your system."
  check_cherrypy3 "$python"

  find_omaha

  info "Running mini-omaha in $SCRIPT_DIR..."
  (set -e
   info "Validating factory config..."
   "$python" "${OMAHA_PROGRAM}" --data_dir "${OMAHA_DATA_DIR}" \
             --factory_config "${OMAHA_CONF}" \
             --validate_factory_config
   info "Starting mini-omaha..."
   "$python" "${OMAHA_PROGRAM}" --data_dir "${OMAHA_DATA_DIR}" \
             --factory_config "${OMAHA_CONF}"
  )
}

main() {
  set -e
  if [ "$#" != 0 ]; then
    flags_help
    exit 1
  fi
  trap on_error EXIT

  check_parameters
  setup_environment

  if [ -n "$FLAGS_usbimg" ]; then
    generate_usbimg
  elif [ -n "$FLAGS_diskimg" ]; then
    generate_diskimg
  else
    generate_omaha
    [ "$FLAGS_run_omaha" = "$FLAGS_FALSE" ] || run_omaha
  fi

  trap on_exit EXIT
}

main "$@"
