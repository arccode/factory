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
#  dd tee od sed chmod basename dirname readlink mktemp stat
#  cp ln rm

# Environment settings for utilities to invoke.
: "${GZIP:="gzip"}"
: "${BZIP2:="bzip2"}"
: "${XZ:="xz"}"
: "${CROS_PAYLOAD_FORMAT:=gz}"
: "${JQ:=""}"
: "${SUDO:="sudo"}"
: "${PV:="cat"}"
: "${UFTPD:="uftpd"}"

# Debug settings
: "${DEBUG:=}"

# Constants
COMPONENTS_ALL="test_image release_image toolkit hwid firmware complete \
netboot_kernel netboot_firmware netboot_cmdline toolkit_config lsb_factory \
description project_config"

# A variable for the file name of tracking temp files.
TMP_OBJECTS=""

# The path of the directory of cros_payloads in RMA shared partition.
DIR_CROS_PAYLOADS="cros_payloads"

# The path of the directory of cros_payloads in installed partition.
OUT_DIR_CROS_PAYLOADS="dev_image/opt/${DIR_CROS_PAYLOADS}"

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

# Returns the compression format of input file or STDIN stream.
# Usage: get_compression_format [FILE]
get_compression_format() {
  # The 'file' command needs special database, so we want to directly read the
  # magic value.
  local magic="$(od -An -N262 -v -w262 -t x1 "$@")"
  case "${magic}" in
    " 1f 8b"*)
      echo "gz"
      ;;
    " 42 5a 68"*)
      echo "bz2"
      ;;
    " fd 37 7a 58 5a 00"*)
      echo "xz"
      ;;
    *" 75 73 74 61 72")
      if [ "${#magic}" = 786 ]; then
        echo "tar"
      fi
      ;;
  esac
}

# Checks if a tool program is already available on path.
# Usage: has_tool PROGRAM
has_tool() {
  type "$1" >/dev/null 2>&1
}

# Invoke pixz in a way that is similar with other compressors.
do_pixz() {
  # pixz has a different command usage that it does not have -c so we have
  # to always use redirection.
  local cmd="pixz -t"

  # '-c' and '-q' were not supported. This must be aligned with how XZ is
  # invoked in do_compress.
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -d)
        cmd="${cmd} $1"
        shift
        ;;
      -*)
        # Ignore all other commands.
        shift
        ;;
      *)
        break
        ;;
    esac
  done

  if [ "$#" -gt 1 ]; then
    die "Does not allow multiple input for pixz."
  elif [ "$#" -gt 0 ]; then
    ${cmd} <"$1"
  else
    ${cmd}
  fi
}

# Compresses or decompresses an input file or stream then output to STDOUT.
# Usage: do_compress URL [-d] [FILE]
do_compress() {
  local url="$1"
  local format="${url##*.}"
  shift

  case "${format}" in
    gz)
      ${GZIP} -cqn "$@"
      ;;
    bz2)
      ${BZIP2} -cq "$@"
      ;;
    xz)
      ${XZ} -cq "$@"
      ;;
    tar)
      # Currently we only support decompression for tar.
      if [ "$1" != "-d" ]; then
        die "Only decompression allowed for tar files."
      fi
      shift
      if [ "$#" -gt 0 ]; then
        tar -xOf "$@"
      else
        tar -xO
      fi
      ;;
    *)
      die "Unknown compression for ${url}."
  esac
}

# Returns an uncompressed file from argument.
get_uncompressed_file() {
  local file="$1"
  local file_format="$(get_compression_format "${file}")"
  if [ -n "${file_format}" ]; then
    local output="$(mktemp)"
    register_tmp_object "${output}"
    # Check if inner file is compressed - usually tar.
    local format2="$(do_compress "${file_format}" -d "${file}" |
                     get_compression_format)"
    if [ -n "${format2}" ]; then
      info "Decompressing ${format2}.${file_format} input file ${file}..."
      ${PV} "${file}" | do_compress "${file_format}" -d | \
        do_compress "${format2}" -d >"${output}"
    else
      info "Decompressing ${file_format} input file ${file}..."
      ${PV} "${file}" | do_compress "${file_format}" -d >"${output}"
    fi
    debug "Uncompressed file ready: ${file} -> ${output}"
    echo "${output}"
  else
    echo "${file}"
  fi
}

# Send `station.message` event to instalog server.
# Usage: instalog_message INSTALOG_URL UID MESSAGE
instalog_message() {
  local instalog_url="$1"; shift
  local uid="$1"; shift
  local message="$*"

  local testlog_json="$(cat <<END_TESTLOG_JSON
{
  "uuid": "${uid}",
  "time": $(date +%s),
  "apiVersion": "0.2",
  "type": "station.message",
  "logLevel": "DEBUG",
  "message": "Multicast: ${message}"
}
END_TESTLOG_JSON
)"

  curl -s -X POST --form-string "event=${testlog_json}" "${instalog_url}"
}

# Summon UFTP client to download the file with multicast protocol.
# Usage: mcast_client JSON_URL [output]
mcast_client() {
  local json_url="$1"
  local output="$2"

  local instalog_url=""
  if [ -n "${SERVER_URL}" ]; then
    instalog_url="${SERVER_URL}/instalog"
  fi

  local addr="${url%:*}"
  local port="${url#*:}"

  # UFTP uses the IP address in hexadecimal for uid by default, so we use it as
  # the uuid for instalog.
  local ip_addr="$(ip -o -4 addr list eth0 | awk '{print $4}' | cut -d '/' -f1)"
  local uid="$(echo -n "${ip_addr}" | sed "s/\./ /g" | xargs printf "%02X")"

  local RETRY_MAX=5
  local retries=0
  while [ "${retries}" -lt "${RETRY_MAX}" ]; do
    local temp_dir="$(mktemp -d)"
    local pid_file_path="$(mktemp)"
    local status_file_path="$(mktemp -u)"
    mkfifo "${status_file_path}"

    info "Summon uftpd."
    "${UFTPD}" -M "${addr}" -p "${port}" -F "${status_file_path}" \
      -P "${pid_file_path}" -D "${temp_dir}" -t -x "0"

    if [ -n "${instalog_url}" ]; then
      instalog_message "${instalog_url}" "${uid}" \
        "Client summoned. Waiting for announcement on ${url}."
    fi

    while read -r line; do
      local result="$(echo "$line" | cut -d ';' -f 1)"
      local status="$(echo "$line" | cut -d ';' -f 7)"

      if [ "${result}" = "CONNECT" ]; then
        info "Received announcement from the server. " \
          "Waiting for file transfer..."
        if [ -n "${instalog_url}" ]; then
          instalog_message "${instalog_url}" "${uid}" \
            "Announcement received." \
            "Waiting for confirmation and file transfer on ${url}."
        fi
        continue
      fi
      # Format: RESULT;timestamp;server_id;session_id;filename;size;status
      if [ "${result}" = "RESULT" ] && [ "${status}" = "copied" ]; then
        info "File transfer completed. Kill uftpd."
        if [ -n "${instalog_url}" ]; then
          instalog_message "${instalog_url}" "${uid}" \
            "File transfer completed on ${url}."
        fi
        kill "$(cat "${pid_file_path}")"

        local file_name="$(echo $line | cut -d ';' -f 5)"
        if [ -z "${output}" ]; then
          "${PV}" "${temp_dir}/${file_name}"
        else
          "${PV}" "${temp_dir}/${file_name}" > ${output}
        fi
        rm -rf "${temp_dir}" "${status_file_path}" "${pid_file_path}"

        return
      fi
    done < "${status_file_path}"


    retries=$(( retries + 1 ))
    if [ "${retries}" -ne "${RETRY_MAX}" ]; then
      info "uftpd exited unexpectedly. Clean up and restart another session."
    else
      die "Reached maximum (${RETRY_MAX}) retries for multicast download."
    fi
    rm -rf "${temp_dir}" "${status_file_path}" "${pid_file_path}"
  done
}

# Downloads from given URL. If output is not given, use STDOUT.
# if `MCAST=1`, then URL should be the remote URL of the multicast payload file.
# Also, if SERVER_URL is defined, then it will also send uftp log messages to
# instalog server (`${SERVER_URL}/instalog`).
# Usage: fetch URL [output]
fetch() {
  local url="$1"
  local output="$2"
  if [ -n "${MCAST}" ]; then
    mcast_client "${url}" "${output}"
    return
  fi

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

  install_optional JSON_URL DEST COMPONENTs...

      Same as install, but doesn't fail when COMPONENT payloads don't exist.

      Example: $0 install_optional http://a/b.json test.json /dev/mmcblk0 hwid

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

  get_file JSON_URL COMPONENT

      Get the payload file of COMPONENT in JSON_URL.

      Example: $0 get_file http://192.168.200.1:8080/static/test.json hwid

  get_all_files JSON_URL

      Get the payload file of every components in JSON_URL.

      Example: $0 get_all_files http://192.168.200.1:8080/static/test.json
  "
}

# JSON helper functions - using jq or python.

# Prettify json string
json_prettify() {
  local json_file="$1"

  # jq prettifies output by default.
  if [ -n "${JQ}" ]; then
    "${JQ}" -s '.[]' "${json_file}"
    return
  fi

  python3 -c "\
import json
import sys

def get_fd(path):
  return sys.stdin if path == '-' else open(path)

json_obj = json.load(get_fd(sys.argv[1]))
print(json.dumps(json_obj, indent=2, separators=(',', ': ')))" "${json_file}"
}

# Merges two json files into stdout.
json_merge() {
  local base_path="$1"
  local update_path="$2"

  if [ -n "${JQ}" ]; then
    "${JQ}" -c -s '.[0] * .[1]' "${base_path}" "${update_path}"
    return
  fi

  python3 -c "\
import json
import sys

def get_fd(path):
  return sys.stdin if path == '-' else open(path)

def merge(base, delta):
  for key, value in delta.items():
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

  python3 -c "\
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

  python3 -c "import json; import sys; print('\n'.join(json.load(sys.stdin)))"
}

# Gets the files of an image from a given JSON file or stdin.
json_get_image_files() {
  local component="$1"
  local json_file="$2"

  if [ -n "${JQ}" ]; then
    local filter=".${component}.crx_cache"
    for i in $(seq 1 12); do
      filter="${filter},.${component}.part${i}"
    done
    "${JQ}" -r "${filter} | select(. != null)" "${json_file}"
    return
  fi

  python3 -c "\
import json
import sys

def get_fd(path):
  return sys.stdin if path == '-' else open(path)

component_data = json.load(get_fd(sys.argv[2])).get(sys.argv[1], None)
if component_data:
  files = [component_data.get('part%d' % i, '') for i in range(1, 13)]
  print('\n'.join(files))" "${component}" "${json_file}"
}

# Gets the file of a component from a given JSON file or stdin.
json_get_file() {
  local component="$1"
  local json_file="$2"

  if [ -n "${JQ}" ]; then
          "${JQ}" -r ".${component}.file | select(. != null)" "${json_file}"
    return
  fi

  python3 -c "\
import json
import sys

def get_fd(path):
  return sys.stdin if path == '-' else open(path)

component_data = json.load(get_fd(sys.argv[2])).get(sys.argv[1], None)
if component_data:
  print(component_data.get('file', ''))" "${component}" "${json_file}"
}

# Encodes a string from argument to single JSON string.
json_encode_str() {
  if [ -n "${JQ}" ]; then
    # shellcheck disable=SC2016
    "${JQ}" -c -n --arg input "$1" '$input'
    return
  fi
  python3 -c "import json; import sys; print(json.dumps(sys.argv[1]))" "$1"
}

# Updates JSON data to specified config.
update_json() {
  local json_path="$1"
  local new_json="$2"

  local new_config="$(mktemp)"
  register_tmp_object "${new_config}"

  printf '%s' "${new_json}" | json_merge "${json_path}" - \
    | json_prettify - >"${new_config}"
  cp -f "${new_config}" "${json_path}"
  chmod a+r "${json_path}"
}

# Updates JSON meta data.
# Usage: update_json_meta JSON_PATH COMPONENT NAME VALUE
update_json_meta() {
  local json_path="$1"
  local component="$2"
  local name="$3"
  local value="$4"
  update_json "${json_path}" \
    "{\"${component}\": {\"${name}\": $(json_encode_str "${value}")}}"
}

# Commits a payload into given location.
# Usage: commit_payload COMPONENT SUBTYPE MD5SUM TEMP_PAYLOAD DIR
commit_payload() {
  local component="$1"
  local subtype="$2"
  local md5sum="$3"
  local temp_payload="$4"
  local dir="$5"
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
  json="{\"${component}\": {\"${subtype}\": \"${output_name}\"}}"
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


  if [ "${nr}" = 1 ]; then
    # Try to archive 'unencrypted' folder which contains CRX cache.
    local stateful_dir="$(mktemp -d)"
    local crx_cache_dir="unencrypted/import_extensions"
    register_tmp_object "${stateful_dir}"
    if ${SUDO} mount "${file}" "${stateful_dir}" -o \
      ro,offset=$((start * bs)),sizelimit=$((count * bs)); then
      if [ -d "${stateful_dir}/${crx_cache_dir}" ]; then
        local crx_cache_file="$(mktemp -p "${output_dir}" \
          tmp_XXXXXX."${CROS_PAYLOAD_FORMAT}")"
        register_tmp_object "${crx_cache_file}"
        local crx_cache_md5="$(tar -cC "${stateful_dir}" "${crx_cache_dir}" | \
          do_compress "${CROS_PAYLOAD_FORMAT}" | tee "${crx_cache_file}" | \
          md5sum -b)"
        commit_payload "${component}" "crx_cache" "${crx_cache_md5%% *}" \
          "${crx_cache_file}" "${output_dir}"
      fi
      ${SUDO} umount "${stateful_dir}"
    fi
  elif [ "${nr}" = 3 ]; then
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
    "${tmp_file}" "${output_dir}"

  if [ -n "${version}" ]; then
    update_json_meta "${json_path}" "${component}" version "${version}"
  fi

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

  # Reset version because add_image_part ignores partitions without version.
  update_json_meta "${json_path}" "${component}" version ""

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
      # The feature manifest is landed in 11163.0.0 .
      local json_manifest="$(sh "${file}" --manifest 2>/dev/null)" || true
      if [ -z "${json_manifest}" ]; then
        # The legacy method of getting firmware version.
        local version="$(head -n 50 "${file}" | \
          sed -n 's/^ *TARGET_.*FWID="\(.*\)"/\1/p' | uniq | paste -sd ';' -)"
        if [ -z "${version}" ]; then
          echo "Unknown-$(md5sum "${file}")"
          return
        fi
        echo ${version}
        return
      fi

      if [ -n "${JQ}" ]; then
        echo "${json_manifest}" | "${JQ}" -r \
          '.[].host.versions | "ro:" + .ro + ";" + "rw:" + .rw'
        return
      fi

      echo "${json_manifest}" | python3 -c "\
import json
import sys
j = json.load(sys.stdin)
for k in j:
  print('ro:%s;rw:%s' %
        (j[k]['host']['versions']['ro'], j[k]['host']['versions']['rw']))"
      ;;
    hwid)
      # 'shar' may add leading X on some versions.
      sed -n 's/^X*checksum: //p' "${file}"
      ;;
    complete | netboot_cmdline)
      local temp="$(md5sum "${file}")"
      echo "${temp%% *}"
      ;;
    project_config)
      local cmd="tar -xvf "${file}" --to-command='md5sum'"
      local temp="$(${cmd} | paste - - | sed 's/\s\+-$//' | sort | md5sum)"
      echo "${temp%% *}"
      ;;
    netboot_kernel)
      # vmlinuz should be unpacked to get 'Linux Version' string. Sometimes
      # we are lucky to find 'version' by compiler, but sometimes not. The
      # command 'file' may work on x86, but probably not on ARM.
      local raw_version="$(strings "${file}" | grep 'version')"
      if [ -z "${raw_version}" ]; then
        raw_version="$(file "${file}" |
          sed -n 's/.* version \([^,]*\) *, .*/\1/p')"
      fi
      if [ -n "${raw_version}" ]; then
        raw_version="${raw_version% }"
      else
        raw_version="Unknown-$(md5sum "${file}")"
        raw_version="${raw_version%% *}"
      fi
      echo "${raw_version}"
      ;;
    netboot_firmware)
      strings "${file}" | grep 'Google_' | uniq
      ;;
    toolkit_config)
      local temp="$(md5sum "${file}")"
      echo "${temp%% *}"
      ;;
    lsb_factory)
      local temp="$(md5sum "${file}")"
      echo "${temp%% *}"
      ;;
    description)
      local temp="$(md5sum "${file}")"
      echo "${temp%% *}"
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
    md5sum="$(do_compress "${CROS_PAYLOAD_FORMAT}" "${file}" | \
      tee "${tmp_file}" | md5sum -b)"
  fi
  version="$(get_file_component_version "${component}" "${file}")"
  commit_payload "${component}" "" "${md5sum%% *}" \
    "${tmp_file}" "${output_dir}"
  update_json_meta "${json_path}" "${component}" version "${version}"
}

# Cache sudo session earlier.
cache_sudo() {
  if [ -n "${SUDO}" ]; then
    ${SUDO} -v
  fi
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
      cache_sudo
      file="$(get_uncompressed_file "${file}")"
      add_image_component "${json_path}" "${component}" "${file}"
      ;;
    toolkit | hwid | firmware | complete | netboot_* | toolkit_config | \
        lsb_factory | description)
      file="$(get_uncompressed_file "${file}")"
      add_file_component "${json_path}" "${component}" "${file}"
      ;;
    project_config)
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

  update_json_meta "${json_path}" "${component}" "${name}" "${value}"
}

# Prints a python script to extract toolkit config files. The toolkit config
# file is a combination of multiple configs. The script splits these configs
# into separate config files and move them to their respective paths.
get_install_toolkit_config_script() {
  cat <<END_PYTHON_SCRIPT
import json
import sys
import os

INSTALL_PATH_MAP = {
  'active_test_list': '/usr/local/factory/py/test/test_lists',
  'cutoff': '/usr/local/factory/sh/cutoff',
  'test_list_constants': '/usr/local/factory/py/config'
}

with open(sys.argv[1]) as f:
  config = json.load(f)

for k, v in config.items():
  dir_path = INSTALL_PATH_MAP.get(k, None)
  if dir_path:
    if not os.path.exists(dir_path):
      os.makedirs(path)
    config_file_path = os.path.join(dir_path, '%s.json' % k)
    with open(config_file_path, 'w') as f:
      json.dump(v, f, indent=2, sort_keys=True)
END_PYTHON_SCRIPT
}

# Adds a stub file for component installation.
# Usage: install_add_stub COMPONENT FILE
install_add_stub() {
  local component="$1"
  local file="$2"
  local output_dir="$(dirname "${file}")/install"
  # Test image runs the stub scripts in collating order. We want the toolkit to
  # be installed first, so we prefix the stubs with prefixs to control their
  # execution order. Currently we prefix toolkit with "0_" and other with "1_".
  # See platform2/init/upstart/test-init/cros_payload.conf for the script to
  # install these components.
  local stub_prefix=""
  # Chrome OS test images may disable symlink and +exec on stateful partition,
  # so we have to implement the stub as pure shell scripts, and invoke the
  # component via shell.
  local cmd=""

  case "${component}" in
    toolkit)
      stub_prefix="0_"
      cmd="sh ./${component} -- --yes"
      ;;
    hwid)
      stub_prefix="1_"
      # Current HWID bundle expects parent folder to exist before being able to
      # extract HWID files so we have to mkdir first.
      cmd="mkdir -p /usr/local/factory; sh ./${component}"
      ;;
    toolkit_config)
      stub_prefix="1_"
      cmd="python3 -c \"$(get_install_toolkit_config_script)\" ./${component}"
      ;;
    project_config)
      stub_prefix="1_"
      project_config_dir="/usr/local/factory/${component}"
      cmd="mkdir -p ${project_config_dir}"
      cmd="${cmd} && tar -xvf ${component} -C ${project_config_dir}"
      ;;
    *)
      return
  esac

  mkdir -m 0755 -p "${output_dir}"
  local stub="${output_dir}/${stub_prefix}${component}.sh"
  echo '#!/bin/sh' >"${stub}"
  # Set default TMPDIR to /usr/local/tmp because +exec of /tmp is disabled in
  # crbug/936818. It will break some executable scripts which is unpacked in
  # temp directory. This variable will affect at least "makeself of toolkit
  # installer" and "mktemp".
  echo 'export TMPDIR="${TMPDIR:=/usr/local/tmp}"' >> "${stub}"
  # shellcheck disable=SC2016
  echo 'cd "$(dirname "$(readlink -f "$0")")"/..' >>"${stub}"
  echo "${cmd}" >>"${stub}"
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
  local mcast_enabled=""

  local remote_file="$(json_get_file_value ".${payload}" "${json_file}")"
  local remote_url="${json_url_base}/${remote_file}"
  local file_ext="${remote_file##*.}"
  local output_is_final=""
  local mount_point

  # Check if multicast resource is available.
  local mcast_config="$(json_get_file_value ".multicast.${payload}" \
                        "${json_file}")"
  if [ "${mcast_config}" != "null" ] && has_tool "${UFTPD}"; then
    mcast_enabled=1
    remote_url="${mcast_config}"
    SERVER_URL="${json_url_base##*//}"
    SERVER_URL="${SERVER_URL%%/*}"
  fi

  if [ "${remote_file}" = "null" ]; then
    if [ -n "${OPTIONAL}" ]; then
      echo "Missing payload [${payload}] from ${json_url}, ignored."
      return 0
    else
      die "Missing payload [${payload}] from ${json_url}."
    fi
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

    local out_dir="${mount_point}/${OUT_DIR_CROS_PAYLOADS}"
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
    MCAST="${mcast_enabled}" fetch "${remote_url}" | \
      do_compress ".${file_ext}" -d | \
      dd of="${dest}" bs=1048576 iflag=fullblock oflag=dsync
  elif [ -n "${DO_INSTALL}" ]; then
    echo "Installing from ${payload} to ${output_display} ..."
    MCAST="${mcast_enabled}" fetch "${remote_url}" | \
      do_compress ".${file_ext}" -d >"${output}"
    if [ -n "${mount_point}" ]; then
      install_add_stub "${payload}" "${output}"
    fi
  else
    echo "Downloading from ${payload} to ${output_display} ..."
    MCAST="${mcast_enabled}" fetch "${remote_url}" "${output}"
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
  if [ -n "${OPTIONAL}" ]; then
    fetch "${json_url}" "${json_file}" || return 0
  else
    fetch "${json_url}" "${json_file}"
  fi

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
        # The Root FS partition should be the last one to be written, since
        # this process is not atomic and we can only get image version from
        # lsb-release.
        for mapping in "6 6" "7 7" "8 8" "9 9" "10 10" "11 11" "12 12" \
          "4 4" "3 5"; do
          from="${mapping% *}"
          to="${mapping#* }"
          install_payload "partition" "${json_url}" \
            "$(get_partition_dev "${dest}" "${to}")" \
            "${json_file}" "${component}.part${from}"
        done
        ;;
      *_image.part*)
        install_payload "partition" "${json_url}" \
          "${dest}" "${json_file}" "${component}"
        ;;
      toolkit | hwid | firmware | complete | *_image.* | netboot_* | \
          toolkit_config | lsb_factory | description | project_config)
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
  DO_INSTALL="" OPTIONAL="" install_components "file" "$@"
}

# Command "install", to install components to target.
# Usage: cmd_install JSON_URL DEST COMPONENTS...
cmd_install() {
  DO_INSTALL=1 OPTIONAL="" install_components "" "$@"
}

# Command "install_optional", to install components to target if the components
# exist.
# Usage: cmd_install_optional JSON_URL DEST COMPONENTS...
cmd_install_optional() {
  DO_INSTALL=1 OPTIONAL=1 install_components "" "$@"
}

# Lists available components on JSON URL.
# Usage: cmd_list "$@"
cmd_list() {
  local json_url="$1"
  json_url="$(get_canonical_url "${json_url}")"

  info "Getting JSON config from ${json_url}..."
  fetch "${json_url}" | json_get_keys
}

# Get payload file of a component.
get_component_file() {
  local json_str="$1"
  local component="$2"

  case "${component}" in
    release_image | test_image)
      printf '%s' "${json_str}" | json_get_image_files "${component}" -
      ;;
    toolkit | hwid | firmware | complete | netboot_* | toolkit_config | \
      lsb_factory | description | project_config)
      printf '%s' "${json_str}" | json_get_file "${component}" -
      ;;
    *)
      die "Unknown component: ${component}"
      ;;
  esac
}

# Command "get_file" to get payload file of a component.
# Usage: cmd_get_file JSON_URL COMPONENT
cmd_get_file() {
  local json_url="$(get_canonical_url "$1")"
  local component="$2"

  local json_str="$(fetch "${json_url}" 2>/dev/null)"

  get_component_file "${json_str}" "${component}"
}

# Get payload file of every components.
# Usage: cmd_get_all_files JSON_URL
cmd_get_all_files() {
  local json_url="$(get_canonical_url "$1")"
  local json_str="$(fetch "${json_url}" 2>/dev/null)"

  local components="$(printf '%s' "${json_str}" | json_get_keys)"
  for component in ${components}; do
    get_component_file "${json_str}" "${component}"
  done
}

# Main entry.
# Usage: main "$@"
main() {
  if [ "$#" -lt 1 ]; then
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
  if has_tool pixz; then
    XZ="do_pixz"
  elif has_tool pxz; then
    XZ="pxz"
  fi
  if has_tool pv; then
    PV="pv"
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
    install_optional)
      shift
      cmd_install_optional "$@"
      ;;
    download)
      shift
      cmd_download "$@"
      ;;
    list)
      shift
      cmd_list "$@"
      ;;
    get_file)
      shift
      cmd_get_file "$@"
      ;;
    get_all_files)
      shift
      cmd_get_all_files "$@"
      ;;
    get_cros_payloads_dir)
      shift
      echo -n "${DIR_CROS_PAYLOADS}"
      ;;
    *)
      cmd_help
      die "Unknown command: $1"
      ;;
  esac
  trap cleanup EXIT
}
main "$@"
