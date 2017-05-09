#!/bin/sh
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# 'cros_payload' is a tool to manipulate resources for imaging ChromeOS device.
# Run 'cros_payload' to get help information.

# This tool must be self-contained with minimal dependency. And at least the
# 'installation' part must be implemented in shell script instead of Python
# because the ChromeOS factory install shim and netboot installer will need to
# run installation without python.

# External dependencies:
#  jq curl md5sum partx|cgpt pigz|gzip
#  dd tee od chmod dirname readlink mktemp stat
#  cp mv ln rm

# TODO(hungte) List of todo:
# - Quick check dependency before starting to run.
# - Add partitions in parallel if pigz cannot be found.
# - Consider using xz/pixz instead of gz.
# - Support adding or removing single partition directly.
# - Add part0 as GPT itself.

# Environment settings for utilities to invoke.
: "${GZIP:="gzip"}"
: "${JQ:=""}"

# Debug settings
: "${DEBUG:=}"

# Constants
COMPONENTS_ALL="test_image release_image toolkit hwid firmware complete"

# A variable for the file name of tracking temp files.
TMP_OBJECTS=""

# Cleans up any temporary files we have created.
# Usage: cleanup
cleanup() {
  trap - EXIT
  local object
  if [ -n "${TMP_OBJECTS}" ]; then
    while read object; do
      if [ -d "${object}" ]; then
        umount -d "${object}" 2>/dev/null || true
      fi
      rm -rf "${object}"
    done <"${TMP_OBJECTS}"
    rm -f "${TMP_OBJECTS}"
  fi
}

# Prints error message and try to abort.
# Usage: die [messages]
die() {
  trap - EXIT
  echo "ERROR: $*" >&2
  cleanup
  exit 1
}

# Prints information to users.
# Usage: info [message]
info() {
  echo "INFO: $*" >&2
}

# Prints debug messages if ${DEBUG} was set to non-empty values.
# Usage: debug [message]
debug() {
  [ -z "${DEBUG}" ] || echo "DEBUG: $*" >&2
}

# Registers a temp object to be deleted on cleanup.
# Usage: register_tmp_object TEMP_FILE
register_tmp_object() {
  # Use file-based temp object tracker so execution in sub-shell (command |
  # while read var) will also work.
  echo "$*" >>"${TMP_OBJECTS}"
}

# Checks if given file is already compressed by gzip.
# Usage: is_gzipped FILE
is_gzipped() {
  local input="$1"

  # The 'file' command needs special database, so we want to directly read the
  # magic value.
  local magic="$(od -An -N2 -x "${input}")"
  local gzip_magic=" 8b1f"

  [ "${magic}" = "${gzip_magic}" ]
}

# Checks if a tool program is already available on path.
# Usage: has_tool PROGRAM
has_tool() {
  type "$1" >/dev/null 2>&1
}

# Downloads from given URL. If output is not given, use STDOUT.
# Usage: fetch URL [output]
fetch() {
  local url="$1"
  local output="$2"
  if [ -n "${output}" ]; then
    curl -L --fail "${url}" -o "${output}"
  else
    curl -L --fail "${url}"
  fi
}

# Prints a path for specific partition on given device.
# For example, "get_partition_dev /dev/mmcblk0 1" prints /dev/mmcblk0p1.
# Usage: get_partition_dev DEV PART_NO
get_partition_dev() {
  local base="$1"
  shift

  # TODO(hungte) decide if we should also test -b ${base}.
  case "${base}" in
    *[0-9])
      # Adjust from /dev/mmcblk0 to /dev/mmcblk0p
      echo "${base}p$*"
      ;;
    "")
      die "Need valid partition device"
      ;;
    *)
      echo "${base}$*"
  esac
}

# Command "help", provides usage help.
# Usage: cmd_help
cmd_help() {
  echo "Usage: $0 command [args...]

  '$(basename "$0")' is an utility for manipulating payload-type resources.
  All the payloads will be stored as gzipped file with MD5SUM in
  file name. A JSON file manages the mapping to individual files.

  Commands:
      add      JSON_PATH COMPONENT FILE
      install  JSON_URL  DEST      COMPONENTS...
      download JSON_URL  DEST      COMPONENTS...
      list     JSON_URL

  COMPONENT: ${COMPONENTS_ALL}
  JSON_PATH: A path to local JSON config file.
  JSON_URL:  A URL to remote or local JSON config file.
  FILE:      A path to local file resource.
  DEST:      Destination (usually a folder or a block device like /dev/sda).
  "
}

# JSON helper functions - using jq or python.

# Merges two json arguments into out.
json_merge() {
  local base_path="$1"
  local update_path="$2"

  if [ -n "${JQ}" ]; then
    jq -s '.[0] * .[1]' "${base_path}" "${update_path}"
    return
  fi

  python -c "\
import json
import sys

def get_fd(path):
  return sys.stdin if path == '-' else open(path)

def merge(base, delta):
  for key, value in delta.iteritems():
    if isinstance(value, dict):
      new_value = base.setdefault(key, {})
      merge(new_value, value)
    else:
      base[key] = value
  return base

base = json.load(get_fd(sys.argv[1]))
delta = json.load(get_fd(sys.argv[2]))
merge(base, delta)
print(json.dumps(base))
" "${base_path}" "${update_path}"
}

# Gets the value of specified query command.
json_get_file_value() {
  local query="$1"
  local json_file="$2"
  if [ -n "${JQ}" ]; then
    "${JQ}" -r \
      "if ${query}|type == \"object\" then ${query}.file else ${query} end" \
      "${json_file}"
    return
  fi

  python -c "\
import json
import sys

j = json.load(open(sys.argv[2]))
for k in sys.argv[1].split('.')[1:]:
  j = j.get(k) if j else None
if isinstance(j, dict):
  j = j['file']
print('null' if j is None else j)" "${query}" "${json_file}"
}

# Gets the keys of given JSON object from stdin.
json_get_keys() {
  if [ -n "${JQ}" ]; then
    "${JQ}" -r 'keys[]'
    return
  fi

  python -c "import json; import sys; print('\n'.join(json.load(sys.stdin)))"
}

# Encodes a string from argument to single JSON string.
json_encode_str() {
  if [ -n "${JQ}" ]; then
    # shellcheck disable=SC2016
    jq -n --arg input "$1" '$input'
    return
  fi
  python -c "import json; import sys; print(json.dumps(sys.argv[1]))" "$1"
}

# Updates JSON data to specified config.
update_json() {
  local json_path="$1"
  local new_json="$2"

  local new_config="$(mktemp)"
  register_tmp_object "${new_config}"

  echo "${new_json}" | json_merge "${json_path}" - >"${new_config}"
  cp -f "${new_config}" "${json_path}"
  chmod a+r "${json_path}"
}

# Commits a payload into given location.
# Usage: commit_payload COMPONENT SUBTYPE MD5SUM TEMP_PAYLOAD DIR VERSION
commit_payload() {
  local component="$1"
  local subtype="$2"
  local md5sum="$3"
  local temp_payload="$4"
  local dir="$5"
  local version="$6"
  local json output_name

  # Derived variables
  [ -n "${md5sum}" ] || die "Fail to get MD5 for ${component}.${subtype}."
  [ -e "${temp_payload}" ] || die "Fail to find temporary file ${temp_payload}."

  if [ -n "${subtype}" ]; then
    output_name="${component}_${subtype}_${md5sum}.gz"
  else
    output_name="${component}_${md5sum}.gz"
    subtype="file"
  fi
  if [ -n "${version}" ]; then
    version="\"version\": $(json_encode_str "${version}"),"
  fi
  json="{\"${component}\": {${version} \"${subtype}\": \"${output_name}\"}}"
  local output="${dir}/${output_name}"

  # Ideally TEMP_PAYLOAD should be deleted by cleanup, and we do want to prevent
  # deleting it in order to prevent race condition if multiple instances of this
  # program is running (so mktemp won't reuse names).
  rm -f "${output}"
  ln "${temp_payload}" "${output}" || cp -f "${temp_payload}" "${output}"

  chmod a+r "${output}"
  update_json "${json_path}" "${json}"
}

# Adds an image partition type payload.
# Usage: add_image_part JSON_PATH COMPONENT FILE PART_NO START SIZE
#  FILE is the disk image file.
#  PART_NO is the number (NR) of partition number.
#  START is the starting sector (bs=512) of partition.
#  SIZE is the number of sectors in partition.
add_image_part() {
  local json_path="$1"
  local component="$2"
  local file="$3"
  local nr="$4"
  local start="$5"
  local sectors="$6"

  local md5sum=""
  local version=""
  local output=""
  local output_dir="$(dirname "$(readlink -f "${json_path}")")"

  local tmp_file="$(mktemp -p "${output_dir}" tmp_XXXXXX.gz)"
  register_tmp_object "${tmp_file}"

  info "Adding component ${component} part ${nr} ($((sectors / 2048))M)..."
  md5sum="$(
    dd if="${file}" bs=512 skip="${start}" count="${sectors}" 2>/dev/null | \
    ${GZIP} -qcn | tee "${tmp_file}" | md5sum -b)"

  if [ "${nr}" = 3 ]; then
    # Read version from /etc/lsb-release#CHROMEOS_RELEASE_DESCRIPTION
    local rootfs_dir="$(mktemp -d)"
    register_tmp_object "${rootfs_dir}"
    sudo mount "${file}" "${rootfs_dir}" -t ext2 -o \
      ro,offset=$((start * 512)),sizelimit=$((sectors * 512))
    version="$(sed -n 's/^CHROMEOS_RELEASE_DESCRIPTION=//p' \
      "${rootfs_dir}/etc/lsb-release")"
    sudo umount "${rootfs_dir}"
  fi

  commit_payload "${component}" "part${nr}" "${md5sum%% *}" \
    "${tmp_file}" "${output_dir}" "${version}"
}

# Adds an disk image type payload.
# Usage: add_image_component JSON_PATH COMPONENT FILE
add_image_component() {
  local json_path="$1"
  local component="$2"
  local file="$3"
  local nr start sectors uuid part_command
  local rootfs_start rootfs_sectors

  # TODO(hungte) Support image in compressed form (for example, test image in
  # tar.xz) using tar -O.
  if has_tool cgpt; then
    part_command="cgpt show -q -n"
  elif has_tool partx; then
    # The order must be same as what CGPT outputs.
    part_command="partx -g -r -o START,SECTORS,NR,UUID"
  else
    die "Missing partition tools - please install cgpt or partx."
  fi

  ${part_command} "${file}" | while read start sectors nr uuid; do
    debug "${part_command} ${file} -> ${start} ${sectors} ${nr} ${uuid}"
    # ${uuid} is not really needed for add_image_part.
    add_image_part "${json_path}" "${component}" "${file}" "${nr}" \
      "${start}" "${sectors}"
  done
}

# Gets the version info from specified file component.
# Usage: get_file_component_version COMPONENT FILE
get_file_component_version() {
  local component="$1"
  local file="$2"
  # TODO(hungte) Process gzipped file.
  case "${component}" in
    toolkit)
      # TODO(hungte) Replace with --lsm.
      sh "${file}" --info | sed -n 's/Identification: //p'
      ;;
    firmware)
      head -n 50 "${file}" | sed -n 's/^ *TARGET_.*FWID="\(.*\)"/\1/p' | \
        uniq | paste -sd ';' -
      ;;
    hwid)
      sed -n 's/^checksum: //p' "${file}"
      ;;
  esac
}

# Adds a simple file type payload.
# Usage: add_file_component JSON_PATH COMPONENT FILE
add_file_component() {
  local json_path="$1"
  local component="$2"
  local file="$3"

  local md5sum=""
  local output=""
  local version=""
  local file_size="$(($(stat -c "%s" "${file}") / 1048576))M"
  local output_dir="$(dirname "$(readlink -f "${json_path}")")"

  local tmp_file="$(mktemp -p "${output_dir}" tmp_XXXXXX.gz)"
  register_tmp_object "${tmp_file}"

  if is_gzipped "${file}"; then
    # Simply copy to destination
    info "Adding component ${component} (${file_size}, gzipped)..."
    md5sum="$(tee "${tmp_file}" <"${file}" | md5sum -b)"
  else
    # gzip and copy at the same time. If we want to prevent storing original
    # file name, add -n.
    info "Adding component ${component} (${file_size})..."
    md5sum="$(${GZIP} -qcn "${file}" | tee "${tmp_file}" | md5sum -b)"
  fi
  version="$(get_file_component_version "${component}" "${file}")"
  commit_payload "${component}" "" "${md5sum%% *}" "${tmp_file}" \
    "${output_dir}" "${version}"
}

# Command "add", to add a component into payloads.
# Usage: cmd_add JSON_PATH COMPONENT FILE
cmd_add() {
  local json_path="$1"
  local component="$2"
  local file="$3"

  if [ ! -e "${json_path}" ]; then
    die "Invalid JSON config path: ${json_path}"
  fi
  if [ ! -e "${file}" ]; then
    die "Missing input file: ${file}"
  fi

  case "${component}" in
    release_image | test_image)
      add_image_component "${json_path}" "${component}" "${file}"
      ;;
    toolkit | hwid | firmware | complete)
      add_file_component "${json_path}" "${component}" "${file}"
      ;;
    *)
      die "Unknown component: ${component}"
      ;;
  esac
}

# Installs a disk image partition type payload to given location.
# Usage: install_partition JSON_URL DEST JSON_FILE COMPONENT MAPPINGS...
install_partition() {
  local json_url="$1"; shift
  local dest="$1"; shift
  local json_file="$1"; shift
  local component="$1"; shift
  local json_url_base="$(dirname "${json_url}")"
  local remote_file="" remote_url="" dest_part_dev=""
  local mapping part_from part_to

  # Each mapping comes in "from_NR to_NR" format.
  # TODO(hungte) Install partitions in parallel if pigz is not available.
  for mapping in "$@"; do
    part_from="${mapping% *}"
    part_to="${mapping#* }"
    remote_file="$( \
      json_get_file_value ".${component}.part${part_from}" "${json_file}")"
    if [ "${remote_file}" = "null" ]; then
      die "Missing payload ${component}.part${part_from} from ${json_url}."
    fi
    remote_url="${json_url_base}/${remote_file}"
    dest_part_dev="$(get_partition_dev "${dest}" "${part_to}")"
    [ -b "${dest_part_dev}" ] || die "Not a block device: ${dest_part_dev}"
    info "Installing from ${component}#${part_from} to ${dest_part_dev} ..."
    # TODO(hungte) Support better dd/pv, pre-fetch size.
    # bs is fixed on 1048576 because many dd implementations do not support
    # units like '1M' or '1m'.
    fetch "${remote_url}" | ${GZIP} -d | \
      dd of="${dest_part_dev}" bs=1048576 iflag=fullblock oflag=dsync
  done
}

# Adds a stub file for component installation.
# Usage: install_add_stub DIR COMPONENT
install_add_stub() {
  local payloads_dir="$1"
  local component="$2"
  local output_dir="${payloads_dir}/install"
  # Chrome OS test images may disable symlink and +exec on stateful partition,
  # so we have to implement the stub as pure shell scripts, and invoke the
  # component via shell.
  local stub="${output_dir}/${component}.sh"
  local command="sh ./${component}"

  case "${component}" in
    toolkit)
      command="sh ./${component} -- --yes"
      ;;
    hwid)
      ;;
    *)
      return
  esac

  # Decompress now to reduce installer dependency.
  ${GZIP} -df "${payloads_dir}/${component}.gz"

  mkdir -m 0755 -p "${output_dir}"
  echo '#!/bin/sh' >"${stub}"
  # shellcheck disable=SC2016
  echo 'cd "$(dirname "$(readlink -f "$0")")"/..' >>"${stub}"
  echo "${command}" >>"${stub}"
}

# Installs a file type payload to given location.
# Usage: install_file JSON_URL DEST JSON_FILE COMPONENT
install_file() {
  local json_url="$1"; shift
  local dest="$1"; shift
  local json_file="$1"; shift
  local component="$1"; shift
  local json_url_base="$(dirname "${json_url}")"
  local output=""

  local remote_file="$(json_get_file_value ".${component}" "${json_file}")"
  local remote_url="${json_url_base}/${remote_file}"

  local download_msg="Installing"
  if [ -z "${DO_INSTALL}" ]; then
    download_msg="Downloading"
  fi

  if [ -d "${dest}" ]; then
    # The destination is a directory.
    output="${dest}/${component}.gz"
    echo "${download_msg} from ${component} to ${output} ..."
    fetch "${remote_url}" "${dest}/${component}.gz"
  elif [ -b "${dest}" ]; then
    local dev="$(get_partition_dev "${dest}" 1)"
    if [ ! -b "${dev}" ]; then
      # The destination is a block device file for partition.
      dev="${dest}"
    fi
    local mount_point="$(mktemp -d)"
    register_tmp_object "${mount_point}"
    mount "${dev}" "${mount_point}"

    local out_dir="${mount_point}/cros_payloads"
    mkdir -p "${out_dir}"
    output="${out_dir}/${component}.gz"
    echo "${download_msg} from ${component} to ${dev}!${output#${mount_point}/}"
    fetch "${remote_url}" "${output}"
    if [ -n "${DO_INSTALL}" ]; then
      install_add_stub "${out_dir}" "${component}"
    fi
    umount "${mount_point}"
  elif [ "${dest%.gz}" = "${dest}" ]; then
    # The destination is an uncompressed file.
    output="${dest}"
    echo "${download_msg} from ${component} to ${output} ..."
    fetch "${remote_url}" | ${GZIP} -d >"${output}"
  else
    # The destination is a compressed file.
    output="${dest}.gz"
    echo "${download_msg} from ${component} to ${output} ..."
    fetch "${remote_url}" "${output}"
  fi
}

# Prints a curl friendly canonical URL of given argument.
# Usage: get_canonical_url URL
get_canonical_url() {
  local url="$*"

  case "${url}" in
    *"://"*)
      echo "$*"
      ;;
    "")
      die "Missing URL."
      ;;
    *)
      echo "file://$(readlink -f "${url}")"
      ;;
  esac
}

# Downloads (and installs if DO_INSTALL is set) components to given destination.
# If DEST_DEV is a folder, download components to the folder.
# If DEST_DEV is a partition (block device), download components to a sub folder
#  "cros_payloads" inside that partition.
# If DEST_DEV is a disk device, use its first partition as block device mode.
# Usage: install_components JSON_URL DEST_DEV [COMPONENTS...]
install_components() {
  local json_url="$1"; shift
  local dest="$1"; shift
  [ -n "${json_url}" ] || die "Need JSON URL."
  if [ ! -e "${dest}" ] && [ ! -e "$(dirname "${dest}")" ]; then
    die "Need existing destination (${dest})."
  fi
  local component
  local components="$*"

  local json_file="$(mktemp)"
  register_tmp_object "${json_file}"
  json_url="$(get_canonical_url "${json_url}")"
  info "Getting JSON config from ${json_url}..."
  fetch "${json_url}" "${json_file}"

  for component in ${components}; do
    if [ -z "${DO_INSTALL}" ]; then
      install_file "${json_url}" "${dest}" "${json_file}" "${component}"
      continue
    fi

    # All ChromeOS USB image sources have
    #  2 = Recovery Kernel
    #  3 = Root FS
    #  4 = Normal Kernel
    # And the installation on fixed storage should be
    #  2 = Test Image Normal Kernel
    #  3 = Test Image Root FS
    #  4 = Release Image Normal Kernel
    #  5 = Release Image Root FS

    # Download and install.
    case "${component}" in
      test_image)
        install_partition \
          "${json_url}" "${dest}" "${json_file}" "${component}" \
          "1 1" "4 2" "3 3"
        ;;
      release_image)
        install_partition \
          "${json_url}" "${dest}" "${json_file}" "${component}" \
          "4 4" "3 5" \
          "6 6" "7 7" "8 8" "9 9" "10 10" "11 11" "12 12"
        ;;
      toolkit | hwid | firmware | complete)
        install_file "${json_url}" "${dest}" "${json_file}" "${component}"
        ;;
      *)
        die "Unknown component: ${component}"
    esac
  done
}

# Command "download", to allow downloading components to target.
# Usage: cmd_download JSON_URL DEST_DEV COMPONENTS...
cmd_download() {
  DO_INSTALL="" install_components "$@"
}

# Command "install", to allow installing components to target.
# Usage: cmd_install JSON_URL DEST_DEV COMPONENTS...
cmd_install() {
  DO_INSTALL=1 install_components "$@"
}

# Lists available components on JSON URL.
# Usage: cmd_list "$@"
cmd_list() {
  local json_url="$1"
  json_url="$(get_canonical_url "${json_url}")"

  info "Getting JSON config from ${json_url}..."
  fetch "${json_url}" | json_get_keys
}

# Main entry.
# Usage: main "$@"
main() {
  if [ "$#" -lt 2 ]; then
    cmd_help
    exit
  fi
  set -e
  trap "die Execution failed." EXIT

  if has_tool pigz; then
    # -n in pigz controls only file name, not modtime.
    GZIP="pigz -T"
  fi
  if has_tool jq; then
    JQ="jq"
  fi
  umask 022

  TMP_OBJECTS="$(mktemp)"
  case "$1" in
    add)
      shift
      cmd_add "$@"
      ;;
    install)
      shift
      cmd_install "$@"
      ;;
    download)
      shift
      cmd_download "$@"
      ;;
    list)
      shift
      cmd_list "$@"
      ;;
    *)
      cmd_help
      die "Unknown command: $1"
      ;;
  esac
  trap cleanup EXIT
}
main "$@"
