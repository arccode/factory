#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script is used to generate the default XML/RPC request to be sent to
# shopfloor service backend. It can be used after factory wiping (in-place
# wiping tmpfs) or after factory reset (in factory reset shim) to inform
# shopfloor the operation is completed.

: "${SERIAL_NUMBER:="$(vpd -g serial_number)"}"
: "${MLB_SERIAL_NUMBER:="$(vpd -g mlb_serial_number)"}"
: "${HWID:="$(crossystem hwid)"}"

usage() {
  echo "Usage: $0 [factory_wipe|factory_reset]"
}

print_post_content() {
  local method="$1"
  local event="$2"
  shift
  shift
  cat <<__REQUEST__
<?xml version='1.0'?>
<methodCall>
 <methodName>${method}</methodName>
 <params><param><struct>
__REQUEST__

  while [ "$#" -gt 0 ]; do
    echo "  <member><name>$1</name><value>$2</value></member>"
    shift
    shift
  done

  cat <<__REQUEST__
 </struct></param>
 <param><value><string>${event}</string></value></param>
</params></methodCall>
__REQUEST__
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

  local event=""

  local post_type="$1"
  case "${post_type}" in
    factory_wipe )
      event="Finalize"
      ;;
    factory_reset )
      # Usually applied after OQC by reset shim.
      event="Refinalize"
      ;;
    *)
      usage
      exit 1
  esac

  if [ -z "${SERIAL_NUMBER}" ]; then
    die_with_error_message "'serial_number' not set in RO VPD."
  fi

  # Fields allowed in Shopfloor Service API 1.0.
  # Note 'serial_number' without 'serials' prefix was introduced in draft
  # version and we may deprecate it in future.
  print_post_content NotifyEvent "${event}" \
    serial_number "${SERIAL_NUMBER}" \
    serials.serial_number "${SERIAL_NUMBER}" \
    serials.mlb_serial_number "${MLB_SERIAL_NUMBER}" \
    hwid "${HWID}"
}

main "$@"
