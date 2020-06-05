#!/usr/bin/env bash
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This is a standalone script that serves as the bootstrap of the bundled
# payload.

# The file content in the source tree is a template string which helps other
# services to construct a bundle file easily.  Words which start with two
# exclamation marks are the placeholders for template arguments.


set -e


print_usage() {
  echo "\
Usage:
  $0 [-d PATH] [-n] [-h] [[--] ARGS...]

Description:
  Self-extract the probe bundle and then optionally execute the runner
  file !!runner_relpath included in the bundle file.

Arguments:
  -d PATH       Specify the target folder to hold the unpacked files.
                If not specified, a temporary folder will be created.
  -n            Don't execute the runner included in the bundle file,
                do the extraction only.
  -h            Shows this usage message and exit.
  ARGS...       Arguments for the !!runner_relpath in the bundle file
                if \"-n\" is not specified.
"
}


main() {
  local opt_name
  local unpack_dest_path
  local exec_runner="y"
  while getopts "d:nh" opt_name "$@"; do
    case "${opt_name}" in
      "d")
        unpack_dest_path="${OPTARG}"
        ;;
      "n")
        exec_runner=
        ;;
      "h")
        print_usage
        exit 0
        ;;
      "?")
        print_usage >&2;
        exit 1
    esac
  done
  shift "$((OPTIND-1))"

  if [ -z "${unpack_dest_path}" ]; then
    local tmpdir_arg="--tmpdir"
    [ -d "/usr/local/tmp" ] && tmpdir_arg="${tmpdir_arg}=/usr/local/tmp"
    unpack_dest_path="$(mktemp -d "${tmpdir_arg}" "bundle.XXXXXXXX")"
  fi
  echo "Unpack the bundle to ${unpack_dest_path}." >&2
  echo -n '!!payload_data' \
      | base64 -d \
      | tar -C "${unpack_dest_path}" -zx

  readonly runner_path="${unpack_dest_path}/!!runner_relpath"
  if [ -n "${exec_runner}" ]; then
    echo "Execute the runner file ${runner_path}." >&2
    exec "${runner_path}" "$@"
  fi
}


main "$@"
