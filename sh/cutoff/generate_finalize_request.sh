#!/bin/sh

# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script is used to generate the default XML/RPC request to be sent to
# shopfloor server. It can be used after factory wiping (in-place wiping tmpfs)
# or after factory reset (in factory reset shim) to inform shopfloor
# the operation is completed.

usage() {
  echo "Usage: $0 [factory_wipe|factory_reset]"
}

print_post_content() {
  echo "<?xml version='1.0'?>"
  echo "<methodCall>"
  echo "<methodName>$1</methodName>"
  echo "<params>"

  shift 1

  local var=""
  for var in "$@"
  do
    echo "<param><value><string>${var}</string></value></param>"
  done

  echo "</params>"
  echo "</methodCall>"
}

die_with_error_message() {
  echo "$@" >&2
  exit 1
}

main() {
  if [ "$#" -lt 1 ]; then
    usage
    exit 1
  fi

  local sn=""
  local method=""

  local post_type="$1"
  case "${post_type}" in
    factory_reset )
      # TODO(hungte) The method name for factory_reset should be more general.
      method="FinalizeFQC"
      ;;
    factory_wipe )
      method="Finalize"
      ;;
    *)
      usage
      exit 1
  esac

  sn="$(vpd -g serial_number)"
  if [ -z "${sn}" ];then
    die_with_error_message "serial_number is not in ro vpd"
  fi

  print_post_content "${method}" "${sn}"
}

main "$@"
