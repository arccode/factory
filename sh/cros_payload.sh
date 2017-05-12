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

# Environment settings for utilities to invoke.
: "${GZIP:="gzip"}"
: "${BZIP2:="bzip2"}"
: "${CROS_PAYLOAD_FORMAT:=gz}"
: "${JQ:=""}"
: "${SUDO:="sudo"}"

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
        ${SUDO} umount -d "${object}" 2>/dev/null || true
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

# Returns the compression format of input file.
# Usage: get_compression_format FILE
get_compression_format() {
  local input="$1"

  # The 'file' command needs special database, so we want to directly read the
  # magic value.
  local magic="$(od -An -N3 -t x1 "${input}")"
  case "${magic}" in
    " 1f 8b"*)
      echo "gz"
      ;;
    " 42 5a 68"*)
      echo "bz2"
      ;;
  esac
}

# Checks if a tool program is already available on path.
# Usage: has_tool PROGRAM
has_tool() {
  type "$1" >/dev/null 2>&1
}

# Compresses or decompresses an input file or stream. The ARGS should be options
# (-dkf) or file.
# Usage: do_compress URL ARGS
do_compress() {
  local url="$1"
  local format="${url##*.}"
  shift

  case "${format}" in
    gz)
      ${GZIP} -qn "$@"
      ;;
    bz2)
      ${BZIP2} -q "$@"
      ;;
    *)
      die "Unknown compression for ${url}."
  esac
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

  '$(basename "$0")' is an utility to manipulate imaging resources as payloads.
  All payloads will be stored as compressed file with MD5SUM in file name.
  A JSON file manages the mapping to individual files.

  The selected compression is ${CROS_PAYLOAD_FORMAT}. To change that, override
  environment variable CROS_PAYLOAD_FORMAT to 'gz' or 'bz2'.

  ARGUMENTS

    COMPONENT: The type name of imaging resource. For disk image components,
               a '.partN' can be added to specify partition N, for example
               'test_image.part1'.
               Known values: ${COMPONENTS_ALL}
    JSON_PATH: A path to local JSON configuration file.
    JSON_URL:  An URL to remote or local JSON configuration file.
    DEST:      Destination (a folder, file, or block device like /dev/sda).

  COMMANDS

  add JSON_PATH COMPONENT FILE

      Creates payloads from FILE as COMPONENT to the JSON_PATH. Payloads wil
      be stored in same folder as JSON_PATH.

      Example: $0 add static/test.json test_image chromiumos_test_image.bin

  install JSON_URL DEST COMPONENTs...

      Fetch and decompress COMPONENT payloads to DEST from remote or local
      storage associated by JSON_URL. Creates installation stubs if needed.
      If DEST is a folder or file path, COMPONENT will be created as file.
      If DEST is a block device, do partition copy if COMPONENT is a partition;
      otherwise put COMPONENT as file on first partition of DEST, in folder
      'cros_payloads', and create installer stub if needed.

      Example: $0 install http://a/b.json test.json /dev/mmcblk0 test_image

  download JSON_URL DEST COMPONENTs...

      Fetch COMPONENT payloads to DEST and keep in compressed form.
      DEST is processed in the same way as 'install' command except partition
      type COMPONENT will be treated as file type.

      Example: $0 download test.json ./output toolkit hwid release_image.part1

  add_meta JSON_PATH COMPONENT NAME VALUE

      Adds a meta data (for example, version) to a component.

      Example: $0 add_meta test.json hwid version '1.0'

  list JSON_URL

      List all available components in JSON_URL.

      Example: $0 list http://192.168.200.1:8080/static/test.json
  "
}

# JSON helper functions - using jq or python.

# Merges two json files into stdout.
json_merge() {
  local base_path="$1"
  local update_path="$2"

  if [ -n "${JQ}" ]; then
    "${JQ}" -s '.[0] * .[1]' "${base_path}" "${update_path}"
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
    "${JQ}" -n --arg input "$1" '$input'
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
  local ext="${temp_payload##*.}"

  if [ -n "${subtype}" ]; then
    output_name="${component}.${subtype}.${md5sum}.${ext}"
  else
    output_name="${component}.${md5sum}.${ext}"
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
# Usage: add_image_part JSON_PATH COMPONENT FILE PART_NO START COUNT
#  FILE is the disk image file.
#  PART_NO is the number (NR) of partition number.
#  START is the starting sector (bs=512) of partition.
#  COUNT is the number of sectors in partition.
add_image_part() {
  local json_path="$1"
  local component="$2"
  local file="$3"
  local nr="$4"
  local start="$5"
  local count="$6"
  local bs=512 bs_max="$((32 * 1024 * 1024))"

  local md5sum=""
  local version=""
  local output=""
  local output_dir="$(dirname "$(readlink -f "${json_path}")")"

  local tmp_file="$(mktemp -p "${output_dir}" \
    tmp_XXXXXX."${CROS_PAYLOAD_FORMAT}")"
  register_tmp_object "${tmp_file}"

  info "Adding component ${component} part ${nr} ($((sectors / 2048))M)..."

  # Larger bs helps dd to run faster. Another approach is to do losetup so start
  # can be 0 (with even larger bs), but setting up loop device takes additional
  # time, need root and is actually slower.
  local o_offset="$((start * bs))" o_size="$((count * bs))"
  debug "Partition info: bs=${bs}, start=${start}, count=${count}."
  # It is possible use iflag=skip_bytes to help getting larger bs, but that will
  # need dd to be GNU dd; also not getting better speed in real experiments.
  while [ "$((start % 2 == 0 && count % 2 == 0 && count > 1 &&
              bs < bs_max))" = 1 ]; do
    # dash does not allow multiple expressions in $(()).
    : "$((start /= 2)) $((count /= 2)) $((bs *= 2))"
  done
  debug "Calculated dd:  bs=${bs}, start=${start}, count=${count}."
  if [ "$((o_offset != start * bs || o_size != count * bs))" = 1 ]; then
    die "Calculation error for dd parameters."
  fi

  # TODO(hungte) Figure out a better way to detect if commands in pipe failed.
  md5sum="$(
    dd if="${file}" bs="${bs}" skip="${start}" count="${count}" 2>/dev/null \
      | do_compress "${CROS_PAYLOAD_FORMAT}" | tee "${tmp_file}" | md5sum -b)"

  if [ "${nr}" = 3 ]; then
    # Read version from /etc/lsb-release#CHROMEOS_RELEASE_DESCRIPTION
    local rootfs_dir="$(mktemp -d)"
    register_tmp_object "${rootfs_dir}"
    ${SUDO} mount "${file}" "${rootfs_dir}" -t ext2 -o \
      ro,offset=$((start * bs)),sizelimit=$((count * bs))
    version="$(sed -n 's/^CHROMEOS_RELEASE_DESCRIPTION=//p' \
      "${rootfs_dir}/etc/lsb-release")"
    ${SUDO} umount "${rootfs_dir}"
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

  # TODO(hungte) Add part0 as GPT itself.
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
  # TODO(hungte) Process compressed file.
  case "${component}" in
    toolkit)
      sh "${file}" --lsm
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
  local compressed=""

  local ext="$(get_compression_format "${file}")"
  if [ -n "${ext}" ]; then
    compressed="${ext}-compressed"
  else
    ext="${CROS_PAYLOAD_FORMAT}"
  fi

  local tmp_file="$(mktemp -p "${output_dir}" tmp_XXXXXX."${ext}")"
  register_tmp_object "${tmp_file}"

  if [ -n "${compressed}" ]; then
    # Simply copy to destination
    info "Adding component ${component} (${file_size}, ${compressed})..."
    md5sum="$(tee "${tmp_file}" <"${file}" | md5sum -b)"
  else
    # Compress and copy at the same time.
    info "Adding component ${component} (${file_size})..."
    md5sum="$(do_compress "${CROS_PAYLOAD_FORMAT}" -c "${file}" | \
      tee "${tmp_file}" | md5sum -b)"
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

# Command "add_meta", to add a meta data into component.
# Usage: cmd_add_meta JSON_PATH COMPONENT NAME VALUE
cmd_add_meta() {
  local json_path="$1"
  local component="$2"
  local name="$3"
  local value="$4"

  if [ ! -e "${json_path}" ]; then
    die "Invalid JSON config path: ${json_path}"
  fi

  update_json "${json_path}" \
    "{\"${component}\": {\"${name}\": $(json_encode_str "${value}")}}"
}

# Adds a stub file for component installation.
# Usage: install_add_stub COMPONENT FILE
install_add_stub() {
  local component="$1"
  local file="$2"
  local output_dir="$(dirname "${file}")/install"
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

  mkdir -m 0755 -p "${output_dir}"
  echo '#!/bin/sh' >"${stub}"
  # shellcheck disable=SC2016
  echo 'cd "$(dirname "$(readlink -f "$0")")"/..' >>"${stub}"
  echo "${command}" >>"${stub}"
}

# Installs (or downloads) a payload (component or part of component).
# When MODE is 'partition', dump the payload to block device DEST.
# Otherwise (MODE = file),
# If DEST is a folder, download payload to the folder.
# If DEST is a file path, download payload to that path.
# If DEST is a disk device with partitions, select its first partition.
# If (selected) DEST is a block device, mount DEST and download payloads to a
# sub folder 'cros_payloads' inside partition. Create installer stubs if needed.
# Usage: install_payload MODE JSON_URL DEST JSON_FILE PAYLOAD
install_payload() {
  local mode="$1"; shift
  local json_url="$1"; shift
  local dest="$1"; shift
  local json_file="$1"; shift
  local payload="$1"; shift
  local json_url_base="$(dirname "${json_url}")"
  local output=""
  local output_display=""

  local remote_file="$(json_get_file_value ".${payload}" "${json_file}")"
  local remote_url="${json_url_base}/${remote_file}"
  local file_ext="${remote_file##*.}"
  local output_is_final=""
  local mount_point

  if [ "${remote_file}" = "null" ]; then
    die "Missing payload [${payload}] from ${json_url}."
  fi

  if [ "${mode}" = "partition" ]; then
    # The destination must be a block device.
    [ -b "${dest}" ] || die "${dest} must be a block device."
    output="${dest}"
    output_is_final="true"
  elif [ -d "${dest}" ]; then
    # The destination is a directory.
    output="${dest}/${payload}.${file_ext}"
  elif [ ! -b "${dest}" ]; then
    # Destination is probably a file path to overwrite.
    output="${dest}"
    output_is_final="true"
  else
    # The destination is a block device file for disk or partition.
    local dev="$(get_partition_dev "${dest}" 1)"
    if [ ! -b "${dev}" ]; then
      dev="${dest}"
    fi
    mount_point="$(mktemp -d)"
    register_tmp_object "${mount_point}"
    ${SUDO} mount "${dev}" "${mount_point}"

    local out_dir="${mount_point}/cros_payloads"
    mkdir -p "${out_dir}"
    output="${out_dir}/${payload}.${file_ext}"
    output_display="${dev}!${output#${mount_point}}"
  fi

  if [ -z "${output_display}" ]; then
    output_display="${output}"
  fi
  if [ -n "${DO_INSTALL}" ] && [ -z "${output_is_final}" ]; then
    output="${output%.${file_ext}}"
    output_display="${output_display%.${file_ext}}"
  fi

  if [ "${mode}" = "partition" ]; then
    info "Installing from ${payload} to ${output} ..."
    # bs is fixed on 1048576 because many dd implementations do not support
    # units like '1M' or '1m'. Larger bs may slightly increase the speed for gz
    # payloads (for a test_image component, execution time reduced from 72s to
    # 59s for bs=2M), but that does not help bz2 payloads and also makes it
    # harder to install small partitions.
    fetch "${remote_url}" | do_compress "${remote_url}" -d | \
      dd of="${dest}" bs=1048576 iflag=fullblock oflag=dsync
  elif [ -n "${DO_INSTALL}" ]; then
    echo "Installing from ${payload} to ${output_display} ..."
    fetch "${remote_url}" | do_compress "${remote_url}" -d >"${output}"
    if [ -n "${mount_point}" ]; then
      install_add_stub "${payload}" "${output}"
    fi
  else
    echo "Downloading from ${payload} to ${output_display} ..."
    fetch "${remote_url}" "${output}"
  fi

  if [ -n "${mount_point}" ]; then
    ${SUDO} umount "${mount_point}"
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
# Usage: install_components MODE JSON_URL DEST COMPONENTS...
install_components() {
  local mode="$1"; shift
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
    if [ -n "${mode}" ]; then
      install_payload "${mode}" "${json_url}" \
        "${dest}" "${json_file}" "${component}"
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
    local from to
    case "${component}" in
      test_image)
        for mapping in "1 1" "4 2" "3 3"; do
          from="${mapping% *}"
          to="${mapping#* }"
          install_payload "partition" "${json_url}" \
            "$(get_partition_dev "${dest}" "${to}")" \
            "${json_file}" "${component}.part${from}"
        done
        ;;
      release_image)
        for mapping in "4 4" "3 5" \
          "6 6" "7 7" "8 8" "9 9" "10 10" "11 11" "12 12"; do
          from="${mapping% *}"
          to="${mapping#* }"
          install_payload "partition" "${json_url}" \
            "$(get_partition_dev "${dest}" "${to}")" \
            "${json_file}" "${component}.part${from}"
        done
        ;;
      test_image.part* | release_image.part*)
        install_payload "partition" "${json_url}" \
          "${dest}" "${json_file}" "${component}"
        ;;
      toolkit | hwid | firmware | complete)
        install_payload "file" "${json_url}" \
          "${dest}" "${json_file}" "${component}"
        ;;
      *)
        die "Unknown component: ${component}"
    esac
  done
}

# Command "download", to download components to target.
# Usage: cmd_download JSON_URL DEST_DEV COMPONENTS...
cmd_download() {
  DO_INSTALL="" install_components "file" "$@"
}

# Command "install", to install components to target.
# Usage: cmd_install JSON_URL DEST COMPONENTS...
cmd_install() {
  DO_INSTALL=1 install_components "" "$@"
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

  if [ "$(id -u)" = 0 ]; then
    SUDO=""
  fi

  # TODO(hungte) Download and install components in parallel if parallel
  # compressors cannot be found.
  if has_tool pigz; then
    # -n in pigz controls only file name, not modtime.
    GZIP="pigz -T"
  fi
  if has_tool lbzip2; then
    BZIP2="lbzip2"
  elif has_tool pbzip2; then
    BZIP2="pbzip2"
  fi
  if has_tool jq; then
    JQ="jq"
  fi
  case "${CROS_PAYLOAD_FORMAT}" in
    gz | bz2)
      ;;
    *)
      die "CROS_PAYLOAD_FORMAT must be either gz or bz2."
      ;;
  esac
  umask 022

  # TODO(hungte) Quick check dependency of all needed tools.
  TMP_OBJECTS="$(mktemp)"
  case "$1" in
    add)
      shift
      cmd_add "$@"
      ;;
    add_meta)
      shift
      cmd_add_meta "$@"
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
