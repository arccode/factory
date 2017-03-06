#!/bin/bash
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$0")"
. "${SCRIPT_DIR}/common.sh"
load_config

print_help() {
  echo "goto.sh <factory|overlay> [command...]"
  echo "  run command in FACTORY_DIR or OVERLAY_DIR"
  echo "  if command is not provied, will open a shell instead"
}

main() {
  if [[ "$0" != *"goto.sh" ]]; then
    set -- "$0" "$@"
  fi

  case "$(basename "$1")" in
    factory*)
      DIR="${FACTORY_DIR}"
      ;;
    overlay*)
      DIR="${OVERLAY_DIR}"
      ;;
    *)
      print_help
      exit 1
      ;;
  esac

  shift  # consume <factory|overlay>
  cd "${DIR}"
  if [ $# -eq 0 ]; then
    echo "${COLOR_RED}You are now in ${DIR}, use 'exit' to exit"
    echo "${COLOR_NOR}"
    echo
    "${SHELL}" -i
  else
    "${SHELL}" -i -c "$1 \"\$@\"" "$@"
  fi
}

# only execute main if this file is called directly
[ "$0" = "${BASH_SOURCE[0]}" ] && main "$@"
