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
# "MFP_CONFIG_"* are shell variables that can be used in config file (--config)
#
# *** IMPORTANT:
# ***
# *** This script is somewhat fragile, so if you make changes, please use
# *** py/tools/test_make_factory_package.py as a regression test.

. "$(dirname "$(readlink -f "$0")")/factory_common.sh" || exit 1

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
DEFINE_string install_shim "" \
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
DEFINE_boolean cros_payload ${FLAGS_FALSE} \
  "Generate the output data using new cros_payload format."
DEFINE_string usbimg "" \
  "If set, the name of the USB installation disk image file to output."
DEFINE_string diskimg "" \
  "If set, the name of the diskimage file to output."
DEFINE_boolean preserve ${FLAGS_FALSE} \
  "If set, reuse the diskimage file, if available"
DEFINE_integer sectors 31277232  "Size of image in sectors."
DEFINE_string omaha_data_dir "" \
  "Directory to place all generated data in Omaha mode."

# Flags for legacy Omaha mode.
DEFINE_string subfolder "" \
  "If set, the name of the subfolder to put the payload items inside"
DEFINE_boolean detect_release_image ${FLAGS_TRUE} \
  "If set, try to auto-detect the type of release image and convert if required"
DEFINE_string config "" \
  'Configuration file where parameters are read from.  You can use '\
'\$MFP_CONFIG_PATH and \$MFP_CONFIG_DIR (path and directory to the '\
'config file itself) in config file to use relative path'
DEFINE_boolean run_omaha ${FLAGS_FALSE} \
  "Run mini-omaha server after factory package setup completed."

# Deprecated flags
DEFINE_string factory_toolkit "" \
  "Deprecated by --toolkit. "
DEFINE_string factory "" \
  "Deprecated by --test_image and --toolkit."
# Usage Help
FLAGS_HELP="Prepares factory resources (mini-omaha server, RMA/usb/disk images)

USAGE: $0 [flags] args
Note environment variables with prefix MFP_ are for reserved for internal use.
"

# Internal variables
ENABLE_FIRMWARE_UPDATER=$FLAGS_TRUE

# Parse command line
FLAGS "$@" || exit 1
ORIGINAL_PARAMS="$@"
eval set -- "${FLAGS_ARGV}"

# Convert legacy options
if [ -z "${FLAGS_toolkit}" ] && [ -n "${FLAGS_factory_toolkit}" ]; then
  FLAGS_toolkit="${FLAGS_factory_toolkit}"
  warn "--factory_toolkit is deprecated by --toolkit."
fi
if [ -n "${FLAGS_factory}" ]; then
  die "--factory is deprecated by --test_image TEST_IMAGE --toolkit TOOLKIT."
fi
if [ -n "${FLAGS_diskimg}" ] || [ -n "${FLAGS_usbimg}" ]; then
  # Currently --diskimg and --usbimg both need cros_payload.
  FLAGS_cros_payload="${FLAGS_TRUE}"
fi

on_exit() {
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
  local param_value="$(eval echo \$$1)"

  [ -n "$param_value" ] ||
    die "You must assign a file for --$param_name $msg"
  [ -f "$param_value" ] ||
    die "Cannot find file: $param_value"
}

check_file_param_or_none() {
  local param="$1"
  local msg="$2"
  local param_name="${param#FLAGS_}"
  local param_value="$(eval echo \$$1)"

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
  local param_value="$(eval echo \$$1)"

  if [ -n "$param_value" ] && [ ! -f "$param_value" ]; then
    die "Cannot find file: $param_value"
  fi
}

check_empty_param() {
  local param="$1"
  local msg="$2"
  local param_name="${param#FLAGS_}"
  local param_value="$(eval echo \$$1)"

  [ -z "$param_value" ] || die "Parameter --$param_name is not supported $msg"
}

check_false_param() {
  local param="$1"
  local msg="$2"
  local param_name="${param#FLAGS_}"
  local param_value="$(eval echo \$$1)"

  [ "$param_value" = $FLAGS_FALSE ] ||
    die "Parameter --$param_name is not supported $msg"
}

check_parameters() {
  # TODO(hungte) Auto-collect files from sub-folders in bundle.
  check_file_param FLAGS_release_image ""
  check_file_param FLAGS_test_image ""
  check_file_param FLAGS_toolkit ""
  check_file_param_or_none FLAGS_hwid ""

  # --usbimg and --diskimg need complete_script to be empty, but that is fine
  # for check_optional_file_param.
  check_optional_file_param FLAGS_complete_script ""

  # Pre-parse parameter default values
  case "${FLAGS_firmware}" in
    $FLAGS_NONE )
      ENABLE_FIRMWARE_UPDATER=$FLAGS_FALSE
      ;;
    "" )
      # Empty value means "enable updater from rootfs" for all modes except
      # --diskimg mode.
      if [ -n "${FLAGS_diskimg}" ]; then
        ENABLE_FIRMWARE_UPDATER=$FLAGS_FALSE
      else
        FLAGS_firmware=$FLAGS_NONE
      fi
      ;;
  esac

  # All remaining parameters must be checked:
  # install_shim, firmware, complete_script.
  if [ -n "${FLAGS_usbimg}" ]; then
    [ -z "${FLAGS_diskimg}" ] ||
      die "--usbimg and --diskimg cannot be used at the same time."
    check_file_param FLAGS_install_shim "in --usbimg mode"
    check_file_param_or_none FLAGS_firmware "in --usbimg mode"
    check_empty_param FLAGS_complete_script "in --usbimg mode"
    check_false_param FLAGS_run_omaha "in --usbimg mode"
  elif [ -n "${FLAGS_diskimg}" ]; then
    check_empty_param FLAGS_install_shim "in --diskimg mode"
    check_empty_param FLAGS_firmware "in --diskimg mode"
    check_empty_param FLAGS_complete_script "in --diskimg mode"
    check_false_param FLAGS_run_omaha "in --diskimg mode"
    if [ -b "${FLAGS_diskimg}" -a ! -w "${FLAGS_diskimg}" ] &&
       [ -z "$MFP_SUDO" -a "$(id -u)" != "0" ]; then
      # Restart the command with original parameters with sudo for writing to
      # block device that needs root permission.
      # MFP_SUDO is a internal flag to prevent unexpected recursion.
      MFP_SUDO=TRUE exec sudo "$0" $ORIGINAL_PARAMS
    fi
  else
    check_empty_param FLAGS_install_shim "in mini-omaha mode"
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

  # Note: The subfolder flag can only append configs.  That means you will need
  # to have unique board IDs for every time you run.  If you delete
  # miniomaha.conf you can still use this flag and it will start fresh.
  if [ -n "${FLAGS_subfolder}" ]; then
    OMAHA_DATA_DIR="${OMAHA_DATA_DIR}${FLAGS_subfolder}/"
  fi

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

  # Use this image as the source image to copy
  RELEASE_DIR="$(dirname "${FLAGS_release_image}")"
  RELEASE_IMAGE="$(basename "${FLAGS_release_image}")"

  if [ "${FLAGS_cros_payload}" = "${FLAGS_FALSE}" ]; then
    FACTORY_IMAGE="$(mktemp --tmpdir)"
    image_add_temp "${FACTORY_IMAGE}"
    local toolkit_output=$(mktemp --tmpdir)
    echo "Creating factory test image from test image and toolkit" \
        "with flags --yes $FLAGS_toolkit_arguments " \
        "(output in $toolkit_output)..."
    # Check cgpt.
    if ! image_has_command cgpt; then
      die "Missing cgpt. Please install cgpt, or run in chroot."
    fi
    cp "${FLAGS_test_image}" "${FACTORY_IMAGE}"
    sudo CGPT="$(which cgpt)" "${FLAGS_toolkit}" \
        "${FACTORY_IMAGE}" --yes ${FLAGS_toolkit_arguments} >& \
        "${toolkit_output}"
  fi

  # Override this with path to modified kernel (for non-SSD images)
  RELEASE_KERNEL=""

  # Check required tools.
  if ! image_has_part_tools; then
    die "Missing partition tools. Please install cgpt/parted, or run in chroot."
  fi
}

# Builds cros_payloads into a folder.
build_payloads() {
  local dest="$1"

  [ -n "$FLAGS_board" ] || die "Need --board parameter for payloads."
  [ -n "$FLAGS_test_image" ] || die "Need --test_image parameter for payloads."
  [ -n "$FLAGS_release_image" ] || die "Need --release_image for payloads."
  [ -n "$FLAGS_toolkit" ] || die "Need --toolkit for payloads."

  # Clean up stale config and data files.
  local json_path="${dest}/${FLAGS_board}.json"
  local cros_payload="${SCRIPT_DIR}/cros_payload"
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
  for i in ${!components[@]}; do
    component="${components[$i]}"
    resource="${resources[$i]}"
    if [ -n "${resource}" ]; then
      echo "Generating ${component} payloads from ${resource}..."
      "${cros_payload}" add "${json_path}" "${component}" "${resource}"
    else
      echo "Adding empty ${component} payload..."
      "${cros_payload}" add "${json_path}" "${component}" "${empty_file}"
    fi
  done
}

generate_omaha2() {
  # Clean up stale config and data files.
  prepare_dir "${OMAHA_DATA_DIR}"
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

  if ! type cgpt >/dev/null 2>&1; then
    die "Missing 'cgpt'. Please install cgpt, or run inside chroot."
  fi

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

  info "Preparing new USB image from ${FLAGS_install_shim}..."
  cp -f "${FLAGS_install_shim}" "${FLAGS_usbimg}"
  local old_size="$(stat --printf="%s" "${FLAGS_usbimg}")"
  local new_size="$((payloads_size * 1024 + old_size))"

  info "Size changed: $((new_size / 1048576))M => $((old_size / 1048576))M."
  truncate -s "${new_size}" "${FLAGS_usbimg}"
  "${SCRIPT_DIR}/pygpt" repair --expand "${FLAGS_usbimg}"

  local state_dev="$(image_map_partition "${FLAGS_usbimg}" 1)"
  local failure=0
  sudo e2fsck -f "${state_dev}" || failure=$?
  sudo resize2fs "${state_dev}" || failure=$?
  image_unmap_partition "${state_dev}" || true
  if [ "${failure}" != 0 ]; then
    die "Failed to resize stateful partition."
  fi

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

generate_img() {
  prepare_img

  local build_tmp="$(mktemp -d --tmpdir)"
  image_add_temp "${build_tmp}"
  build_payloads "${build_tmp}"

  local cros_payload="${SCRIPT_DIR}/cros_payload"
  local json_path="${build_tmp}/${FLAGS_board}.json"
  local failure=0
  # TODO(hungte) "losetup -P" needs Ubuntu 15 and we need an alternative for 14.
  local outdev="$(sudo losetup --find --show -P "${FLAGS_diskimg}")"

  sudo "${cros_payload}" install "${json_path}" "${outdev}" \
    test_image release_image toolkit hwid || failure=$?
  sudo losetup -d "${outdev}"

  echo "Updating files in stateful partition"
  # Add /etc/lsb-factory into diskimg if not exists.
  image_mount_partition "${outdev}" 1 "${build_tmp}" "rw"
  sudo touch "${build_tmp}"/dev_image/etc/lsb-factory
  image_umount_partition "${build_tmp}"

  if [ "${failure}" != 0 ]; then
    die "Installation to ${FLAGS_diskimg} failed."
  fi

  echo "Generated Image at ${FLAGS_diskimg}."
  echo "Done"
}

# Prepares release image source by checking image type, and creates modified
# partition blob in RELEASE_KERNEL if required.
prepare_release_image() {
  local image="$(readlink -f "$1")"
  local kernelA="$(mktemp --tmpdir)"
  local kernelB="$(mktemp --tmpdir)"
  image_add_temp "${kernelA}" "${kernelB}"

  # New Image Types (crbug.com/398236):
  # - recovery: kernel in #4
  # - usb: kernel in #4
  # - ssd: kernel in #2, no need to change (almost deprecated)
  # Old image Types:
  # - recovery: kernel in #4 and vmlinuz_hd.vblock in #1
  # - usb: kernel in #2 and vmlinuz_hd.vblock in #1
  # - ssd: kernel in #2, no need to change (almost deprecated)
  image_dump_partition "${image}" "2" >"${kernelA}" 2>/dev/null ||
    die "Cannot extract kernel A partition from image: ${image}"
  image_dump_partition "${image}" "4" >"${kernelB}" 2>/dev/null ||
    die "Cannot extract kernel B partition from image: ${image}"

  local image_typeA="$(image_cros_kernel_boot_type "${kernelA}")"
  local image_typeB="$(image_cros_kernel_boot_type "${kernelB}")"
  local need_vmlinuz_hd=""
  info "Image type is [${image_typeA}]: ${image}"

  case "${image_typeA}" in
    "ssd" )
      true
      ;;
    "usb" )
      RELEASE_KERNEL="${kernelA}"
      need_vmlinuz_hd="TRUE"
      ;;
    "recovery" )
      RELEASE_KERNEL="${kernelB}"
      need_vmlinuz_hd="TRUE"
      ;;
    * )
      die "Unexpected release image type: ${image_typeA}."
      ;;
  esac

  # When vmlinuz_hd does not exist (new images), we should replace it by kernelB
  # if image_type is 'ssd'.
  if [ -n "${need_vmlinuz_hd}" ]; then
    local temp_mount="$(mktemp -d --tmpdir)"
    local vmlinuz_hd_file="vmlinuz_hd.vblock"
    image_add_temp "${temp_mount}"
    image_mount_partition "${image}" "1" "${temp_mount}" "ro" ||
      die "No stateful partition in $image."
    if [ -s "${temp_mount}/${vmlinuz_hd_file}" ]; then
      sudo dd if="${temp_mount}/${vmlinuz_hd_file}" of="${RELEASE_KERNEL}" \
        bs=512 conv=notrunc >/dev/null 2>&1 ||
        die "Cannot update kernel with ${vmlinuz_hd_file}"
    else
      if [ "${image_typeB}" = "ssd" ]; then
        RELEASE_KERNEL="${kernelB}"
      else
        die "Failed to find ${vmlinuz_hd_file} or normal bootable kernel."
      fi
    fi
    image_umount_partition "${temp_mount}"
  fi
}

# Prepares firmware updater from specified file source or release rootfs.
prepare_firmware_updater() {
  local image="$(readlink -f "$1")"
  if [ -f "$FLAGS_firmware" ]; then
    return
  fi

  local fwupdater="$(mktemp --tmpdir)"
  local temp_mount="$(mktemp -d --tmpdir)"
  local updater_path="/usr/sbin/chromeos-firmwareupdate"
  local src_file="$temp_mount$updater_path"
  image_add_temp "$fwupdater"
  image_add_temp "$temp_mount"

  # 'ext2' is required to prevent accidentally modifying image
  image_mount_partition "$image" "3" "$temp_mount" "ro" "-t ext2" ||
    die "Cannot mount partition #3 (rootfs) in release image: $image"
  [ -f "$src_file" ] ||
    die "No firmware updater in release image: $image"
  cp "$src_file" "$fwupdater" ||
    die "Failed to copy firmware updater from release image $image."
  image_umount_partition "$temp_mount"
  info "Prepared firmware updater from release image: $image:3#$updater_path"
  FLAGS_firmware="$fwupdater"
}

prepare_img() {
  local outdev="$(readlink -f "$FLAGS_diskimg")"
  local sectors="$FLAGS_sectors"

  # We'll need some code to put in the PMBR, for booting on legacy BIOS.
  echo "Fetch PMBR"
  local pmbrcode="$(mktemp --tmpdir)"
  image_add_temp "$pmbrcode"
  sudo dd bs=512 count=1 if="${FLAGS_release_image}" of="${pmbrcode}" status=noxfer

  echo "Prepare base disk image"
  # Create an output file if requested, or if none exists.
  if [ -b "${outdev}" ] ; then
    echo "Using block device ${outdev}"
  elif [ ! -e "${outdev}" -o \
        "$(stat -c %s ${outdev})" != "$(( ${sectors} * 512 ))"  -o \
        "$FLAGS_preserve" = "$FLAGS_FALSE" ]; then
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
  sudo cat "${chromeos_common_path}" "${write_gpt_path}" > "${partition_script}"
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
  [ "$ret" = $FLAGS_TRUE ] || die "Failed to setup partition (write_gpt.sh)."
}

prepare_dir() {
  local dir="$1"

  # TODO(hungte) the three files were created as root by old mk_memento_images;
  #  we can prevent the sudo in future.
  sudo rm -f "${dir}/rootfs-test.gz"
  sudo rm -f "${dir}/rootfs-release.gz"
  sudo rm -f "${dir}/update.gz"
  for filename in efi oem state hwid firmware; do
    rm -f "${dir}/${filename}.gz"
  done
  if [ ! -d "${dir}" ]; then
    mkdir -p "${dir}"
  fi
}

# Copies "unencrypted" files (such as the CRX cache) from release
# stateful partition into the target stateful partition.
#
# Currently this copies all of unencrypted (in order to get the
# "unencrypted" directory's ownership right).  TODO(jsalz): Figure out
# how to determine the right list of files to copy.
tar_unencrypted() {
  local indev="$1"
  local outdev="$2"
  local result="0"

  local release_stateful_dir="$(mktemp -d --tmpdir)"
  image_add_temp "${release_stateful_dir}"
  image_mount_partition "${FLAGS_release_image}" "1" "${release_stateful_dir}" "ro"
  if [ -d "${release_stateful_dir}/unencrypted" ]; then
    echo "Creating stateful_files.tar.xz in stateful partition..."
    local factory_stateful_dir="$(mktemp -d --tmpdir)"
    image_add_temp "${factory_stateful_dir}"
    image_mount_partition "${outdev}" 1 "${factory_stateful_dir}" "rw"
    local dest_file="${factory_stateful_dir}/stateful_files.tar.xz"
    # Check that all the files in the unencrypted directory are owned by root.
    sudo find "${release_stateful_dir}"/unencrypted -printf '%U:%G %p\n' |
        grep -v -E '^0:0 ' >&2 &&
        die "tar of release stateful partition's unencrypted contains the " \
            "above files which are not owned by 0:0 (root:root). Aborting."

    sudo tar acf "${dest_file}" --numeric-owner -C "${release_stateful_dir}" \
        unencrypted || result="$?"
    # ls destination file to show its size
    ls -hl "${dest_file}"
    image_umount_partition "${factory_stateful_dir}"
  else
    echo "Release image has no files in stateful partition."
  fi
  image_umount_partition "${release_stateful_dir}"
  [ $result = "0" ] ||
    die "tar of release stateful partition's unencrypted dir failed " \
        "($result). aborting."
}

generate_omaha() {
  local kernel rootfs stateful_efi_source
  [ -n "$FLAGS_board" ] || die "Need --board parameter for mini-omaha server."
  # Clean up stale config and data files.
  prepare_dir "${OMAHA_DATA_DIR}"

  echo "Generating omaha release image from ${FLAGS_release_image}"
  if [ -n "${FACTORY_IMAGE}" ]; then
    echo "Generating omaha factory image from ${FACTORY_IMAGE}"
  fi
  echo "Output omaha image to ${OMAHA_DATA_DIR}"
  echo "Output omaha config to ${OMAHA_CONF}"

  local final_factory_image
  if [ -n "${FACTORY_IMAGE}" ]; then
    # Make a copy of the image
    final_factory_image="$(mktemp --tmpdir)"
    image_add_temp "${final_factory_image}"
    echo "Creating temporary test image..."
    cp "${FACTORY_IMAGE}" "${final_factory_image}"
    # Add the unencrypted bits from the release stateful partition
    tar_unencrypted "${FLAGS_release_image}" "${final_factory_image}"
  fi

  kernel="${RELEASE_KERNEL:-${FLAGS_release_image}:2}"
  rootfs="${FLAGS_release_image}:3"
  stateful_efi_source="${FLAGS_release_image}"
  release_hash="$(compress_and_hash_memento_image "$kernel" "$rootfs" \
                  "${OMAHA_DATA_DIR}/rootfs-release.gz")"
  echo "release: ${release_hash}"

  oem_hash="$(compress_and_hash_partition "${FLAGS_release_image}" 8 \
              "${OMAHA_DATA_DIR}/oem.gz")"
  echo "oem: ${oem_hash}"

  if [ -n "${final_factory_image}" ]; then
    kernel="${final_factory_image}:2"
    rootfs="${final_factory_image}:3"
    stateful_efi_source="${final_factory_image}"
    test_hash="$(compress_and_hash_memento_image "$kernel" "$rootfs" \
                 "${OMAHA_DATA_DIR}/rootfs-test.gz")"
    echo "test: ${test_hash}"
  fi

  state_hash="$(compress_and_hash_partition "${stateful_efi_source}" 1 \
                "${OMAHA_DATA_DIR}/state.gz")"
  echo "state: ${state_hash}"

  efi_hash="$(compress_and_hash_partition "${stateful_efi_source}" 12 \
              "${OMAHA_DATA_DIR}/efi.gz")"

  echo "efi: ${efi_hash}"

  if [ -n "${FLAGS_firmware}" ]; then
    firmware_hash="$(compress_and_hash_file "${FLAGS_firmware}" \
                     "${OMAHA_DATA_DIR}/firmware.gz")"
    echo "firmware: ${firmware_hash}"
  fi

  if [ -n "${FLAGS_hwid}" ]; then
    hwid_hash="$(compress_and_hash_file "${FLAGS_hwid}" \
                 "${OMAHA_DATA_DIR}/hwid.gz")"
    echo "hwid: ${hwid_hash}"
  fi

  if [ -n "${FLAGS_complete_script}" ]; then
    complete_hash="$(compress_and_hash_file "${FLAGS_complete_script}" \
                     "${OMAHA_DATA_DIR}/complete.gz")"
    echo "complete: ${complete_hash}"
  fi

  # If the file does exist and we are using the subfolder flag we are going to
  # append another config.
  if [ -n "${FLAGS_subfolder}" ] &&
     [ -f "${OMAHA_CONF}" ]; then
    # Remove the ']' from the last line of the file
    # so we can add another config.
    while  [ -s "${OMAHA_CONF}" ]; do
      # If the last line is null
      if [ -z "$(tail -1 "${OMAHA_CONF}")" ]; then
        sed -i '$d' "${OMAHA_CONF}"
      elif [ "$(tail -1 "${OMAHA_CONF}")" != ']' ]; then
        sed -i '$d' "${OMAHA_CONF}"
      else
        break
      fi
    done

    # Remove the last ]
    if [ "$(tail -1 "${OMAHA_CONF}")" = ']' ]; then
      sed -i '$d' "${OMAHA_CONF}"
    fi

    # If the file is empty, create it from scratch
    if [ ! -s "${OMAHA_CONF}" ]; then
      echo "config = [" >"${OMAHA_CONF}"
    fi
  else
    echo "config = [" >"${OMAHA_CONF}"
  fi

  if [ -n "${FLAGS_subfolder}" ]; then
    subfolder="${FLAGS_subfolder}/"
  fi

  echo -n "{
   'qual_ids': set([\"${FLAGS_board}\"]),
   'release_image': '${subfolder}rootfs-release.gz',
   'release_checksum': '${release_hash}',
   'oempartitionimg_image': '${subfolder}oem.gz',
   'oempartitionimg_checksum': '${oem_hash}',
   'efipartitionimg_image': '${subfolder}efi.gz',
   'efipartitionimg_checksum': '${efi_hash}',
   'stateimg_image': '${subfolder}state.gz',
   'stateimg_checksum': '${state_hash}'," >>"${OMAHA_CONF}"

  if [ -n "${FACTORY_IMAGE}" ]  ; then
    echo -n "
   'factory_image': '${subfolder}rootfs-test.gz',
   'factory_checksum': '${test_hash}'," >>"${OMAHA_CONF}"
  fi

  if [ -n "${FLAGS_firmware}" ]  ; then
    echo -n "
   'firmware_image': '${subfolder}firmware.gz',
   'firmware_checksum': '${firmware_hash}'," >>"${OMAHA_CONF}"
  fi

  if [ -n "${FLAGS_hwid}" ]  ; then
    echo -n "
   'hwid_image': '${subfolder}hwid.gz',
   'hwid_checksum': '${hwid_hash}'," >>"${OMAHA_CONF}"
  fi

  if [ -n "${FLAGS_complete_script}" ]  ; then
    echo -n "
   'complete_image': '${subfolder}complete.gz',
   'complete_checksum': '${complete_hash}'," >>"${OMAHA_CONF}"
  fi

  echo -n "
 },
]
" >>"${OMAHA_CONF}"

  local data_dir_param=""
  if [ -n "${FLAGS_omaha_data_dir}" ]; then
      data_dir_param="--data_dir ${OMAHA_DATA_DIR}"
  fi
  info "The miniomaha server lives in: $OMAHA_DATA_DIR
  To validate the configutarion, run:
    python2.6 $OMAHA_PROGRAM $data_dir_param --validate_factory_config
  To run the server:
    python2.6 $OMAHA_PROGRAM $data_dir_param"
}

check_cherrypy3() {
  local version="$("$1" -c 'import cherrypy as c;print c.__version__' || true)"
  local version_major="${version%%.*}"

  if [ -n "$version_major" ] && [ "$version_major" -ge 3 ]; then
    return $FLAGS_TRUE
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
  local python="python2.6"
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

parse_and_run_config() {
  # This function parses parameters from config file. Parameters can be put
  # in sections and sections of parameters will be run in turn.
  #
  # Config file format:
  # [section1]
  #  --param value
  #  --another_param  # comment
  #
  # # some more comment
  # [section2]
  #  --yet_another_param
  #
  # Note that a section header must start at the beginning of a line.
  # And it's not allowed to read from config file recursively.

  local config_file="$1"
  local -a cmds
  local cmd=""
  local line

  echo "Read parameters from: $config_file"
  while read line; do
    if [[ "$line" =~ ^\[.*] ]]; then
      if [ -n "$cmd" ]; then
        cmds+=("$cmd")
        cmd=""
      fi
      continue
    fi
    line="${line%%#*}"
    cmd="$cmd $line"
  done < "$config_file"
  if [ -n "$cmd" ]; then
    cmds+=("$cmd")
  fi

  for cmd in "${cmds[@]}"
  do
    info "Executing: $0 $cmd"
    # Sets internal environment variable MFP_SUBPROCESS to prevent unexpected
    # recursion.
    eval "MFP_SUBPROCESS=1 $0 $cmd"
  done
}

# Checks if normal parameters are all empty.
check_empty_normal_params() {
  local param
  local mode="$1"
  local param_list="release factory firmware_updater hwid_updater install_shim
                    complete_script usb_img disk_img subfolder"
  for param in $param_list; do
    check_empty_param FLAGS_$param "$mode"
  done
}

main() {
  set -e
  if [ "$#" != 0 ]; then
    flags_help
    exit 1
  fi
  trap on_error EXIT

  if [ -n "$FLAGS_config" ]; then
    [ -z "$MFP_SUBPROCESS" ] ||
      die "Recursively reading from config file is not allowed"

    check_file_param FLAGS_config ""
    check_empty_normal_params "when using config file"

    # Make the path and folder of config file available when parsing config.
    # These MFP_CONFIG_* are special shell variables (not environment variables)
    # that a config file (by --config) can use them.
    MFP_CONFIG_PATH="$(readlink -f "$FLAGS_config")"
    MFP_CONFIG_DIR="$(dirname "$MFP_CONFIG_PATH")"

    parse_and_run_config "$FLAGS_config"
    [ "$FLAGS_run_omaha" = $FLAGS_FALSE ] || run_omaha
    trap on_exit EXIT
    exit
  fi

  check_parameters
  setup_environment

  if [ "${FLAGS_cros_payload}" = "${FLAGS_TRUE}" ]; then

    if [ -n "$FLAGS_usbimg" ]; then
      generate_usbimg
    elif [ -n "$FLAGS_diskimg" ]; then
      generate_img
    else
      generate_omaha2
      [ "$FLAGS_run_omaha" = $FLAGS_FALSE ] || run_omaha
    fi

  else

    # Image preparation is only needed in non-cros_payload system.
    if [ "$FLAGS_detect_release_image" = $FLAGS_TRUE ]; then
      prepare_release_image "$FLAGS_release_image"
    fi
    if [ "$ENABLE_FIRMWARE_UPDATER" = $FLAGS_TRUE ]; then
      prepare_firmware_updater "$FLAGS_release_image"
    fi

    generate_omaha
    [ "$FLAGS_run_omaha" = $FLAGS_FALSE ] || run_omaha
  fi
  trap on_exit EXIT
}

main "$@"
